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
from dataclasses import dataclass, field
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
from dw_bravo.expression import RuleRefusedError, UndecidableError
from dw_bravo.import_template import read_import_template
from dw_bravo.layout import Layout, read_layout
from dw_bravo.ports import ProcedurePort, ReferencePort, Session
from dw_bravo.watch import Component, Fingerprint
from dw_bravo_gateway.ports import (
    AmbiguousDocumentError,
    Batch,
    BravoUnavailableError,
    BravoUser,
    ColumnRight,
    CommandRight,
    DocumentNotFoundError,
    StaleRowError,
    Statement,
    StoredDocument,
)
from dw_bravo_gateway.statements import SCREENS

T = TypeVar("T")


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
    # The shared template each screen's layout leans on and DW does not hold
    # yet (script 03c): a plan made without it is provisional and never writes.
    missing_templates: Mapping[str, str] = field(
        default_factory=lambda: {"EDIT_BizDocSO": "BizDocEditor"}
    )

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
                "SELECT Id, POLine, ItemCode, Quantity9, EstimatedTimeDelivery, timestamp"
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
        return "unknown"

    # ---------------------------------------------------------- documents

    def _columns(self, table: str) -> list[str]:
        rows = self._rows(
            "SELECT c.name FROM sys.columns c WHERE c.object_id = OBJECT_ID(?)"
            " ORDER BY c.column_id",
            (f"dbo.{table}",),
        )
        return [str(r["name"]) for r in rows]

    async def load(self, screen: str, doc_id: int) -> StoredDocument:
        tables = SCREENS[screen]
        [line_table] = tables.lines.values()

        def work() -> StoredDocument:
            order = {t: self._columns(t) for t in (tables.header, line_table)}
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
                header=header, lines=lines, column_order=order, prevent_edit=locks
            )

        return await self._in_thread(work)

    # ------------------------------------------------------------- engine

    async def layout(self, screen: str) -> Layout:
        rows = await self._in_thread(
            lambda: self._rows(
                "SELECT l.Id, d.LayoutData FROM dbo.B00Layout l"
                " JOIN dbo.B00LayoutData d ON d.Id = l.Id"
                " WHERE l.FormName = ? AND l.IsActive = 1 AND ISNULL(l.IsTemplate, 0) = 0",
                (screen,),
            )
        )
        if len(rows) != 1:
            # Which of several the client opens is not measured.
            raise UndecidableError(f"{len(rows)} active layouts for {screen}")
        return read_layout(
            layout_xml(rows[0]["LayoutData"]),
            screen,
            missing_template=self.missing_templates.get(screen),
        )

    def procedures(self) -> ProcedurePort:
        return _NotYetCalled()

    def references(self) -> ReferencePort:
        return _NotYetCalled()

    async def session(self, user: BravoUser, branch: str, now: datetime) -> Session:
        return Session(user={"Id": Decimal(user.id)}, branch=branch, now=now.replace(tzinfo=None))

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
                for row in self._rows(
                    "SELECT CommandKey, DLLName, ClassName, CtorArgs, MethodName, InvokeArgs"
                    " FROM dbo.B00Command WHERE CommandKey = ?",
                    (screen,),
                ):
                    components.append(Component("command", screen, _digest(row)))
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
        rows = self._rows(
            "SELECT l.Id, l.ModifiedAt, l.ModifiedBy, d.LayoutData FROM dbo.B00Layout l"
            " JOIN dbo.B00LayoutData d ON d.Id = l.Id"
            " WHERE l.FormName = ? AND l.IsActive = 1 AND ISNULL(l.IsTemplate, 0) = 0",
            (screen,),
        )
        found = []
        for row in rows:
            unknown: tuple[str, ...] = ()
            try:
                read_layout(layout_xml(row["LayoutData"]), screen, missing_template=None)
            except (UndecidableError, RuleRefusedError, ValueError) as refused:
                unknown = (str(refused)[:200],)
            data = row["LayoutData"]
            found.append(
                Component(
                    "layout",
                    screen if len(rows) == 1 else f"{screen}#{row['Id']}",
                    _digest(bytes(data) if isinstance(data, bytes | bytearray) else data),
                    modified_at=str(row["ModifiedAt"]),
                    modified_by=str(row["ModifiedBy"]),
                    unknown=unknown,
                )
            )
        return found

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
                    for statement in batch.statements:
                        sql, values = bind(statement)
                        cursor.execute(sql, values)
                        if cursor.rowcount != 1:
                            raise StaleRowError(statement.table)
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
                finally:
                    cursor.execute("SET CONTEXT_INFO 0x")
                    connection.commit()

        await self._in_thread(work)


_NAMED = re.compile(r"@(_\w+)")


def bind(statement: Statement) -> tuple[str, tuple[object, ...]]:
    """The client's UPDATE with its named parameters bound by position.

    The read-back SELECT is left out: the pipeline reads the document back
    whole (`WritePipeline._reconcile`), and the UPDATE's own row count is
    what says whether the rowversion still held.
    """
    update = statement.sql.split(";SELECT TOP (1)")[0] + ";"
    values: list[object] = []
    for name in _NAMED.findall(update):
        value = statement.parameters[name]
        values.append(_binary(str(value)) if name == "_Original_timestamp" else value)
    return _NAMED.sub("?", update), tuple(values)


# The routines every write depends on, by what they are to the watch: the
# context parser Bravo's triggers read the PIC from, and the rights and lock
# functions the gateway asks (ticket 65's list).
ROUTINES: Final[Mapping[str, Literal["routine", "context_parser"]]] = {
    "ufn_sys_GetUserIdFromContext_Info": "context_parser",
    "usp_sys_GetControlPermission": "routine",
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
