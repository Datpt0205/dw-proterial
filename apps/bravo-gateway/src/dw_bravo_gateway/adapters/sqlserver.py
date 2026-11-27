"""Bravo's SQL Server, through the one driver DW holds (ADR 0027).

`mssql-python`, chosen by measurement in this image's base (ticket 63,
Comments): column grants, a trigger reading the user from CONTEXT_INFO, the
rowversion condition, SNAPSHOT reads and TLS all behave as Bravo's client
needs. Two logins, never one: reads through the read login, the write
batch through the write login (ADR 0027 decision 2). The driver is
synchronous; each call runs in a worker thread on a connection of its own,
closed after, and a write's context is cleared before the connection is
let go, so nothing of one PIC's write reaches another call.

Everything read here is named by Bravo's schema or the 11-20 trace. What is
not measured is refused, never guessed:

- `command_right`: which `ufn_B00Permission_Getdata` rows the client applies
  to open and save a screen is not traced (script 06 counts the rows), so
  it answers "unknown" and the pipeline refuses;
- the routines a screen's rules call: running one against Bravo needs the
  read login and a rolled-back harness (some of the 22 write, e.g.
  `usp_B30BizDocProcess_CreateProcess`), ticket 50; until then a call is
  undecided and a block that needs one refuses.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
import zipfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Final, Literal, TypeVar

import mssql_python

from dw_bravo.contract import (
    WRITE_KINDS,
    CustomerPoRow,
    CustomerPoRows,
    SalesOrderState,
    SoLineState,
)
from dw_bravo.expression import RuleRefusedError, UndecidableError, UnsupportedSyntaxError
from dw_bravo.import_template import read_import_template
from dw_bravo.layout import (
    Layout,
    Window,
    merge_windows,
    read_layout,
    read_template,
    read_window,
    with_template,
    with_window,
)
from dw_bravo.ports import ProcedurePort, ReferencePort, Session
from dw_bravo.sync import SYNC_TABLES, SyncPage, SyncQuery, SyncRow, as_text
from dw_bravo.watch import Component, Fingerprint
from dw_bravo_gateway.ports import (
    AmbiguousDocumentError,
    Batch,
    BravoUnavailableError,
    BravoUser,
    ColumnRight,
    CommandRight,
    DocumentNotFoundError,
    ProcedureStep,
    ReadBack,
    StaleRowError,
    Statement,
    StoredDocument,
    WriteRejectedError,
)
from dw_bravo_gateway.statements import PROCESS_PROCEDURE, SCREENS

T = TypeVar("T")

# What makes a stored layout unreadable: refused syntax, XML that does not
# parse, an archive that is not one.
_UNREADABLE: Final = (
    UndecidableError,
    UnsupportedSyntaxError,
    SyntaxError,
    ValueError,
    zipfile.BadZipFile,
)

# `B00Layout.IsTemplate` of a screen's two layouts (script 03a, 2026-11-19;
# script 06): 3 the `<DataSource>`, 0 the form. A shared template is 1 or 2.
DATA_SOURCE: Final = 3
FORM: Final = 0


@dataclass(frozen=True)
class Login:
    host: str
    port: int
    database: str
    user: str
    password: str
    encrypt: bool = True

    def __post_init__(self) -> None:
        for name in ("host", "database", "user", "password"):
            if any(c in getattr(self, name) for c in ";{}"):
                raise ValueError(f"{name} holds a character a connection string cannot")

    def connection_string(self) -> str:
        return (
            f"Server={self.host},{self.port};Database={self.database};UID={self.user};"
            f"PWD={self.password};Encrypt={'yes' if self.encrypt else 'no'};"
            "TrustServerCertificate=yes;APP=dw-bravo-gateway"
        )


def rowversion(value: object) -> str:
    if not isinstance(value, bytes | bytearray) or len(value) != 8:
        raise BravoUnavailableError("a rowversion that is not 8 bytes")
    return "0x" + bytes(value).hex().upper()


def _binary(text: str) -> bytes:
    return bytes.fromhex(text[2:])


@dataclass
class SqlServerBravo:
    """Directory, Rights, Documents, Engine and Writer over Bravo's database."""

    read: Login
    write: Login
    # A read starts its SNAPSHOT transaction itself, which SQL Server refuses
    # inside one the driver already opened (measured): reads connect in
    # autocommit, the write does not.
    connect: Callable[[str, bool], Any] = lambda cs, auto: mssql_python.connect(cs, autocommit=auto)
    # The shared template each screen loads beside its own layout
    # (`B00Command`'s TemplateName; script 03c, 2026-11-25): read from
    # `B00Layout` with the layout, its guards applied at every save. Not
    # found, or not readable, the plan stays provisional and never writes.
    templates: Mapping[str, str] = field(default_factory=lambda: {"EDIT_BizDocSO": "BizDocEditor"})

    # ----------------------------------------------------------- plumbing

    @contextmanager
    def _connection(self, login: Login, *, autocommit: bool) -> Iterator[Any]:
        try:
            connection = self.connect(login.connection_string(), autocommit)
        except Exception as failed:  # the driver's own errors: no answer
            raise BravoUnavailableError(type(failed).__name__) from None
        try:
            yield connection
        finally:
            connection.close()

    async def _in_thread(self, work: Callable[[], T]) -> T:
        return await asyncio.to_thread(work)

    def _rows(self, sql: str, parameters: Sequence[object] = ()) -> list[dict[str, object]]:
        with self._connection(self.read, autocommit=True) as connection:
            cursor = connection.cursor()
            cursor.execute("SET TRANSACTION ISOLATION LEVEL SNAPSHOT; BEGIN TRANSACTION;")
            try:
                cursor.execute(sql, tuple(parameters))
                names = [d[0] for d in cursor.description or ()]
                return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]
            finally:
                cursor.execute("IF @@TRANCOUNT > 0 ROLLBACK")

    # ---------------------------------------------------------- directory

    async def users_by_employee_code(self, employee_code: str) -> Sequence[BravoUser]:
        rows = await self._in_thread(
            lambda: self._rows(
                "SELECT Id, UserName, Ma_CbNv, IsActive, Expire FROM dbo.B00UserList"
                " WHERE Ma_CbNv = ? AND ISNULL(IsGroup, 0) = 0",
                (employee_code,),
            )
        )
        # Active: IsActive and not flagged Expire. `LockDate` is Bravo's
        # period lock (with `UsingLockDate`), not the account's.
        return [
            BravoUser(
                id=int(row["Id"]),  # type: ignore[call-overload]
                user_name=str(row["UserName"]),
                employee_code=str(row["Ma_CbNv"]) if row["Ma_CbNv"] is not None else None,
                active=row["IsActive"] in (True, 1) and not row["Expire"],
            )
            for row in rows
        ]

    # -------------------------------------------------------------- reads

    async def sales_order(self, so_no: str) -> SalesOrderState:
        """`DocCode = 'SO'` is the code the client's SO list filters on (the
        11-20 trace). The lines join on the header's `BizDocId`, as `load`."""

        def work() -> SalesOrderState:
            headers = self._rows(
                "SELECT Id, BizDocId, DocNo FROM dbo.B30BizDoc WHERE DocCode = 'SO' AND DocNo = ?",
                (so_no,),
            )
            if not headers:
                raise DocumentNotFoundError(so_no)
            if len(headers) > 1:
                raise AmbiguousDocumentError(so_no)
            [header] = headers
            rows = self._rows(
                "SELECT Id, POLine, ItemCode, Quantity9, EstimatedTimeDelivery, timestamp, IsCancel"
                " FROM dbo.B30BizDocDetailSO WHERE BizDocId = ? ORDER BY BuiltinOrder",
                (header["BizDocId"],),
            )
            return SalesOrderState(
                so_id=int(header["Id"]),  # type: ignore[call-overload]
                so_no=str(header["DocNo"]),
                lines=tuple(_line_state(row) for row in rows),
            )

        return await self._in_thread(work)

    async def customer_po(self, customer_code: str, po_no: str) -> CustomerPoRows:
        rows = await self._in_thread(
            lambda: self._rows(
                "SELECT h.DocNo, d.POLine, d.ItemCode, d.Quantity9, d.OriginalUnitCost,"
                " d.PORequestDate, d.EstimatedTimeDelivery"
                " FROM dbo.B30BizDoc h JOIN dbo.B30BizDocDetailSO d ON d.BizDocId = h.BizDocId"
                " WHERE h.DocCode = 'SO' AND h.CustomerCode = ? AND h.POCustomer = ?"
                " ORDER BY h.DocNo, d.BuiltinOrder",
                (customer_code, po_no),
            )
        )
        return CustomerPoRows(tuple(_po_row(row) for row in rows))

    async def changes(self, query: SyncQuery) -> SyncPage:
        """`SYNC_TABLES`' columns of one table past ``query.after``, in
        rowversion order (ticket 50). Table and column names come from the
        allowlist only, never from the request."""
        columns = SYNC_TABLES[query.table]
        listed = ", ".join(f"[{c}]" for c in columns)
        where = "" if query.after is None else " WHERE [timestamp] > CONVERT(binary(8), ?, 1)"
        sql = (
            f"SELECT TOP ({int(query.limit)}) [Id], [timestamp], {listed}"
            f" FROM dbo.[{query.table}]{where} ORDER BY [timestamp]"
        )
        params: tuple[object, ...] = () if query.after is None else (query.after,)
        rows = await self._in_thread(lambda: self._rows(sql, params))
        return SyncPage(
            tuple(
                SyncRow(
                    row_id=int(row["Id"]),  # type: ignore[call-overload]
                    row_version=str(rowversion(row["timestamp"])),
                    data={c: as_text(row[c]) for c in columns},
                )
                for row in rows
            )
        )

    # ------------------------------------------------------------- rights

    async def column_rights(self, user_id: int, command_key: str) -> Sequence[ColumnRight]:
        rows = await self._in_thread(
            lambda: self._rows(
                "EXEC dbo.usp_sys_GetControlPermission @_UserId = ?, @_CommandKey = ?",
                (user_id, command_key),
            )
        )
        return [
            ColumnRight(
                table=str(row["TableName"]),
                column=str(row["ColumnName"]),
                no_add_new=bool(row["NoAddNew"]),
                no_edit=bool(row["NoEdit"]),
            )
            for row in rows
        ]

    async def command_right(
        self, user_id: int, command_key: str, operation: Literal["update", "insert"]
    ) -> CommandRight:
        keys = COMMAND_KEYS.get(command_key)
        if keys is None:
            return "unknown"  # which Bravo commands carry this screen's rights: not measured
        rows = await self._in_thread(
            lambda: self._rows(
                "SELECT CommandKey, SubCommandKey, NoOpen, NoDisplay, NoAddNew, NoEdit, '1' AS Kind"
                " FROM dbo.ufn_B00Permission_Getdata(?, NULL, '1')"
                " UNION ALL SELECT CommandKey, SubCommandKey, NoOpen, NoDisplay, NoAddNew, NoEdit,"
                " '2' FROM dbo.ufn_B00Permission_Getdata(?, NULL, '2')"
                " UNION ALL SELECT CommandKey, SubCommandKey, NoOpen, NoDisplay, NoAddNew, NoEdit,"
                " '3' FROM dbo.ufn_B00Permission_Getdata(?, NULL, '3')",
                (user_id, user_id, user_id),
            )
        )
        return decide_command_right(rows, keys, operation)

    # ---------------------------------------------------------- documents

    def _columns(self, table: str) -> list[str]:
        rows = self._rows(
            "SELECT c.name FROM sys.columns c WHERE c.object_id = OBJECT_ID(?)"
            " ORDER BY c.column_id",
            (f"dbo.{table}",),
        )
        return [str(r["name"]) for r in rows]

    def _column_facts(self, table: str) -> tuple[list[str], frozenset[str], frozenset[str]]:
        """A table's columns in order; those with no default (an INSERT lists
        them NULL); those it generates (identity, rowversion, computed)."""
        rows = self._rows(
            "SELECT c.name, c.is_identity, c.is_computed, c.default_object_id,"
            " TYPE_NAME(c.system_type_id) AS system_type"
            " FROM sys.columns c WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id",
            (f"dbo.{table}",),
        )
        generated = frozenset(
            str(r["name"]).lower()
            for r in rows
            if r["is_identity"] or r["is_computed"] or r["system_type"] == "timestamp"
        )
        no_default = frozenset(
            str(r["name"]).lower()
            for r in rows
            if not r["default_object_id"] and str(r["name"]).lower() not in generated
        )
        return [str(r["name"]) for r in rows], no_default, generated

    async def view_columns(self, view: str) -> Sequence[str]:
        if not view.replace("_", "").isalnum():
            raise UndecidableError(f"{view!r} is not a view name the layout gives")
        return await self._in_thread(lambda: self._columns(view))

    async def load(self, screen: str, doc_id: int) -> StoredDocument:
        tables = SCREENS[screen]
        [line_table] = tables.lines.values()

        def work() -> StoredDocument:
            facts = {t: self._column_facts(t) for t in (tables.header, line_table)}
            order = {t: f[0] for t, f in facts.items()}
            headers = self._rows(f"SELECT * FROM dbo.{tables.header} WHERE Id = ?", (doc_id,))
            if len(headers) != 1:
                raise DocumentNotFoundError(doc_id)
            header = _stored(headers[0])
            lines = [
                _stored(row)
                for row in self._rows(
                    f"SELECT * FROM dbo.{line_table} WHERE BizDocId = ? ORDER BY BuiltinOrder",
                    (header["BizDocId"],),
                )
            ]
            locks: dict[str, int | None] = {}
            for line in lines:
                [answer] = self._rows(
                    "SELECT dbo.ufn_Prevent_Edit(?, ?, 'SO') AS locked",
                    (header["BizDocId"], line["RowId"]),
                )
                value = answer["locked"]
                locks[str(line["RowId"])] = int(value) if value is not None else None  # type: ignore[call-overload]
            return StoredDocument(
                header=header,
                lines=lines,
                column_order=order,
                prevent_edit=locks,
                no_default={t: f[1] for t, f in facts.items()},
                generated={t: f[2] for t, f in facts.items()},
            )

        return await self._in_thread(work)

    # ------------------------------------------------------------- engine

    def _screen_layouts(self, screen: str, columns: str = "") -> list[dict[str, object]]:
        """A screen's active rows in `B00Layout`: its `<DataSource>` (the
        tables and rules, `IsTemplate` 3) and its form (the window's
        controls, `IsTemplate` 0). Every `EDIT_*` screen of script 03a's
        survey (2026-11-19) and script 06's has one of each: 8212 and 8213
        for `EDIT_BizDocSO`."""
        return self._rows(
            f"SELECT l.Id, l.IsTemplate{columns}, d.LayoutData FROM dbo.B00Layout l"
            " JOIN dbo.B00LayoutData d ON d.Id = l.Id"
            " WHERE l.FormName = ? AND l.IsActive = 1"
            f" AND l.IsTemplate IN ({DATA_SOURCE}, {FORM}) ORDER BY l.Id",
            (screen,),
        )

    async def layout(self, screen: str) -> Layout:
        rows = await self._in_thread(lambda: self._screen_layouts(screen))
        sources = [r for r in rows if r["IsTemplate"] == DATA_SOURCE]
        if len(sources) != 1:
            # Which of several the client opens is not measured.
            raise UndecidableError(f"{len(sources)} active DataSource layouts for {screen}")
        name = self.templates.get(screen)
        layout = read_layout(layout_xml(sources[0]["LayoutData"]), screen, missing_template=name)
        forms = [r for r in rows if r["IsTemplate"] == FORM]
        window, why = await self._in_thread(lambda: self._window(screen, forms))
        layout = (
            replace(layout, missing_window=why) if window is None else with_window(layout, window)
        )
        if name is None:
            return layout
        template = await self._in_thread(lambda: self._template_rows(name))
        if len(template) != 1:
            # Absent or ambiguous: the plan stays provisional, never a write.
            return layout
        try:
            return with_template(layout, read_template(layout_xml(template[0]["LayoutData"]), name))
        except (UnsupportedSyntaxError, ValueError):
            return layout

    def _window(
        self, screen: str, forms: Sequence[Mapping[str, object]]
    ) -> tuple[Window | None, str]:
        """The screen's window: its one form layout, as far as every user's
        or role's own copy of it (`B00LayoutDataEdit`, which the client
        loads by `UserId`/`RoleId`) binds the same; which copy a user opens
        is not measured, so a lookup the copies bind differently refuses
        when it binds. Not readable: none, and why."""
        if len(forms) != 1:
            return None, f"{len(forms)} active form layouts"
        try:
            base = read_window(layout_xml(forms[0]["LayoutData"]), screen)
            edits = self._window_edits(forms[0]["Id"])
            variants = [read_window(layout_xml(e["LayoutData"]), screen) for e in edits]
        except _UNREADABLE as refused:
            return None, f"{type(refused).__name__}: {str(refused)[:160]}"
        except Exception as failed:  # the driver's own errors: no answer, so none
            return None, f"could not read: {type(failed).__name__}"
        why = "a user's or role's own window binds it differently (B00LayoutDataEdit)"
        return merge_windows(base, variants, why), ""

    def _window_edits(self, layout_id: object) -> list[dict[str, object]]:
        return self._rows(
            "SELECT Id, UserId, RoleId, LayoutData FROM dbo.B00LayoutDataEdit"
            " WHERE Id = ? ORDER BY UserId, RoleId",
            (layout_id,),
        )

    def _template_rows(self, name: str) -> list[dict[str, object]]:
        return self._rows(
            "SELECT l.Id, d.LayoutData FROM dbo.B00Layout l"
            " JOIN dbo.B00LayoutData d ON d.Id = l.Id"
            " WHERE l.FormName = ? AND l.IsActive = 1 AND ISNULL(l.IsTemplate, 0) > 0",
            (name,),
        )

    def procedures(self) -> ProcedurePort:
        return _NotYetCalled()

    def references(self) -> ReferencePort:
        return _NotYetCalled()

    async def session(self, user: BravoUser, branch: str, now: datetime) -> Session:
        """The session a plan runs in; the branch's own attributes from
        `B00Branch` (what `BRANCH('IsGroup')` reads). A branch not found, or
        not readable, has none: a guard that reads one is undecided and
        blocks."""

        def branch_info() -> dict[str, object]:
            try:
                rows = self._rows(
                    "SELECT IsGroup FROM dbo.B00Branch WHERE BranchCode = ? AND IsActive = 1",
                    (branch,),
                )
            except Exception:  # the driver's own errors: no answer, so none
                return {}
            if len(rows) != 1 or rows[0]["IsGroup"] is None:
                return {}
            return {"IsGroup": Decimal(int(bool(rows[0]["IsGroup"])))}

        return Session(
            user={"Id": Decimal(user.id)},
            branch=branch,
            now=now.replace(tzinfo=None),
            branch_info=await self._in_thread(branch_info),
        )

    # -------------------------------------------------------- fingerprint

    async def fingerprint(self, environment: Literal["uat", "production"]) -> Fingerprint:
        """What DW's writes depend on, measured through the read login
        (ticket 65). A definition the login cannot read (no VIEW
        DEFINITION) is "could not check", never a constant that reads as
        unchanged forever. The client version (needs VIEW SERVER STATE) is
        not measured yet."""
        screens = sorted({k.screen for k in WRITE_KINDS.values()})
        tables = sorted({t for k in WRITE_KINDS.values() for t in k.tables})

        def work() -> Fingerprint:
            components: list[Component] = []
            for screen in screens:
                components.extend(self._layout_components(screen))
                components.append(self._template_component(screen))
                # The shared template rides on the screen's command: either
                # changing pauses the screen's writes.
                name = self.templates.get(screen)
                shared = [] if name is None else self._template_rows(name)
                for row in self._rows(
                    "SELECT CommandKey, DLLName, ClassName, CtorArgs, MethodName, InvokeArgs"
                    " FROM dbo.B00Command WHERE CommandKey = ?",
                    (screen,),
                ):
                    components.append(Component("command", screen, _digest([row, shared])))
            for table in tables:
                columns = self._rows(
                    "SELECT c.name, TYPE_NAME(c.user_type_id) AS type, c.max_length,"
                    " c.precision, c.scale, c.is_nullable,"
                    " OBJECT_DEFINITION(c.default_object_id) AS dflt"
                    " FROM sys.columns c WHERE c.object_id = OBJECT_ID(?) ORDER BY c.column_id",
                    (f"dbo.{table}",),
                )
                if not columns:
                    raise BravoUnavailableError(f"cannot see the columns of {table}")
                components.append(Component("columns", table, _digest(columns)))
                for trigger in self._rows(
                    "SELECT t.name, t.is_disabled, OBJECT_DEFINITION(t.object_id) AS body"
                    " FROM sys.triggers t WHERE t.parent_id = OBJECT_ID(?)",
                    (f"dbo.{table}",),
                ):
                    if trigger["body"] is None:
                        raise BravoUnavailableError(f"cannot read trigger {trigger['name']}")
                    components.append(
                        Component("trigger", str(trigger["name"]), _digest(trigger), table=table)
                    )
            for name, kind in ROUTINES.items():
                [row] = self._rows(
                    "SELECT OBJECT_DEFINITION(OBJECT_ID(?)) AS body", (f"dbo.{name}",)
                )
                if row["body"] is None:
                    raise BravoUnavailableError(f"cannot read routine {name}")
                components.append(Component(kind, name, _digest(row["body"])))
            return Fingerprint(environment, datetime.now(UTC), tuple(components))

        return await self._in_thread(work)

    def _template_component(self, screen: str) -> Component:
        """The screen's Import templates (`B00ImportSetting`, ticket 51), as
        one component named for the screen: any of them changed, added,
        switched on or off changes it. A template the reader cannot read is
        named in `unknown`."""
        rows = self._rows(
            "SELECT Id, IsActive, LayoutData FROM dbo.B00ImportSetting"
            " WHERE CommandKey = ? ORDER BY Id",
            (screen,),
        )
        unknown: list[str] = []
        for row in rows:
            if not row["IsActive"]:
                continue
            try:
                read_import_template(layout_xml(row["LayoutData"]))
            except (UndecidableError, ValueError, zipfile.BadZipFile) as refused:
                unknown.append(f"template {row['Id']}: {str(refused)[:160]}")
        return Component(
            "template",
            screen,
            _digest(
                repr(
                    [(row["Id"], bool(row["IsActive"]), _digest(row["LayoutData"])) for row in rows]
                )
            ),
            unknown=tuple(unknown),
        )

    def _layout_components(self, screen: str) -> list[Component]:
        """The screen's layout as one component named for the screen (what
        the watch keys a screen's writes on): its DataSource and its form,
        either changed changes it. A DataSource the runner cannot read, or
        not exactly one, is named in `unknown`."""
        rows = self._screen_layouts(screen, ", l.ModifiedAt, l.ModifiedBy")
        if not rows:
            return []
        sources = [r for r in rows if r["IsTemplate"] == DATA_SOURCE]
        forms = [r for r in rows if r["IsTemplate"] == FORM]
        unknown: list[str] = []
        if len(sources) != 1:
            unknown.append(f"{len(sources)} active DataSource layouts")
        for row in sources:
            try:
                read_layout(layout_xml(row["LayoutData"]), screen, missing_template=None)
            except (UndecidableError, RuleRefusedError, ValueError) as refused:
                unknown.append(str(refused)[:200])
        window, why = self._window(screen, forms)
        if window is None:
            unknown.append(f"the window: {why}")
        edits = [e for form in forms for e in self._window_edits(form["Id"])]
        latest = max(rows, key=lambda r: str(r["ModifiedAt"]))

        def data(row: Mapping[str, object]) -> object:
            value = row["LayoutData"]
            return bytes(value) if isinstance(value, bytes | bytearray) else value

        shapes: list[tuple[object, ...]] = [
            (r["Id"], r["IsTemplate"], _digest(data(r))) for r in rows
        ]
        shapes += [(e["Id"], e["UserId"], e["RoleId"], _digest(data(e))) for e in edits]
        return [
            Component(
                "layout",
                screen,
                _digest(repr(shapes)),
                modified_at=str(latest["ModifiedAt"]),
                modified_by=str(latest["ModifiedBy"]),
                unknown=tuple(unknown),
            )
        ]

    # ------------------------------------------------------------- writer

    async def execute(self, batch: Batch) -> None:
        def work() -> None:
            with self._connection(self.write, autocommit=False) as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        "SET LOCK_TIMEOUT 10000; DECLARE @context_info AS varbinary(128);"
                        " SET @context_info = CAST(? AS varbinary(128));"
                        " SET CONTEXT_INFO @context_info;",
                        (batch.context.encode("ascii"),),
                    )
                    needed = _read_back_tables(batch)
                    read: dict[str, Mapping[str, object]] = {}
                    for statement in batch.statements:
                        keep = statement.row_id is None and statement.table.lower() in needed
                        sql, values = bind(statement, read, keep_read_back=keep)
                        cursor.execute(sql, values)
                        if keep:
                            row = _read_back_row(cursor)
                            if row is None:
                                raise WriteRejectedError(f"{statement.table}: no row read back")
                            read[statement.table.lower()] = row
                        elif cursor.rowcount != 1:
                            raise StaleRowError(statement.table)
                    for step in batch.steps:
                        cursor.execute(*bind_step(step, read))
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                finally:
                    cursor.execute("SET CONTEXT_INFO 0x")
                    connection.commit()

        await self._in_thread(work)


_NAMED = re.compile(r"@(_\w+)")


def bind(
    statement: Statement,
    read: Mapping[str, Mapping[str, object]] | None = None,
    *,
    keep_read_back: bool = False,
) -> tuple[str, tuple[object, ...]]:
    """The client's UPDATE or INSERT with its named parameters bound by
    position, each `ReadBack` resolved from ``read`` (the rows the batch's
    earlier INSERTs read back, by lower-case table).

    The read-back SELECT is left out unless ``keep_read_back``: the pipeline
    reads the document back whole (`WritePipeline._reconcile`), and the
    statement's own row count is what says whether the rowversion still held
    (an INSERT's is 1: measured with a trigger in Bravo's `SET NOCOUNT ON`
    shape, ticket 73). An INSERT whose read-back a later value needs keeps
    it, in the same batch: `SCOPE_IDENTITY()` answers only in the INSERT's
    own scope.
    """
    text = statement.sql if keep_read_back else statement.sql.split(";SELECT TOP (1)")[0] + ";"
    values: list[object] = []
    for name in _NAMED.findall(text):
        value = _resolved(statement.parameters[name], read or {})
        values.append(_binary(str(value)) if name == "_Original_timestamp" else value)
    return _NAMED.sub("?", text), tuple(values)


def _resolved(value: object, read: Mapping[str, Mapping[str, object]]) -> object:
    if not isinstance(value, ReadBack):
        return value
    row = read.get(value.table.lower())
    lowered = {k.lower(): v for k, v in (row or {}).items()}
    if row is None or value.column.lower() not in lowered:
        raise WriteRejectedError(f"{value.table}.{value.column} was not read back")
    found = lowered[value.column.lower()]
    if found is None or found == "":
        # Bravo's trigger did not fill it: a line keyed '' belongs to no SO.
        raise WriteRejectedError(f"{value.table}.{value.column} read back empty")
    return found


def _read_back_tables(batch: Batch) -> set[str]:
    values = [v for s in batch.statements for v in s.parameters.values()]
    values += [v for step in batch.steps for v in step.parameters.values()]
    return {v.table.lower() for v in values if isinstance(v, ReadBack)}


def _read_back_row(cursor: Any) -> dict[str, object] | None:
    """The one row of a statement's read-back SELECT, past whatever counts
    the statement and its triggers report first; none, or several, is None."""
    while cursor.description is None:
        if not cursor.nextset():
            return None
    names = [d[0] for d in cursor.description]
    rows = cursor.fetchall()
    if len(rows) != 1:
        return None
    return dict(zip(names, rows[0], strict=True))


@dataclass(frozen=True)
class CommandKeys:
    """Where Bravo keeps a screen's rights (`B00PermissionData`): the list
    command that opens it, the sub-commands an operation uses there, and the
    editing form's own key for its operations."""

    explorer: str
    editor: str
    sub_commands: Mapping[str, tuple[str, ...]]  # operation -> SubCommandKeys


# Which Bravo commands carry a screen's rights. Empty until script 10 (ticket
# 75) has shown, for users whose Bravo behaviour is known, that these keys
# reproduce what the client lets each of them do: until then the answer is
# "unknown" and every live write is refused, as before.
COMMAND_KEYS: Final[Mapping[str, CommandKeys]] = {}


def decide_command_right(
    rows: Sequence[Mapping[str, object]],
    keys: CommandKeys,
    operation: Literal["update", "insert"],
) -> CommandRight:
    """What `ufn_B00Permission_Getdata` (Bravo's own function, which folds a
    user's rows, their groups' and their roles' with `NoInherit`) says of an
    operation: by command (type 1), by sub-command (type 2), by the editing
    form's operation (type 3). Bravo's rights are deny-lists: a row with a
    flag set denies; no row allows."""

    def flag(row: Mapping[str, object], name: str) -> bool:
        return str(row.get(name) or 0) not in ("0", "")

    subs = {s.lower() for s in keys.sub_commands.get(operation, ())}
    if not subs:
        return "unknown"
    for row in rows:
        kind, command = str(row.get("Kind")), str(row.get("CommandKey") or "").lower()
        sub = str(row.get("SubCommandKey") or "").lower()
        if kind == "1" and command in (keys.explorer.lower(), keys.editor.lower()):
            if flag(row, "NoOpen"):
                return "denied"
        elif kind == "2" and command == keys.explorer.lower() and sub in subs:
            if flag(row, "NoOpen") or flag(row, "NoDisplay"):
                return "denied"
        elif kind == "3" and command == keys.editor.lower():
            barred = "NoEdit" if operation == "update" else "NoAddNew"
            if flag(row, barred) or flag(row, "NoOpen"):
                return "denied"
    return "allowed"


def bind_step(
    step: ProcedureStep, read: Mapping[str, Mapping[str, object]] | None = None
) -> tuple[str, tuple[object, ...]]:
    """`EXEC dbo.<procedure> @_P=?, ...` for one of the procedures a save runs
    (`statements.PROCESS_PROCEDURE` only), its arguments bound by position,
    a `ReadBack` resolved as `bind` does."""
    if step.name != PROCESS_PROCEDURE:
        raise ValueError(f"{step.name!r} is not a procedure a save runs")
    names = list(step.parameters)
    if not all(n.startswith("_") and n[1:].isalnum() for n in names):
        raise ValueError("a procedure's parameters are Bravo's own names")
    sql = f"EXEC dbo.{step.name} " + ",".join(f"@{n}=?" for n in names) + ";"
    return sql, tuple(_resolved(step.parameters[n], read or {}) for n in names)


# The routines every write depends on, by what they are to the watch: the
# context parser Bravo's triggers read the PIC from, and the rights and lock
# functions the gateway asks (ticket 65's list).
ROUTINES: Final[Mapping[str, Literal["routine", "context_parser"]]] = {
    "ufn_sys_GetUserIdFromContext_Info": "context_parser",
    "usp_sys_GetControlPermission": "routine",
    PROCESS_PROCEDURE: "routine",
    "ufn_B00Permission_Getdata": "routine",
    "ufn_sys_GetPermissionUserListTable": "routine",
    "ufn_Prevent_Edit": "routine",
}


def _digest(value: object) -> str:
    data = value if isinstance(value, bytes) else repr(value).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _line_state(row: Mapping[str, object]) -> SoLineState:
    when = row["EstimatedTimeDelivery"]
    return SoLineState(
        line_id=int(row["Id"]),  # type: ignore[call-overload]
        po_line=int(row["POLine"]),  # type: ignore[call-overload]
        item_code=str(row["ItemCode"]),
        quantity=Decimal(str(row["Quantity9"])),
        confirmed_date=when.date() if isinstance(when, datetime) else None,
        rowversion=str(rowversion(row["timestamp"])),
        cancel_state=str(row["IsCancel"]),
    )


def _day(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _po_row(row: Mapping[str, object]) -> CustomerPoRow:
    return CustomerPoRow(
        so_no=str(row["DocNo"]),
        po_line=int(row["POLine"]),  # type: ignore[call-overload]
        item_code=str(row["ItemCode"]),
        quantity=Decimal(str(row["Quantity9"])),
        unit_price=Decimal(str(row["OriginalUnitCost"])),
        requested_date=_day(row["PORequestDate"]),
        confirmed_date=_day(row["EstimatedTimeDelivery"]),
    )


def _stored(row: Mapping[str, object]) -> dict[str, object]:
    out = dict(row)
    out["timestamp"] = rowversion(out.get("timestamp"))
    return out


def layout_xml(data: object) -> str:
    """`B00LayoutData.LayoutData`: a ZIP holding one file, `Xml`."""
    if not isinstance(data, bytes | bytearray):
        raise UndecidableError("the layout is not stored as bytes")
    with zipfile.ZipFile(io.BytesIO(bytes(data))) as archive:
        if archive.namelist() != ["Xml"]:
            raise UndecidableError(f"the layout archive holds {archive.namelist()}")
        return archive.read("Xml").decode("utf-8")


class _NotYetCalled:
    """Bravo's routines are not called live yet (ticket 50): undecided."""

    def call(
        self, command: str, parameters: Mapping[str, object], outputs: Sequence[str]
    ) -> Mapping[str, object]:
        raise UndecidableError(f"{command} is not called live yet (ticket 50)")

    def find(self, lookup_key: str, code: object, filter_key: str | None) -> None:
        raise UndecidableError(f"lookup {lookup_key} is not read live yet (ticket 50)")

    def key_taken(
        self, table: str, values: Mapping[str, object], filter_key: str | None, own_id: object
    ) -> bool:
        raise UndecidableError(f"a key of {table} is not read live yet (ticket 50)")
