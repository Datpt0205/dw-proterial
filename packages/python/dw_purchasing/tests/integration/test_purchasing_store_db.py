"""DW02 function 1 on PostgreSQL, as `dw_app` under RLS (migration 2d0c58dc3806).

The SQL store keeps what the in-memory one promises; each tenant and each
workspace sees only its own cases and mail outcomes, with no WHERE of its own
and none at all for a session that never scoped itself; an outcome is written
once and never rewritten; the catalog's CHECKs hold the domain's values; the
roles hold what they should and no platform role holds a `purchasing.*` scope;
and the service, end to end on the database, writes its audit row and reads a
tenant's own rules from the platform's override store.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from purchasing_harness import Tenancy
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from dw_kernel.errors import ConflictError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.adapters.persistence.rule_versions import SqlRuleVersionLookup
from dw_purchasing.adapters.mock.inbox import MockInbox
from dw_purchasing.adapters.persistence.store import SqlPurchasingStore
from dw_purchasing.adapters.policy_files import PolicyFiles, platform_rule_book
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.intake import PurchaseRequests, Worker
from dw_purchasing.application.ports import Disposition, MessageOutcome
from dw_purchasing.application.rules import PurchasingRulesService
from dw_purchasing.domain.automation import PurchasingModelStep
from dw_purchasing.domain.cases import (
    CaseStatus,
    PrSource,
    PurchaseCase,
)
from dw_purchasing.domain.requests import (
    PrLine,
    PurchaseRequest,
)
from dw_purchasing.testing.world import Authz, ScriptedModel, caller

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[5]
NOW = datetime(2026, 11, 2, 1, 0, tzinfo=UTC)
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]


def _case(*, source: PrSource = PrSource.FORM, ref: str | None = None) -> PurchaseCase:
    return PurchaseCase(
        case_id=uuid.uuid4(),
        case_version=1,
        status=CaseStatus.RECEIVED,
        source=source,
        source_ref=ref,
        request=PurchaseRequest(
            pr_no="PR-2611-020",
            department="Kho",
            requester="Trần Văn Kho",
            budget_code="CC-WH-01",
            currency="VND",
            lines=(PrLine(line_no=1, description="Pallet", quantity=Decimal(20), unit="cái"),),
        ),
        received_at=NOW,
        received_by=uuid.UUID(int=0xB0B),
        rules_ref="purchasing_rules@1.0.0",
    )


def _store(sessions: async_sessionmaker[AsyncSession]) -> SqlPurchasingStore:
    return SqlPurchasingStore(sessions, SqlAuditRepository, SqlApprovalRepository)


async def test_a_case_and_an_outcome_round_trip_in_their_own_workspace_only(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    store = _store(app_sessions)
    case = _case(source=PrSource.MAIL, ref="P01")
    outcome = MessageOutcome("P01", Disposition.OPENED, None, case.case_id, case.received_by, NOW)
    async with store(caller(tenancy.alpha)) as work:
        await work.cases.add(case)
        await work.outcomes.add(outcome)

    async with store(caller(tenancy.alpha)) as work:
        assert await work.cases.get(case.case_id) == case
        assert await work.outcomes.get("P01") == outcome
        assert list(await work.cases.page(limit=10, before=None)) == [case]
    for other in (tenancy.alpha_other, tenancy.beta):
        async with store(caller(other)) as work:
            assert await work.cases.get(case.case_id) is None
            assert await work.outcomes.all() == []
            assert await work.cases.page(limit=10, before=None) == []


async def test_every_field_of_a_case_survives_the_round_trip(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    """The body holds every field the columns do not: a field added to the
    case and not to the body would come back as its default (failure-modes
    #2), as `read_from` once did."""
    from dw_purchasing.domain.cases import ReadFrom, Review

    store = _store(app_sessions)
    case = _case(source=PrSource.MAIL, ref="P08").model_copy(
        update={
            "read_from": ReadFrom(attachment_id="scan-014", attachment="scan.pdf", scanned=True),
            "review": Review(asked_at=NOW),
        }
    )
    async with store(caller(tenancy.alpha)) as work:
        await work.cases.add(case)
    async with store(caller(tenancy.alpha)) as work:
        assert await work.cases.get(case.case_id) == case


async def test_a_session_that_never_scoped_itself_reads_nothing(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    async with _store(app_sessions)(caller(tenancy.alpha)) as work:
        await work.cases.add(_case())
    async with app_sessions() as session:
        for table in ("purchasing.cases", "purchasing.mail_outcomes"):
            count = (await session.execute(sa.text(f"SELECT count(*) FROM {table}"))).scalar()
            assert count == 0, table


async def test_a_mail_is_settled_once(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    store = _store(app_sessions)
    outcome = MessageOutcome(
        "P03", Disposition.TO_PERSON, "sender_not_internal", None, uuid.UUID(int=1), NOW
    )
    async with store(caller(tenancy.alpha)) as work:
        await work.outcomes.add(outcome)
    with pytest.raises(ConflictError):
        async with store(caller(tenancy.alpha)) as work:
            await work.outcomes.add(outcome)
    # Another workspace's mail with the same id is its own.
    async with store(caller(tenancy.alpha_other)) as work:
        await work.outcomes.add(outcome)


async def test_an_outcome_is_never_rewritten_nor_one_of_the_wrong_shape_written(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    store = _store(app_sessions)
    async with store(caller(tenancy.alpha)) as work:
        await work.outcomes.add(
            MessageOutcome(
                "P05", Disposition.TO_PERSON, "no_pr_number", None, uuid.UUID(int=1), NOW
            )
        )
    for statement in (
        "UPDATE purchasing.mail_outcomes SET reason = 'x'",
        "DELETE FROM purchasing.mail_outcomes",
    ):
        with pytest.raises(DBAPIError, match="permission denied"):
            async with store(caller(tenancy.alpha)) as work:
                await work.cases.get(uuid.uuid4())  # opens the scoped transaction
                await _execute(work, statement)
    # An opened mail names its case; one for a person gives its reason.
    with pytest.raises(DBAPIError, match="ck_mail_outcomes_shape"):
        async with store(caller(tenancy.alpha)) as work:
            await work.outcomes.add(
                MessageOutcome("P06", Disposition.OPENED, None, None, uuid.UUID(int=1), NOW)
            )
    # A supplier's mail is settled at the case it was handled at, without a
    # reason (ad62389cc25d).
    case = _case()
    async with store(caller(tenancy.alpha)) as work:
        await work.cases.add(case)
    settled = MessageOutcome("Q01", Disposition.SUPPLIER, None, case.case_id, case.received_by, NOW)
    async with store(caller(tenancy.alpha)) as work:
        await work.outcomes.add(settled)
    async with store(caller(tenancy.alpha)) as work:
        assert await work.outcomes.get("Q01") == settled
    for wrong in (
        MessageOutcome("Q02", Disposition.SUPPLIER, None, None, uuid.UUID(int=1), NOW),
        MessageOutcome("Q03", Disposition.SUPPLIER, "x", case.case_id, uuid.UUID(int=1), NOW),
    ):
        with pytest.raises(DBAPIError, match="ck_mail_outcomes_shape"):
            async with store(caller(tenancy.alpha)) as work:
                await work.outcomes.add(wrong)


async def _execute(work: object, statement: str) -> None:
    session = work.cases._session  # type: ignore[attr-defined]
    await session.execute(sa.text(statement))


async def test_the_catalogs_checks_hold_the_domains_values(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        rows = (
            await conn.execute(
                sa.text(
                    "SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint"
                    " WHERE connamespace = 'purchasing'::regnamespace"
                    " AND conname IN ('ck_cases_status', 'ck_cases_source',"
                    " 'ck_mail_outcomes_disposition')"
                )
            )
        ).all()
    found = {row.conname: set(re.findall(r"'([a-z_]+)'::text", row.definition)) for row in rows}
    assert found == {
        "ck_cases_status": {s.value for s in CaseStatus},
        "ck_cases_source": {s.value for s in PrSource},
        "ck_mail_outcomes_disposition": {d.value for d in Disposition},
    }


async def test_every_dw2_model_step_can_be_measured(migrator: AsyncEngine) -> None:
    """The platform's measurements table, shared with Sales, admits each DW2
    reading a switch waits on: a step it refused could never be attested,
    and its `ai_auto` would never take effect."""
    async with migrator.connect() as conn:
        definition = await conn.scalar(
            sa.text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint"
                " WHERE conname = 'ck_model_step_measurements_step'"
                " AND connamespace = 'platform'::regnamespace"
            )
        )
    admitted = set(re.findall(r"'([a-z_]+)'::text", str(definition)))
    assert {s.value for s in PurchasingModelStep} <= admitted


async def test_the_application_holds_the_verbs_each_table_needs(migrator: AsyncEngine) -> None:
    async with migrator.connect() as conn:
        held = {
            (row.tbl, row.verb)
            for row in await conn.execute(
                sa.text(
                    "SELECT c.relname AS tbl, v.verb FROM pg_class c"
                    " JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " CROSS JOIN unnest(ARRAY['SELECT','INSERT','UPDATE','DELETE']) AS v(verb)"
                    " WHERE n.nspname = 'purchasing' AND c.relkind IN ('r', 'p')"
                    " AND has_table_privilege('dw_app', c.oid, v.verb)"
                )
            )
        }
    assert {v for t, v in held if t == "cases"} == {"SELECT", "INSERT", "UPDATE", "DELETE"}
    assert {v for t, v in held if t == "mail_outcomes"} == {"SELECT", "INSERT"}


async def test_the_roles_hold_purchasing_scopes_and_no_platform_role_does(
    migrator: AsyncEngine,
) -> None:
    async with migrator.connect() as conn:
        roles = {
            row.key: set(row.scopes)
            for row in await conn.execute(sa.text("SELECT key, scopes FROM platform.roles"))
        }
    every = {s.value for s in PurchasingScopes}
    read = PurchasingScopes.REQUEST_READ.value
    assert roles["purchasing_buyer"] == {
        read,
        PurchasingScopes.REQUEST_INTAKE.value,
        PurchasingScopes.REQUEST_SUBMIT.value,
        PurchasingScopes.RFQ_PREPARE.value,
        PurchasingScopes.PO_PREPARE.value,
        PurchasingScopes.PO_DOWNLOAD.value,
    }
    assert roles["purchasing_viewer"] == {read}
    assert roles["purchasing_head"] == {
        read,
        PurchasingScopes.APPROVE_TIER1.value,
        PurchasingScopes.APPROVE_TIER2.value,
        PurchasingScopes.RULES_PROPOSE.value,
        PurchasingScopes.RULES_APPROVE.value,
    }
    # The person who configures DW2 proposes; the head decides (633993a6d8b4).
    assert roles["purchasing_configurer"] == {read, PurchasingScopes.RULES_PROPOSE.value}
    leaking = {k for k, s in roles.items() if not k.startswith("purchasing_") and s & every}
    assert leaking == set()
    async with migrator.connect() as conn:
        sets = {
            row.key: set(row.scopes)
            for row in await conn.execute(
                sa.text("SELECT key, scopes FROM platform.permission_sets")
            )
        }
    assert sets["purchasing_director_approver"] == {PurchasingScopes.APPROVE_TIER3.value}
    # What a tenant's admin grants beyond the roles (fcc0e57d0817).
    assert sets["purchasing_po_downloader"] == {PurchasingScopes.PO_DOWNLOAD.value}
    assert sets["purchasing_request_reader"] == {read}
    assert sets["purchasing_rules_approver"] == {PurchasingScopes.RULES_APPROVE.value}
    # Every scope a rule may stamp is held by someone the catalogue names.
    held = set().union(*roles.values(), *sets.values())
    assert every <= held


async def test_the_service_on_the_database_audits_and_reads_the_tenants_own_rules(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    files = PolicyFiles.load(REPO / "configs/policies")
    book = platform_rule_book(REPO / "configs/policies", SqlRuleVersionLookup(app_sessions))
    service = PurchaseRequests(
        uow=_store(app_sessions),
        gate=Gate(Authz()),
        rules=book,
        inbox=MockInbox.load(tenant_id=tenancy.alpha[0], workspace_id=tenancy.alpha[1]),
        model=ScriptedModel(ANSWERS),
        worker=Worker("purchasing-dw2", "1.0.0"),
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
    )
    me = caller(tenancy.alpha)
    opened = await service.read_mail(me, "P01")
    assert opened.disposition is Disposition.OPENED and opened.case_id is not None
    assert (await service.case(me, opened.case_id)).request.pr_no == "PR-2611-004"

    # The tenant's own version, applied by its head through the platform's
    # rule-version engine (`platform.rule_versions`): need-by required.
    document = {
        "version": "9.0.0",
        "pr_form": {
            "required": ["budget_code", "need_by"],
            "max_lines": 50,
            "currencies": ["VND"],
            "default_currency": "VND",
        },
        "internal_domains": ["seller.example"],
    }
    head = me.model_copy(
        update={
            "scopes": me.scopes
            | {PurchasingScopes.RULES_PROPOSE.value, PurchasingScopes.RULES_APPROVE.value}
        }
    )
    rules = PurchasingRulesService(
        uow=_store(app_sessions),
        gate=Gate(Authz()),
        book=book,
        clock=FixedClock(NOW),
        ids=Uuid4Generator(),
    )
    applied = await rules.propose(head, "purchasing_rules", document)
    assert (applied.status, applied.applied_directly) == ("approved", True)
    # Read under RLS: the other tenant's resolution never meets it.
    beta = (await book.resolve(caller(tenancy.beta))).version
    assert beta == files.current().version
    routed = await service.read_mail(me, "P02")
    # P02's one line names its date.
    assert routed.disposition is Disposition.OPENED and routed.case_id is not None
    stamped = (await service.case(me, routed.case_id)).rules_ref
    assert stamped == "purchasing_rules@9.0.0"

    async with app_sessions() as session, session.begin():
        await session.execute(
            sa.text(
                "SELECT set_config('app.tenant_id', :t, true),"
                " set_config('app.workspace_id', :w, true)"
            ),
            {"t": str(tenancy.alpha[0]), "w": str(tenancy.alpha[1])},
        )
        actions = (
            (
                await session.execute(
                    sa.text(
                        "SELECT action FROM platform.audit_events"
                        " WHERE resource_type = 'purchase_case' ORDER BY occurred_at"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert list(actions).count("purchasing.request.received") == 2


async def test_a_requesters_cases_are_narrowed_in_the_query(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    """`requested_by` is the body's, generated, and the page narrows by it
    in SQL; a requester's case that names nobody is refused by the table."""
    hoa, nam = uuid.uuid4(), uuid.uuid4()
    me = caller(tenancy.alpha)
    mine = _case(source=PrSource.REQUESTER).model_copy(update={"requested_by": hoa})
    theirs = _case(source=PrSource.REQUESTER).model_copy(update={"requested_by": nam})
    async with _store(app_sessions)(me) as work:
        await work.cases.add(mine)
        await work.cases.add(theirs)
        await work.cases.add(_case())
    async with _store(app_sessions)(me) as work:
        own = await work.cases.page(limit=50, before=None, requested_by=hoa)
        every = await work.cases.page(limit=50, before=None)
    assert [c.case_id for c in own] == [mine.case_id]
    assert own[0].requested_by == hoa and len(every) == 3
    with pytest.raises(DBAPIError, match="ck_cases_requester"):
        async with _store(app_sessions)(me) as work:
            await _execute(
                work,
                "UPDATE purchasing.cases SET body = body - 'requested_by'"
                f" WHERE id = '{mine.case_id}'",
            )


async def test_rows_past_their_tenants_term_are_deleted_one_workspace_at_a_time(
    app_sessions: async_sessionmaker[AsyncSession], tenancy: Tenancy
) -> None:
    """`purchasing.prune_expired_in`, as the worker's lane runs it as `dw_app`:
    one workspace's case received before its cutoff goes, with its mail
    outcome; a newer one stays; another tenant's old case is untouched; a
    NULL cutoff deletes nothing. The lane reads the term from the tenant's
    rules (the platform's ten years here)."""
    from datetime import timedelta

    from dw_purchasing.adapters.persistence.retention import SqlRetentionStore
    from dw_purchasing.application.retention import PurchasingRetention

    me, them = caller(tenancy.alpha), caller(tenancy.beta)
    old = _case(source=PrSource.MAIL, ref="OLD-1").model_copy(
        update={"received_at": NOW - timedelta(days=4000)}
    )
    new = _case()
    theirs = _case(source=PrSource.MAIL, ref="OLD-2").model_copy(
        update={"received_at": NOW - timedelta(days=4000)}
    )
    async with _store(app_sessions)(me) as work:
        await work.cases.add(old)
        await work.cases.add(new)
        await work.outcomes.add(
            MessageOutcome(
                message_id="OLD-1",
                disposition=Disposition.OPENED,
                reason=None,
                case_id=old.case_id,
                settled_by=uuid.UUID(int=0xB0B),
                settled_at=NOW - timedelta(days=4000),
            )
        )
    async with _store(app_sessions)(them) as work:
        await work.cases.add(theirs)
    store = SqlRetentionStore(app_sessions)
    assert {tenancy.alpha, tenancy.beta} <= set(await store.scopes())
    kept = await store.prune(
        tenancy.alpha,
        cases_before=None,
        outcomes_before=None,
        mail_before=None,
    )
    assert (kept.cases, kept.outcomes, kept.mail) == (0, 0, 0)
    book = platform_rule_book(REPO / "configs/policies", SqlRuleVersionLookup(app_sessions))
    lane = PurchasingRetention(
        store=_OnlyAlpha(store, tenancy.alpha), book=book, clock=FixedClock(NOW)
    )
    await lane.prune()
    async with _store(app_sessions)(me) as work:
        assert await work.cases.get(old.case_id) is None
        assert await work.cases.get(new.case_id) is not None
        assert await work.outcomes.get("OLD-1") is None
    async with _store(app_sessions)(them) as work:
        assert await work.cases.get(theirs.case_id) is not None


@dataclass(frozen=True)
class _OnlyAlpha:
    """The real store, its scope list cut to one workspace: the test's
    database holds other tests' tenants, which this run must not touch."""

    inner: Any
    scope: tuple[uuid.UUID, uuid.UUID]

    async def scopes(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        return [self.scope]

    async def prune(self, scope: Any, **cutoffs: Any) -> Any:
        return await self.inner.prune(scope, **cutoffs)
