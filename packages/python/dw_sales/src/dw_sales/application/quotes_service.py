"""Quote cases through the API: reading them and each Sales step.

The same path as an order's decision: the scope first, the case in the
caller's workspace, the version decided on, then the case decides
(`QuoteCase`) and the next case is stored with its event and audit row in
one transaction.

**Submitting and the approval are DW1's run** (`dw_sales.application.runs`,
dw_sales ADR 0004): the quotation is submitted inside a run that pauses on a
`sales.quote` approval in the platform's approvals, decided by
`sales.quote.approve` and never by the pricer, and applied to the case when
the run resumes (`CaseDecisions`). A step here that moves a quotation out of
`pending_approval` (priced again, declined) withdraws that approval.

A price is the caller's own decision, stamped with their principal id and
the server's time; its LME month is named by the caller and its figure read
from master data, never taken from the request (`QuotationService`).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from dw_kernel.errors import ConflictError, DomainError
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.ports import SalesCatalogPort
from dw_sales.application.quotation import QuotationService, ScreeningRow
from dw_sales.application.runs import (
    PendingDecisionsPort,
    awaiting,
    subject_of,
    withdraw_if_left,
)
from dw_sales.application.support import (
    decided,
    person_event,
    same_version,
    save_quote,
    stored_quote,
)
from dw_sales.application.views import (
    CaseChangeView,
    PendingDecisionView,
    QuoteCaseView,
    QuoteSummaryView,
    quote_case,
    quote_change,
    quote_summary,
)
from dw_sales.domain.catalog import CopperBasis
from dw_sales.domain.dispositions import CaseKind
from dw_sales.domain.pricing import Incoterm
from dw_sales.domain.quotes import (
    DeclineReason,
    LinePrice,
    PricingDecision,
    QuoteActor,
    QuoteCapability,
    QuoteCase,
    QuoteFindingCode,
    QuoteStatus,
)

_QUOTE = "sales_quote_case"
# The day a quotation is issued and screened on is the seller's calendar day.
_LOCAL = ZoneInfo("Asia/Ho_Chi_Minh")

SpecStep = Literal["start", "settle", "ask_design_again"]


def local_day(at: datetime) -> date:
    return at.astimezone(_LOCAL).date()


def quote_actor(context: AccessContext, gate: Gate) -> QuoteActor:
    """The caller as the case knows them: the approve capability only with
    `sales.quote.approve`, whatever else their roles hold."""
    capabilities = (
        frozenset({QuoteCapability.APPROVE})
        if gate.allows(context, SalesScopes.QUOTE_APPROVE)
        else frozenset()
    )
    return QuoteActor(user_id=context.principal_id, capabilities=capabilities)


@dataclass(frozen=True, slots=True)
class PricedLine:
    """One line of a price decision, as the caller states it."""

    line_no: int
    unit_price: Decimal
    moq: Decimal
    lead_time_days: int
    copper_basis: CopperBasis


def parse_finding_key(key: str) -> tuple[QuoteFindingCode, int | None]:
    """``code:line`` or ``code:-``, as `views.quote_finding_key` writes it."""
    code, _, line = key.partition(":")
    try:
        return QuoteFindingCode(code), (None if line == "-" else int(line))
    except ValueError:
        raise DomainError("not a finding key", details={"field": "finding_key"}) from None


@dataclass(frozen=True)
class QuoteQueries:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    service: QuotationService
    decisions: PendingDecisionsPort

    async def summaries(self, context: AccessContext) -> list[QuoteSummaryView]:
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_QUOTE)
        today = local_day(self.clock.now())
        async with self.uow(sales_scope(context)) as work:
            stored = await work.quotes.list_all()
        return [quote_summary(s.case, s.origin.assigned_to, today) for s in stored]

    async def get(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        incoterm: Incoterm | None = None,
        destination: str | None = None,
    ) -> QuoteCaseView:
        """The case; with the price evidence once Design has replied, for a
        caller who may see prices, as of today."""
        await self.gate.require(
            context, SalesScopes.CASE_READ, resource_type=_QUOTE, resource_id=str(case_id)
        )
        scope = sales_scope(context)
        async with self.uow(scope) as work:
            stored = await stored_quote(work, case_id)
        prices = self.gate.prices(context)
        today = local_day(self.clock.now())
        case = stored.case
        evidence = None
        if prices.amounts and case.design_reply is not None:
            evidence = await self.service.price_evidence(
                scope, case, as_of=today, incoterm=incoterm, destination=destination
            )
        decision = None
        if (waits_on := awaiting(case)) is not None:
            approval_id = await self.decisions.pending(
                context, subject_of(CaseKind.QUOTE, case.case_id)
            )
            if approval_id is not None:
                decision = PendingDecisionView(approval_id=approval_id, approval_type=waits_on)
        return quote_case(
            case,
            assigned_to=stored.origin.assigned_to,
            release_manifest_ref=stored.origin.release_manifest_ref,
            today=today,
            prices=prices,
            evidence_rows=evidence,
            decision=decision,
        )

    async def screening(self, context: AccessContext, as_of: date | None) -> list[ScreeningRow]:
        """WIV-03-023 step 12: codes quoted with no order in the 12 months."""
        await self.gate.require(context, SalesScopes.CASE_READ, resource_type=_QUOTE)
        day = as_of or local_day(self.clock.now())
        return list(await self.service.screening(sales_scope(context), day))


@dataclass(frozen=True)
class QuoteCommands:
    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    service: QuotationService
    catalog: SalesCatalogPort
    decisions: PendingDecisionsPort

    async def answer_finding(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        finding_key: str,
        *,
        case_version: int,
        quantity: Decimal | None = None,
        needed_by: date | None = None,
        customer_code: str | None = None,
        note: str | None = None,
    ) -> CaseChangeView:
        """Sales types what the request lacked (`rfq_incomplete`) or confirms
        the customer of a forwarded one (`customer_unknown`)."""
        code, line_no = parse_finding_key(finding_key)

        def step(case: QuoteCase, actor: QuoteActor, at: datetime) -> QuoteCase:
            if code is QuoteFindingCode.CUSTOMER_UNKNOWN:
                if customer_code is None:
                    raise DomainError("the customer is named", details={"field": "customer_code"})
                return case.confirm_customer(customer_code, by=actor.user_id, at=at)
            if code is QuoteFindingCode.RFQ_INCOMPLETE and line_no is not None:
                return case.complete_line(
                    line_no,
                    by=actor.user_id,
                    at=at,
                    quantity=quantity,
                    needed_by=needed_by,
                    note=note,
                )
            raise ConflictError(
                "only a request's own findings are answered by Sales",
                details={"case_id": str(case.case_id), "finding_key": finding_key},
            )

        return await self._decide(
            context,
            case_id,
            case_version,
            "quote.finding_answered",
            step,
            finding_key=finding_key,
        )

    async def ycbg(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        ycbg_no: str | None,
    ) -> CaseChangeView:
        """Step 2: the YCBG drafted; with its number, recorded as Bravo gave it."""

        def step(case: QuoteCase, actor: QuoteActor, at: datetime) -> QuoteCase:
            if ycbg_no is None:
                return case.draft_ycbg()
            drafted = case.draft_ycbg() if case.status is QuoteStatus.RECEIVED else case
            return drafted.record_ycbg(ycbg_no, by=actor.user_id, at=at)

        return await self._decide(
            context,
            case_id,
            case_version,
            "quote.ycbg_recorded" if ycbg_no else "quote.ycbg_drafted",
            step,
            field="ycbg_no" if ycbg_no else None,
        )

    async def design_sent(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """Step 3: Sales sent the request to Design."""
        return await self._decide(
            context,
            case_id,
            case_version,
            "quote.sent_to_design",
            lambda c, a, t: c.send_to_design(),
        )

    async def spec_discussion(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int, step: SpecStep
    ) -> CaseChangeView:
        """Step 6: discussing the spec with the customer, settled, or back to Design."""
        moves: Mapping[SpecStep, Callable[[QuoteCase], QuoteCase]] = {
            "start": QuoteCase.discuss_spec,
            "settle": QuoteCase.settle_spec,
            "ask_design_again": QuoteCase.send_to_design,
        }
        return await self._decide(
            context,
            case_id,
            case_version,
            f"quote.spec_{step}",
            lambda case, actor, at: moves[step](case),
        )

    async def price(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        lme_month: str | None,
        lines: Sequence[PricedLine],
        management_guidance: str | None,
    ) -> CaseChangeView:
        """Step 7: the caller's price. Decided by them, now, against the LME
        figure master data holds for the month they name."""
        await self._require(context, case_id, SalesScopes.QUOTE_PREPARE)
        now, scope = self.clock.now(), sales_scope(context)
        lme = None
        if lme_month is not None:
            lme = (await self.catalog.lme_for_month(scope, lme_month)).data
            if lme is None:
                raise ConflictError(
                    "no LME figure on record for the month", details={"lme_month": lme_month}
                )
        decision = decided(
            lambda: PricingDecision(
                decided_by=context.principal_id,
                decided_at=now,
                lme=lme,
                lines=tuple(
                    LinePrice(
                        line_no=line.line_no,
                        unit_price=line.unit_price,
                        moq=line.moq,
                        lead_time_days=line.lead_time_days,
                        copper_basis=line.copper_basis,
                    )
                    for line in lines
                ),
                management_guidance=management_guidance,
            )
        )
        async with self.uow(scope) as work:
            case = (await stored_quote(work, case_id)).case
            same_version(case_id, case.case_version, case_version)
            priced = await self.service.decide_price(scope, case, decision, by=context.principal_id)
            event = person_event("quote.priced", context, now)
            await save_quote(work, context, self.ids, case, priced, event)
            await work.commit()
        # Priced again while pending: the document the approver was asked
        # about is withdrawn, and so is the approval.
        await withdraw_if_left(self.decisions, context, case, priced)
        return quote_change(priced)

    async def sent(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """Step 10: Sales sent the approved quotation."""
        return await self._decide(
            context,
            case_id,
            case_version,
            "quote.sent",
            lambda case, actor, at: case.mark_sent(by=actor.user_id, at=at),
        )

    async def master_list(
        self, context: AccessContext, case_id: uuid.UUID, *, case_version: int
    ) -> CaseChangeView:
        """Step 11: Sales confirmed the master-list rows; they are written to
        the ledger, then the case records it."""
        await self._require(context, case_id, SalesScopes.QUOTE_PREPARE)
        now, scope = self.clock.now(), sales_scope(context)
        async with self.uow(scope) as work:
            case = (await stored_quote(work, case_id)).case
            same_version(case_id, case.case_version, case_version)
            recorded = await self.service.record_master_list(
                scope, case, by=context.principal_id, at=now
            )
            event = person_event("quote.master_list_recorded", context, now)
            await save_quote(work, context, self.ids, case, recorded, event)
            await work.commit()
        return quote_change(recorded)

    async def decline(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        *,
        case_version: int,
        reason: DeclineReason,
        note: str | None,
    ) -> CaseChangeView:
        """Step 5: Sales declines, at any step before the quotation is sent."""
        return await self._decide(
            context,
            case_id,
            case_version,
            "quote.declined",
            lambda case, actor, at: case.decline_request(
                by=actor.user_id, at=at, reason=reason, note=note
            ),
            reason_code=reason.value,
        )

    # ------------------------------------------------------------- helpers --

    async def _require(
        self, context: AccessContext, case_id: uuid.UUID, scope: SalesScopes
    ) -> None:
        await self.gate.require(context, scope, resource_type=_QUOTE, resource_id=str(case_id))

    async def _decide(
        self,
        context: AccessContext,
        case_id: uuid.UUID,
        case_version: int,
        action: str,
        step: Callable[[QuoteCase, QuoteActor, datetime], QuoteCase],
        *,
        finding_key: str | None = None,
        field: str | None = None,
        reason_code: str | None = None,
    ) -> CaseChangeView:
        await self._require(context, case_id, SalesScopes.QUOTE_PREPARE)
        actor, now = quote_actor(context, self.gate), self.clock.now()
        async with self.uow(sales_scope(context)) as work:
            case = (await stored_quote(work, case_id)).case
            same_version(case_id, case.case_version, case_version)
            after = decided(lambda: step(case, actor, now))
            event = person_event(
                action,
                context,
                now,
                finding_key=finding_key,
                field=field,
                reason_code=reason_code,
            )
            await save_quote(work, context, self.ids, case, after, event)
            await work.commit()
        await withdraw_if_left(self.decisions, context, case, after)
        return quote_change(after)
