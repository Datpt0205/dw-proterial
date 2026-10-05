"""Downloading a generated artifact: the effect boundary until ticket 10.

A person uploads the file to Bravo or sends the draft, so the download is the
step the runtime's approval would otherwise guard (dw_sales ADR 0001). Each
download checks, in order: `sales.case.read`; the case in the caller's
workspace (404 otherwise, another tenant's included); the artifact belongs to
that case; `sales.price.read` for a price-bearing kind (403); and the state
gate per kind below (409 before its state).

The gates are ticket 06's table, landed here before any artifact exists
(G16), because a download route without them would serve whatever ticket 06
first writes. Rendering and storing the files is ticket 06's.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import ArtifactRecord, SalesUnitOfWorkFactory
from dw_sales.application.ports import ArtifactBytesPort
from dw_sales.application.support import stored_order, stored_quote
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.orders import (
    IN_BRAVO,
    CloseReason,
    FindingCode,
    MappingStatus,
    OrderCase,
    OrderStatus,
)
from dw_sales.domain.quotes import QuoteCase, QuoteStatus

_O = OrderStatus
_Q = QuoteStatus


@dataclass(frozen=True, slots=True)
class OrderGate:
    price_bearing: bool
    open_in: Callable[[OrderCase], bool]


@dataclass(frozen=True, slots=True)
class QuoteGate:
    price_bearing: bool
    open_in: Callable[[QuoteCase, AccessContext, Gate], bool]


def _unmapped_without_code(case: OrderCase) -> bool:
    unmapped = {f.line_no for f in case.findings if f.code is FindingCode.CODE_UNMAPPED}
    return any(
        line.line_no in unmapped and line.mapping.status is MappingStatus.UNMAPPED
        for line in case.lines
    )


# Ticket 06's "Download allowed when", one row per kind.
ORDER_GATES: Final[Mapping[str, OrderGate]] = {
    "bravo_upload": OrderGate(True, lambda c: c.status is _O.PREPARED or c.status in IN_BRAVO),
    "cross_check_sheet": OrderGate(True, lambda c: c.status is _O.UPLOADED_TO_BRAVO),
    "confirmation_draft": OrderGate(True, lambda c: c.status is _O.CROSS_CHECKED),
    "portal_checklist": OrderGate(True, lambda c: c.status is _O.CROSS_CHECKED),
    "correction_request": OrderGate(True, lambda c: c.status is _O.CORRECTION_REQUESTED),
    "change_summary": OrderGate(True, lambda c: c.status is _O.CHANGE_REVIEW),
    "convert_list_proposal": OrderGate(
        False,
        lambda c: any(line.mapping.status is MappingStatus.CANDIDATE_CONFIRMED for line in c.lines),
    ),
    "design_code_request": OrderGate(False, _unmapped_without_code),
    "cannot_supply_draft": OrderGate(False, lambda c: c.close_reason is CloseReason.CANNOT_SUPPLY),
}

_BEFORE_YCBG = frozenset({_Q.RECEIVED, _Q.DECLINED})


def _pricer_or_approver(case: QuoteCase, context: AccessContext, gate: Gate) -> bool:
    pricer = case.pricing.decided_by if case.pricing else None
    return context.principal_id == pricer or gate.allows(context, SalesScopes.QUOTE_APPROVE)


QUOTE_GATES: Final[Mapping[str, QuoteGate]] = {
    "ycbg_draft": QuoteGate(False, lambda c, *_: c.status not in _BEFORE_YCBG),
    "design_request_draft": QuoteGate(
        False, lambda c, *_: c.status not in _BEFORE_YCBG | {_Q.YCBG_DRAFTED}
    ),
    "spec_discussion_draft": QuoteGate(False, lambda c, *_: c.status is _Q.SPEC_DISCUSSION),
    "decline_draft": QuoteGate(False, lambda c, *_: c.status is _Q.DECLINED),
    "quotation_preview": QuoteGate(
        True,
        lambda c, ctx, gate: c.status is _Q.PENDING_APPROVAL and _pricer_or_approver(c, ctx, gate),
    ),
    "quotation_final": QuoteGate(True, lambda c, *_: c.status is _Q.APPROVED),
    "send_draft": QuoteGate(True, lambda c, *_: c.status is _Q.APPROVED),
    "master_list_update": QuoteGate(True, lambda c, *_: c.status is _Q.SENT),
}


@dataclass(frozen=True, slots=True)
class Download:
    record: ArtifactRecord
    data: bytes

    @property
    def file_name(self) -> str:
        """Kind and case, never a value from the file (ui-quality §6)."""
        return f"{self.record.kind}-{self.record.case_id}"


@dataclass(frozen=True)
class ArtifactService:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    storage: ArtifactBytesPort

    async def order_artifact(
        self, context: AccessContext, case_id: uuid.UUID, artifact_id: uuid.UUID
    ) -> Download:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            resource_type="sales_artifact",
            resource_id=str(artifact_id),
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_order(work, case_id)).case
            record = _belongs(
                await work.artifacts.get(artifact_id), CaseKind.ORDER, case_id, artifact_id
            )
        gate = ORDER_GATES.get(record.kind)
        await self._price(context, gate is None or gate.price_bearing, artifact_id)
        if gate is None or not gate.open_in(case):
            raise _closed(record, case.status.value)
        return Download(record, await self.storage.get_object(record.object_key(scope)))

    async def quote_artifact(
        self, context: AccessContext, case_id: uuid.UUID, artifact_id: uuid.UUID
    ) -> Download:
        await self.gate.require(
            context,
            SalesScopes.CASE_READ,
            resource_type="sales_artifact",
            resource_id=str(artifact_id),
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_quote(work, case_id)).case
            record = _belongs(
                await work.artifacts.get(artifact_id), CaseKind.QUOTE, case_id, artifact_id
            )
        gate = QUOTE_GATES.get(record.kind)
        await self._price(context, gate is None or gate.price_bearing, artifact_id)
        if gate is None or not gate.open_in(case, context, self.gate):
            raise _closed(record, case.status.value)
        return Download(record, await self.storage.get_object(record.object_key(scope)))

    async def _price(
        self, context: AccessContext, price_bearing: bool, artifact_id: uuid.UUID
    ) -> None:
        if price_bearing and not self.gate.allows(context, SalesScopes.PRICE_READ):
            raise PermissionDeniedError(
                "this artifact carries prices: it needs sales.price.read",
                details={"action": SalesScopes.PRICE_READ.value, "artifact_id": str(artifact_id)},
            )


def _belongs(
    record: ArtifactRecord | None, kind: CaseKind, case_id: uuid.UUID, artifact_id: uuid.UUID
) -> ArtifactRecord:
    """The artifact, when it is this case's; another case's reads as none."""
    if record is None or (record.case_kind, record.case_id) != (kind, case_id):
        raise NotFoundError(
            "the case has no such artifact",
            details={"case_id": str(case_id), "artifact_id": str(artifact_id)},
        )
    return record


def _closed(record: ArtifactRecord, status: str) -> ConflictError:
    """An artifact asked for outside its state; a kind with no gate is never served."""
    return ConflictError(
        "this artifact is not available in the case's current state",
        details={"artifact_id": str(record.artifact_id), "kind": record.kind, "status": status},
    )
