"""The 11-20 UAT trace, replayed through the gateway (ticket 63, acceptance 3).

For each saved SO UPDATE whose typed edit is a gateway command (a quantity,
a confirmed date), the command is signed, sent through every check of
`WritePipeline` against the document as it stood before the save, and the
statements the gateway would send are compared with the client's own:
the context line, each UPDATE's text, and each written value.

The trace and the layouts are Proterial's and stay out of git; this test
reads them from `DW_BRAVO_TRACE` and `DW_BRAVO_LAYOUTS` and skips where they
are absent, as ticket 59's do. What the trace cannot say is stubbed and named:
the lock (`ufn_Prevent_Edit`'s result is not in a trace) and the rights (a
`usp_sys_GetControlPermission` result neither).
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from gateway_fakes import SIGNER, TENANT, VERIFIER, WORKSPACE, FakeLedger, FakeRights, FakeSwitches

from dw_bravo.contract import LineRef, SetConfirmedDate, SetQuantity
from dw_bravo.layout import Layout, read_layout
from dw_bravo.ports import ProcedurePort, ReferencePort, Session
from dw_bravo.testing import sql_trace
from dw_bravo.testing.replay import SaveState, ScreenReplay, group_saves, so_screen_replay
from dw_bravo_gateway.pipeline import WritePace, WritePipeline
from dw_bravo_gateway.ports import Batch, BravoUser, StoredDocument
from dw_bravo_gateway.statements import SCREENS

LAYOUTS = os.environ.get("DW_BRAVO_LAYOUTS")
TRACE = os.environ.get("DW_BRAVO_TRACE")
SO_LAYOUT = "layout_8212_EDIT_BizDocSO__Xml"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        not LAYOUTS
        or not (Path(LAYOUTS) / SO_LAYOUT).is_file()
        or not TRACE
        or not Path(TRACE).is_file(),
        reason="Proterial's layouts and UAT trace are not on this machine",
    ),
]

_UPDATE = re.compile(r"UPDATE TOP \(1\) .*? WHERE Id=@_Id;")
_CONTEXT = re.compile(r"CAST\(''(.*?)'' AS varbinary\(128\)\)")
_DECLARED = re.compile(r"@_(\w+) ")


def _column_order(write: sql_trace.Write) -> list[str]:
    """A table's columns in the client's order: its parameter declarations."""
    sql = write.statement.sql
    declared = sql[sql.find(",N'@_") + 3 : sql.find("',@_", sql.find(",N'@_") + 3)]
    return [n for n in _DECLARED.findall(declared + " ") if not n.startswith("Original_")]


def _rowversion(value: object) -> str:
    text = str(value)
    return "0x" + text[2:].upper()


@dataclass
class TraceBravo:
    """Documents, engine and writer answering from one save of the trace."""

    screen_layout: Layout
    replay: ScreenReplay
    state: SaveState
    user: BravoUser
    before: StoredDocument
    after: StoredDocument
    batches: list[Batch] = field(default_factory=list)
    loads: int = 0

    async def load(self, screen: str, doc_id: int) -> StoredDocument:
        self.loads += 1
        return self.before if self.loads == 1 else self.after

    async def execute(self, batch: Batch) -> None:
        self.batches.append(batch)

    async def users_by_employee_code(self, employee_code: str) -> list[BravoUser]:
        return [self.user]

    async def layout(self, screen: str) -> Layout:
        return self.screen_layout

    def procedures(self) -> ProcedurePort:
        return self.replay.procedures(self.state)

    def references(self) -> ReferencePort:
        from dw_bravo.testing.replay import _NoReferences

        return _NoReferences()

    async def session(self, user: BravoUser, branch: str, now: datetime) -> Session:
        return self.replay.session_for(self.state.save)


def _fixed(at: datetime) -> Callable[[], datetime]:
    return lambda: at


def _stored(
    header: dict[str, object],
    lines: list[dict[str, object]],
    written: dict[str, sql_trace.Write],
    replay: ScreenReplay,
) -> StoredDocument:
    header = dict(header)
    lines = [dict(line) for line in lines]
    order: dict[str, list[str]] = {}
    for label, write in written.items():
        order[write.table] = _column_order(write)
        if label == "Parent":
            header["timestamp"] = _rowversion(write.values["Original_timestamp"])
        else:
            line = next(
                x for x in lines if x.get("BuiltinOrder") == write.values.get("BuiltinOrder")
            )
            line["timestamp"] = _rowversion(write.values["Original_timestamp"])
    for row in (header, *lines):
        row.setdefault("timestamp", "0x0000000000000000")
    return StoredDocument(
        header=header,
        lines=lines,
        derived_header=replay.derive_header(header),
        derived_lines=[replay.derive_line(line) for line in lines],
        column_order=order,
        # Not in a trace: the lock function's result. The replay measures
        # the statements, so the lock is taken as open, and said so here.
        prevent_edit={str(line.get("RowId")): 0 for line in lines},
    )


async def test_every_traced_so_update_a_command_covers_is_the_clients_own_statement() -> None:
    statements = sql_trace.read(Path(TRACE or ""))
    saves = group_saves(sql_trace.writes(statements), "EDIT_BizDocSO")
    calls = [
        c for c in sql_trace.procedure_calls(statements) if c.statement.screen == "EDIT_BizDocSO"
    ]
    traced_context = _CONTEXT.search(saves[0].writes[0].statement.sql)
    assert traced_context is not None
    _, user_id, _, branch, _ = traced_context.group(1).split("@")
    event = traced_context.group(1).split("@")[0].strip().split("|")[1]
    layout = read_layout(
        (Path(LAYOUTS or "") / SO_LAYOUT).read_text(encoding="utf-8"),
        "EDIT_BizDocSO",
        missing_template="BizDocEditor",
    )
    replay = so_screen_replay(layout, int(user_id), branch)
    # The trace's session saved with `<screen>|<event>`; the shipped table
    # measures none for an existing SO, so the replay names the traced one.
    screens = {"EDIT_BizDocSO": replace(SCREENS["EDIT_BizDocSO"], context_event={"update": event})}
    user = BravoUser(id=int(user_id), user_name="pic", employee_code="NV-TRACE", active=True)

    covered, skipped, refusals = 0, [], set()
    for state in replay.states(saves, calls):
        result = replay._replay_update(state.save, state.header, state.lines, state.window)
        roots = [(label, cols) for label, cols in result.roots.items()]
        before_h, before_l, _, after_l, written = replay.before_after(state)
        if len(roots) != 1 or not roots[0][0].startswith("Detail#") or len(roots[0][1]) != 1:
            skipped.append([c for _, cols in roots for c in cols])
            continue
        label, [column] = roots[0]
        index = int(label.split("#")[1])
        before = _stored(before_h, before_l, written, replay)
        line = before.lines[index]
        ref = LineRef(
            so_id=int(Decimal(str(before.header["Id"]))),
            line_id=int(Decimal(str(line["Id"]))),
            line_rowversion=str(line["timestamp"]),
        )
        typed = after_l[index][column]
        if column == "Quantity9":
            command: SetQuantity | SetConfirmedDate = SetQuantity(
                line=ref, quantity=Decimal(str(typed))
            )
        elif column == "EstimatedTimeDelivery":
            assert isinstance(typed, datetime) and typed.time() == datetime.min.time()
            command = SetConfirmedDate(line=ref, confirmed_date=typed.date())
        else:
            skipped.append([column])
            continue
        at = state.save.at.replace(tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
        bravo = TraceBravo(layout, replay, state, user, before, before)
        pipeline = WritePipeline(
            verifier=VERIFIER,
            switches=FakeSwitches(),
            ledger=FakeLedger(),
            directory=bravo,
            rights=FakeRights(),
            documents=bravo,
            engine=bravo,
            writer=bravo,
            now=_fixed(at),
            screens=screens,
            pace=WritePace(),
        )
        token = SIGNER.sign(
            approval_id=uuid.uuid4(),
            tenant_id=TENANT,
            workspace_id=WORKSPACE,
            command=command,
            bravo_user_id=user.id,
            employee_code="NV-TRACE",
            now=at,
        )

        preview = await pipeline.preview(command, token)

        # Today the gateway holds every such save back: the real layout's
        # blocking validators without a ClassName wait on the shared template
        # (script 03c) and stay undecided, and the plan is provisional. What it
        # would send once they are decided is the client's own save.
        assert preview.check == "rules" and (preview.reason or "").startswith("undecided: ")
        refusals.add(preview.reason or "")
        batch = preview.batch
        assert batch is not None, (state.save.at, preview)
        assert bravo.batches == []  # a preview sends nothing
        client = next(iter(written.values())).statement.sql
        assert batch.context == _CONTEXT.search(client).group(1)  # type: ignore[union-attr]
        assert len(batch.statements) == len(written)
        for ours in batch.statements:
            theirs = next(w for w in written.values() if w.table == ours.table)
            client_update = _UPDATE.search(theirs.statement.sql)
            assert client_update is not None
            assert _assignments(ours.sql) == _assignments(client_update.group(0))
            assert _frame(ours.sql) == _frame(client_update.group(0)), (state.save.at, ours.table)
            for name, value in ours.parameters.items():
                if name.startswith(("_Original_", "_Id")):
                    continue
                assert _equal(value, theirs.values.get(name[1:])), (state.save.at, name)
        covered += 1

    # Three of the six saved UPDATEs are a gateway command (a quantity, two
    # confirmed dates). The others: a header's PO number (not a command), a
    # split's first half (`Divide`; its new line waits on script 03c), and a
    # cancel being cleared (IsCancel, CancelPrice, CancelQuantity set to
    # NULL), which is not a cancel; a real one is ticket 52's to trace.
    assert covered == 3, skipped
    assert sorted(map(tuple, skipped)) == [
        ("Divide",),
        ("IsCancel", "CancelPrice", "CancelQuantity"),
        ("POCustomer",),
    ]
    print("held back:", sorted(refusals))


_SET = re.compile(r"^(UPDATE TOP \(1\) \w+ SET )(.*?)( WHERE .*)$")


def _assignments(sql: str) -> set[str]:
    """The SET list as a set: the client's order is its own (statements.py)."""
    match = _SET.match(sql)
    assert match is not None, sql
    return set(match.group(2).split(","))


def _frame(sql: str) -> tuple[str, str]:
    """Everything but the SET list: the table, the WHERE and the read-back."""
    match = _SET.match(sql)
    assert match is not None, sql
    return match.group(1), match.group(3)


def _equal(ours: object, theirs: object) -> bool:
    if isinstance(ours, Decimal | int) and isinstance(theirs, Decimal | int):
        return Decimal(ours) == Decimal(theirs)
    return ours == theirs
