"""A triage card on a routed message (`sales.messages.triage`) and the mail a
skill version was taught from (`sales.skill_replays.trigger`), migration
2c91d318f833, tickets 33 and 34, against a real database, as `dw_app`.

A card reads back as the domain wrote it, undecided and decided, under the
message's RLS only; the CHECK keeps one off a message on a case it did not
attach, and keeps it an object. A replay's taught mail reads back beside it,
and its CHECK keeps it an object.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sales_harness import T0, OrderRun, World
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_platform.adapters.persistence.repositories import SqlAuditRepository
from dw_platform.application.rule_versions import RuleVersion
from dw_platform.domain.approval import ApprovalRequest
from dw_platform.domain.audit import lane_audit_event
from dw_sales.adapters.persistence.skill_replays import SqlSkillReplays
from dw_sales.adapters.persistence.uow import SqlSalesUnitOfWorkFactory
from dw_sales.application.ports import SalesScope
from dw_sales.application.skills import (
    SKILLS_APPROVAL,
    SkillDocument,
    SkillReplay,
    SkillTrigger,
    TriggerReplay,
)
from dw_sales.domain.dispositions import (
    SALES_PIC_POOL,
    CaseKind,
    DispositionKind,
    MessageDisposition,
    RoutingReason,
)
from dw_sales.domain.message_intent import ResolvedReference
from dw_sales.domain.reply_intent import CaseReply
from dw_sales.domain.triage import CardVerdict, TriageCard, card_case, card_step

pytestmark = pytest.mark.integration

_AT = datetime.now(UTC).replace(microsecond=0)
AN_ID = uuid.UUID(int=0xA1)


def _card(case_id: uuid.UUID | None, number: str = "VLX-PO-2609-0118") -> TriageCard:
    references = (
        ()
        if case_id is None
        else (ResolvedReference(number=number, record="purchase_order", order_case_id=case_id),)
    )
    return TriageCard(
        prompt="sales.triage_card@1.0.0",
        model_profile="onprem",
        route="structured_extraction",
        rules="sales_order_rules@1.5.2",
        skill="sales_skill_mail_kinds@1.0.0",
        kind="reply_to_case",
        routed_as="reply_to_case",
        references=references,
        case_id=card_case(references),
        step=card_step("reply_to_case"),
    )


def _routed(message_id: str, card: TriageCard) -> MessageDisposition:
    return MessageDisposition(
        message_id=message_id,
        kind=DispositionKind.ROUTED_TO_SALES,
        reason=RoutingReason.OTHER,
        owner=SALES_PIC_POOL,
        customer_code="VLX",
        triage=card,
    )


async def test_a_card_reads_back_undecided_and_decided_in_its_scope_only(
    order_run: OrderRun, uow: SqlSalesUnitOfWorkFactory, world: World
) -> None:
    m01 = order_run.outcomes["M01"].disposition
    assert m01 is not None and m01.case_id is not None
    card = _card(m01.case_id)
    routed = _routed("R-CARD", card)
    async with uow(order_run.scope) as work:
        await work.messages.record(routed, T0)
        await work.commit()
    async with uow(order_run.scope) as work:
        assert await work.messages.get("R-CARD") == routed
    # Decided: attached to the card's case, the card kept with its decision.
    verdict = CardVerdict(
        decision="taken", step="reply_to_case", case_id=m01.case_id, by=AN_ID, at=_AT
    )
    attached = MessageDisposition(
        message_id="R-CARD",
        kind=DispositionKind.ATTACHED_TO_CASE,
        case_kind=CaseKind.ORDER,
        case_id=m01.case_id,
        customer_code="VLX",
        reply=CaseReply(linked_to="M01", picked_by=AN_ID),
        triage=card.model_copy(update={"decided": verdict}),
    )
    async with uow(order_run.scope) as work:
        await work.messages.record(attached, T0)
        await work.commit()
    async with uow(order_run.scope) as work:
        assert await work.messages.get("R-CARD") == attached
    async with uow(world.alpha_other) as work:
        assert await work.messages.get("R-CARD") is None


@pytest.mark.parametrize(
    ("disposition", "card"),
    [
        # A card on a message a flow put on a case.
        ("case_created", '{"kind": null}'),
        # Not an object.
        ("routed_to_sales", '["reply_to_case"]'),
    ],
)
async def test_the_check_keeps_a_card_an_object_on_a_routed_message(
    order_run: OrderRun,
    app_sessions: async_sessionmaker[AsyncSession],
    disposition: str,
    card: str,
) -> None:
    scope = order_run.scope
    on_case = disposition == "case_created"
    async with app_sessions() as session, session.begin():
        for key, value in (
            ("app.tenant_id", scope.tenant_id.value),
            ("app.workspace_id", scope.workspace_id.value),
        ):
            await session.execute(
                sa.text("SELECT set_config(:k, :v, true)"), {"k": key, "v": str(value)}
            )
        case_id = order_run.outcomes["M01"].disposition.case_id  # type: ignore[union-attr]
        with pytest.raises(DBAPIError, match="ck_messages_triage"):
            await session.execute(
                sa.text(
                    "INSERT INTO sales.messages (id, tenant_id, workspace_id, message_id,"
                    " disposition, order_case_id, routing_reason, owner, processed_at, triage)"
                    " VALUES (gen_random_uuid(), :t, :w, 'R-BAD-CARD', :d, :c, :r, :o, now(),"
                    " CAST(:card AS jsonb))"
                ),
                {
                    "t": scope.tenant_id.value,
                    "w": scope.workspace_id.value,
                    "d": disposition,
                    "c": case_id if on_case else None,
                    "r": None if on_case else "other",
                    "o": None if on_case else SALES_PIC_POOL,
                    "card": card,
                },
            )


async def _proposed(uow: SqlSalesUnitOfWorkFactory, scope: SalesScope) -> uuid.UUID:
    """A proposed version of the mail kinds, taught from a mail."""
    document = SkillDocument(
        policy_id="sales_skill_mail_kinds",
        policy_version="1.1.0",
        description="Classifying an email.",
        instructions="- kind: other\n  route: other\n  means: anything else",
        trigger=SkillTrigger(workspace_id=scope.workspace_id.value, message_id="M31"),
    )
    async with uow(scope) as work:
        approval_id = uuid.uuid4()
        await work.approvals.add(
            ApprovalRequest(
                id=approval_id,
                tenant_id=TenantId(scope.tenant_id.value),
                workspace_id=WorkspaceId(scope.workspace_id.value),
                approval_type=SKILLS_APPROVAL,
                requested_by=UserId(AN_ID),
                reason="ticket 34",
                payload={},
                required_scope="sales.rules.approve",
            )
        )
        version = RuleVersion(
            version_id=uuid.uuid4(),
            key=document.policy_id,
            version="1.1.0",
            document=document.model_dump(mode="json"),
            status="proposed",
            proposed_by=AN_ID,
            proposed_at=_AT,
            approval_id=approval_id,
        )
        await work.rule_versions.add(version)
        await work.commit()
    async with uow(scope) as work:
        stored = await work.rule_versions.get(version.version_id)
    assert stored is not None
    assert SkillDocument.model_validate(dict(stored.document)).trigger == document.trigger
    return version.version_id


async def test_a_replay_reads_back_the_taught_mail_both_ways(
    app_sessions: async_sessionmaker[AsyncSession],
    migrator: AsyncEngine,
    uow: SqlSalesUnitOfWorkFactory,
    world: World,
) -> None:
    version_id = await _proposed(uow, world.alpha)
    replay = SkillReplay(
        version_id=version_id,
        replayed_at=_AT,
        source="platform_examples",
        outcome="replayed",
        messages=92,
        right_with=92,
        right_without=91,
        unanswered=0,
        trigger=TriggerReplay(
            message_id="M31",
            found=True,
            with_kind="invoice_request",
            with_label="Khách hỏi hoá đơn",
            with_route="other",
            without_kind="other",
            without_route="other",
        ),
    )
    store = SqlSkillReplays(app_sessions, SqlAuditRepository)
    audit = lane_audit_event(
        lane="sales_skill_replay",
        event_id=uuid.uuid4(),
        tenant_id=world.alpha.tenant_id,
        workspace_id=world.alpha.workspace_id,
        action="sales.skills.replayed",
        resource_type="sales_skill_version",
        resource_id=str(version_id),
        occurred_at=_AT,
    )
    assert await store.store(world.alpha, replay, audit)
    assert await store.stored(world.alpha, [version_id]) == {version_id: replay}
    with pytest.raises(DBAPIError, match="ck_skill_replays_trigger"):
        async with migrator.begin() as conn:
            await conn.execute(
                sa.text(
                    "INSERT INTO sales.skill_replays (id, tenant_id, workspace_id, version_id,"
                    " replayed_at, source, outcome, messages, right_with, right_without,"
                    " unanswered, security_failed, trigger) VALUES (:id, :t, :w, :v, now(),"
                    " 'platform_examples', 'replayed', 1, 1, 1, 0, '[]'::jsonb, '[1]'::jsonb)"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": world.alpha.tenant_id.value,
                    "w": world.alpha.workspace_id.value,
                    "v": uuid.uuid4(),
                },
            )
