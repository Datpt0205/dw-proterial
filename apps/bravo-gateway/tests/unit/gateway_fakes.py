# ruff: noqa: E501 - the layout below is XML kept on the lines Bravo would write it
"""Fakes for the gateway's ports, each honouring its Protocol, and a small
layout written for these tests in the SO screen's own column names (no
Bravo data)."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from dw_bravo.adapters.recorded import RecordedProcedures, RecordedReferences
from dw_bravo.approval_token import ApprovalClaims, ApprovalTokenSigner, ApprovalTokenVerifier
from dw_bravo.contract import BravoTarget, LineRef, SetConfirmedDate, SetQuantity
from dw_bravo.layout import Layout, read_layout
from dw_bravo.ports import ProcedurePort, ReferencePort, Session
from dw_bravo_gateway.pipeline import WritePace, WritePipeline
from dw_bravo_gateway.ports import (
    Batch,
    BravoUnavailableError,
    BravoUser,
    ColumnRight,
    CommandRight,
    DocumentNotFoundError,
    LedgerEntry,
    LedgerStatus,
    StaleRowError,
    StoredDocument,
    SwitchState,
)
from dw_bravo_gateway.statements import SCREENS
from dw_bravo_gateway.targets import TargetBravo, Targets

LAYOUT = """<root><Tables>
<ParentTable>
  <Name>vB30BizDoc_Edit</Name>
  <Evaluators>
    <Eval_Total><DataMember>TotalQuantity</DataMember><Value>SUM(Child(Detail).Quantity9)</Value></Eval_Total>
  </Evaluators>
</ParentTable>
<ChildTable_Detail>
  <Name>vB30BizDocDetailSO_Edit</Name><Alias>Detail</Alias>
  <ColumnChanged>
    <Quantity9><Eval_Amount9 /></Quantity9>
    <Amount9><Eval_Total /></Amount9>
  </ColumnChanged>
  <Evaluators>
    <Eval_Amount9><DataMember>Amount9</DataMember><Value>Quantity9 * OriginalUnitCost</Value></Eval_Amount9>
  </Evaluators>
  <Validators>
    <QtyNotBelowMade><ClassName>BravoValidator</ClassName><SourceColumn>Quantity9</SourceColumn>
      <zValidateExpr>Quantity9 &gt;= Made</zValidateExpr></QtyNotBelowMade>
    <Late><ClassName>BravoValidator</ClassName><SourceColumn>EstimatedTimeDelivery</SourceColumn>
      <zValidateExpr>EstimatedTimeDelivery &gt;= Parent.DocDate</zValidateExpr>
      <bValidateWarning>True</bValidateWarning></Late>
  </Validators>
</ChildTable_Detail>
</Tables></root>"""

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=UTC)  # 10:00 in Vietnam
TENANT, WORKSPACE = uuid.uuid4(), uuid.uuid4()
PIC = BravoUser(id=2413, user_name="pic", employee_code="NV001", active=True)
KEY = Ed25519PrivateKey.generate()
SIGNER = ApprovalTokenSigner(KEY, "k1")
VERIFIER = ApprovalTokenVerifier({"k1": KEY.public_key()})
ROWVERSION = "0x00000000000007D2"
LINE = LineRef(so_id=10, line_id=20, line_rowversion=ROWVERSION)
SET_DATE = SetConfirmedDate(line=LINE, confirmed_date=date(2026, 12, 1))
SET_QUANTITY = SetQuantity(line=LINE, quantity=Decimal(5))
# The shipped screens: the client's word for a stored SO's save is traced
# (`Edit`, ticket 70).
TEST_SCREENS = dict(SCREENS)


def token(
    command: object = SET_DATE, *, approval: uuid.UUID | None = None, user: int = 2413
) -> str:
    return SIGNER.sign(
        approval_id=approval or uuid.uuid4(),
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        command=command,
        bravo_user_id=user,
        employee_code="NV001",
        now=NOW,
    )


def stored() -> StoredDocument:
    return StoredDocument(
        header={
            "Id": 10,
            "BizDocId": "D10",
            "BranchCode": "A01",
            "DocDate": datetime(2026, 11, 20),
            "TotalQuantity": Decimal(3),
            "ModifiedBy": 1,
            "timestamp": "0x00000000000007D1",
        },
        lines=[
            {
                "Id": 20,
                "RowId": "R20",
                "Quantity9": Decimal(3),
                "OriginalUnitCost": Decimal(2),
                "Amount9": Decimal(6),
                "Made": Decimal(2),
                "EstimatedTimeDelivery": None,
                "IsCancel": None,
                "CancelRemark": None,
                "ModifiedBy": 1,
                "timestamp": ROWVERSION,
            }
        ],
        column_order={
            "B30BizDoc": ["Id", "BizDocId", "BranchCode", "DocDate", "ModifiedBy", "TotalQuantity"],
            "B30BizDocDetailSO": [
                "Id",
                "RowId",
                "Quantity9",
                "OriginalUnitCost",
                "Amount9",
                "Made",
                "ModifiedBy",
                "EstimatedTimeDelivery",
                "IsCancel",
                "CancelRemark",
            ],
        },
        prevent_edit={"R20": 0},
    )


@dataclass
class FakeSwitches:
    state_: SwitchState = "enabled"
    target_: BravoTarget | None = "uat"

    async def state(self, tenant_id: uuid.UUID, workspace_id: uuid.UUID, kind: str) -> SwitchState:
        return self.state_

    async def target(self, tenant_id: uuid.UUID) -> BravoTarget | None:
        return self.target_


@dataclass
class FakeLedger:
    """Honours `Ledger`: an approval id is claimed once, ever."""

    entries: dict[uuid.UUID, LedgerEntry] = field(default_factory=dict)

    async def find(self, claims: ApprovalClaims) -> LedgerEntry | None:
        return self.entries.get(claims.approval_id)

    async def claim(self, claims: ApprovalClaims) -> bool:
        if claims.approval_id in self.entries:
            return False
        self.entries[claims.approval_id] = LedgerEntry(
            claims.approval_id, "claimed", claims.kind, claims.content_hash
        )
        return True

    async def settle(
        self, claims: ApprovalClaims, status: LedgerStatus, detail: Mapping[str, object]
    ) -> None:
        entry = self.entries[claims.approval_id]
        self.entries[claims.approval_id] = replace(entry, status=status, detail=dict(detail))


@dataclass
class FakeDirectory:
    users: list[BravoUser] = field(default_factory=lambda: [PIC])
    down: bool = False

    async def users_by_employee_code(self, employee_code: str) -> Sequence[BravoUser]:
        if self.down:
            raise BravoUnavailableError("no answer")
        return [u for u in self.users if u.employee_code == employee_code]


@dataclass
class FakeRights:
    command: CommandRight = "allowed"
    columns: list[ColumnRight] = field(default_factory=list)
    # Bravo's answer for one operation where it differs from `command`.
    by_operation: dict[str, CommandRight] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    async def column_rights(self, user_id: int, command_key: str) -> Sequence[ColumnRight]:
        return self.columns

    async def command_right(
        self, user_id: int, command_key: str, operation: Literal["update", "insert"]
    ) -> CommandRight:
        self.asked.append(operation)
        return self.by_operation.get(operation, self.command)


@dataclass
class FakeBravo:
    """Documents and the writer over one held document, as Bravo would:
    a statement whose rowversion no longer matches touches no row."""

    document: StoredDocument = field(default_factory=stored)
    batches: list[Batch] = field(default_factory=list)
    fail_with: Exception | None = None
    tamper: dict[str, object] = field(default_factory=dict)  # a trigger's own change
    version: int = 0x7D2
    # Bravo's `DML_B30BizDocDetailSO_InsertUpdate_RowId`: a new line's RowId
    # filled from its Id (off: the trigger's join found nothing).
    fills_row_id: bool = True
    tamper_new: dict[str, object] = field(default_factory=dict)  # on each new line

    async def load(self, screen: str, doc_id: int) -> StoredDocument:
        if doc_id != self.document.header["Id"]:
            raise DocumentNotFoundError(doc_id)
        return replace(
            self.document,
            header=dict(self.document.header),
            lines=[dict(line) for line in self.document.lines],
        )

    async def execute(self, batch: Batch) -> None:
        self.batches.append(batch)
        if self.fail_with is not None:
            raise self.fail_with
        rows = {"B30BizDoc": [self.document.header], "B30BizDocDetailSO": self.document.lines}
        updates = [s for s in batch.statements if s.row_id is not None]
        for statement in updates:
            row = next(r for r in rows[statement.table] if r["Id"] == statement.row_id)
            if row["timestamp"] != statement.parameters["_Original_timestamp"]:
                raise StaleRowError(statement.table)
        for statement in batch.statements:
            if statement.row_id is None:
                new_id = max(int(r["Id"]) for r in rows[statement.table]) + 1  # type: ignore[call-overload]
                row = {"Id": new_id}
                rows[statement.table].append(row)
            else:
                row = next(r for r in rows[statement.table] if r["Id"] == statement.row_id)
            for name, value in statement.parameters.items():
                if not name.startswith(("_Original_", "_Id")):
                    row[name[1:]] = value
            self.version += 1
            row["timestamp"] = f"0x{self.version:016X}"
            if statement.row_id is None:
                if self.fills_row_id:
                    row["RowId"] = f"R{row['Id']}"
                row.update(self.tamper_new)
        self.document.lines[0].update(self.tamper)


@dataclass
class FakeEngine:
    layout_: Layout = field(
        default_factory=lambda: read_layout(LAYOUT, "EDIT_BizDocSO", missing_template=None)
    )
    views: dict[str, list[str]] = field(default_factory=dict)

    async def layout(self, screen: str) -> Layout:
        return self.layout_

    def procedures(self) -> ProcedurePort:
        return RecordedProcedures()

    def references(self) -> ReferencePort:
        return RecordedReferences()

    async def session(self, user: BravoUser, branch: str, now: datetime) -> Session:
        return Session(user={"Id": Decimal(user.id)}, branch=branch, now=now.replace(tzinfo=None))

    async def view_columns(self, view: str) -> Sequence[str]:
        return self.views.get(view, [])


@dataclass
class Gateway:
    pipeline: WritePipeline
    switches: FakeSwitches
    ledger: FakeLedger
    directory: FakeDirectory
    rights: FakeRights
    bravo: FakeBravo


def gateway(**over: object) -> Gateway:
    switches, ledger, directory = FakeSwitches(), FakeLedger(), FakeDirectory()
    rights, bravo = FakeRights(), FakeBravo()
    pipeline = WritePipeline(
        verifier=VERIFIER,
        switches=switches,
        ledger=ledger,
        directory=directory,
        rights=rights,
        documents=bravo,
        engine=FakeEngine(),
        writer=bravo,
        now=lambda: NOW,
        tenant_id=TENANT,
        target="uat",
        screens=TEST_SCREENS,
        pace=WritePace(),
    )
    for name, value in over.items():
        setattr(pipeline, name, value)
    return Gateway(pipeline, switches, ledger, directory, rights, bravo)


def targets(gw: Gateway, **reads: object) -> Targets:
    """The gateway's router over one target, UAT: the pipeline and ``reads``
    (`orders`, `directory`, `sync`, `fingerprints`)."""
    return Targets(TENANT, gw.switches, {"uat": TargetBravo(gw.pipeline, **reads)})  # type: ignore[arg-type]
