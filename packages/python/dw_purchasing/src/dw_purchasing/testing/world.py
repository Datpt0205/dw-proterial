"""DW2 assembled over in-memory adapters: the unit tests' and the eval smoke's.

`open_world` builds `PurchaseRequests` over the mock mailbox (bound to
`ALPHA`), the platform's rule files from the checkout, a tenant policy store
and a scripted model that answers each mail by the PR number in it, the way a
recorded live answer replays. Nothing here reaches a database or a model.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from pydantic import BaseModel

from dw_agent_runtime.contracts import RunContext
from dw_agent_runtime.model.interpretation import ModelUnavailableError, PromptRef
from dw_kernel.errors import PermissionDeniedError
from dw_kernel.ports import FixedClock, Uuid4Generator
from dw_platform.application.access_context import AccessContext
from dw_platform.application.rule_versions import RuleVersion
from dw_purchasing.adapters.bravo_file import BravoFile
from dw_purchasing.adapters.master_template import XlsxMasterTemplate
from dw_purchasing.adapters.mock.inbox import MockInbox
from dw_purchasing.adapters.mock.master_data import MockMasterData
from dw_purchasing.adapters.policy_files import platform_rule_book
from dw_purchasing.application.access import Gate, PurchasingScopes
from dw_purchasing.application.approvals import (
    RequestApprovals,
    RequestDecisions,
    RequestSettlement,
)
from dw_purchasing.application.assistant import AssistantService
from dw_purchasing.application.automation import Automation, AutomationChecks, SwitchesService
from dw_purchasing.application.follow_up import OrderFollowUp
from dw_purchasing.application.intake import PurchaseRequests, Worker
from dw_purchasing.application.master_data import MasterDataService
from dw_purchasing.application.orders import PurchaseOrders
from dw_purchasing.application.ports import Person
from dw_purchasing.application.reapprovals import (
    ReapprovalDecisions,
    Reapprovals,
    ReapprovalSettlement,
)
from dw_purchasing.application.requesters import RequesterDesk
from dw_purchasing.application.rfq_mail import RfqMailService
from dw_purchasing.application.rule_drafting import RuleWordsDesk
from dw_purchasing.application.rules import (
    PurchasingRulesService,
    RuleDecisions,
    RuleSettlement,
)
from dw_purchasing.application.services import PurchasingServices
from dw_purchasing.application.sourcing import SupplierSourcing
from dw_purchasing.testing.measurements import FixedModel, MemoryMeasurements
from dw_purchasing.testing.memory import (
    MemoryAssistantStore,
    MemoryMasterImports,
    MemoryRfqMails,
    MemoryStore,
)

ALPHA: Final = (uuid.UUID(int=0xA1), uuid.UUID(int=0xA2))
BETA: Final = (uuid.UUID(int=0xB1), uuid.UUID(int=0xB2))
BUYER: Final = uuid.UUID(int=0xB0B)
EVERY_SCOPE: Final = frozenset(s.value for s in PurchasingScopes)


def caller(
    scope: tuple[uuid.UUID, uuid.UUID] = ALPHA,
    *,
    scopes: frozenset[str] = EVERY_SCOPE,
    principal: uuid.UUID = BUYER,
) -> AccessContext:
    return AccessContext(
        tenant_id=scope[0],
        workspace_id=scope[1],
        principal_id=principal,
        roles=frozenset({"purchasing_buyer"}),
        scopes=scopes,
        plan_id="professional",
    )


class Authz:
    """The platform's scope check, as the verified context's scopes answer it."""

    async def require(
        self,
        *,
        context: AccessContext,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
    ) -> None:
        if action not in context.scopes:
            raise PermissionDeniedError(f"missing scope {action}", details={"scope": action})

    def is_allowed(self, context: AccessContext, action: str) -> bool:
        return action in context.scopes


# Who seeded a tenant's version in a test: fictional.
SEEDED_BY = uuid.UUID(int=0x5EED)


@dataclass
class _Seeding:
    """``documents[(tenant, key)] = document`` writes ``document`` as the
    tenant's version in force, as a stored row is: unvalidated, so a test can
    hold a version today's schema no longer reads."""

    store: MemoryStore

    def __setitem__(self, where: tuple[uuid.UUID, str], document: dict[str, Any]) -> None:
        from datetime import UTC, datetime

        tenant_id, key = where
        # Written as the engine writes every document (`by_alias`): the
        # version as `policy_version`, the key as `policy_id`.
        document = {"policy_id": key, **document}
        if "version" in document:
            document["policy_version"] = document.pop("version")
        held = self.store.versions.setdefault(tenant_id, {})
        for version_id, before in list(held.items()):
            if before.key == key and before.status == "approved":
                held[version_id] = before.model_copy(update={"status": "superseded"})
        at = datetime(2026, 10, 1, tzinfo=UTC)
        version_id = uuid.uuid4()
        held[version_id] = RuleVersion(
            version_id=version_id,
            key=key,
            version=str(document["policy_version"]),
            document=document,
            status="approved",
            proposed_by=SEEDED_BY,
            proposed_at=at,
            decided_by=SEEDED_BY,
            decided_at=at,
            applied_directly=True,
        )


@dataclass
class TenantPolicies:
    """A tenant's own rule versions, seeded into the store's (`_Seeding`)."""

    store: MemoryStore

    @property
    def documents(self) -> _Seeding:
        return _Seeding(self.store)


@dataclass
class RecordedNotices:
    """Implements `NoticesPort`: every notice kept as (key, recipients' scopes,
    people, excluded, title), once per key, as the platform's inbox holds it."""

    told: dict[str, tuple[frozenset[str], tuple[uuid.UUID, ...], tuple[uuid.UUID, ...], str]] = (
        field(default_factory=dict)
    )

    async def tell(
        self,
        context: AccessContext,
        *,
        scopes: frozenset[str],
        people: Sequence[uuid.UUID] = (),
        excluding: Sequence[uuid.UUID] = (),
        source_key: str,
        title: str,
        body: str,
        link: str | None,
    ) -> None:
        self.told.setdefault(source_key, (scopes, tuple(people), tuple(excluding), title))


@dataclass
class Directory:
    """`PeoplePort` over a dict: who each member is, as a directory says."""

    people: dict[uuid.UUID, Person] = field(default_factory=dict)

    async def person(self, context: AccessContext, user_id: uuid.UUID) -> Person | None:
        return self.people.get(user_id)


@dataclass
class ScriptedModel:
    """`InterpretationPort` answering by the first key found in any input
    (the mail, or the file beside it); ``failure`` raised instead when set.
    Every call is kept."""

    answers: Mapping[str, Mapping[str, Any]]
    failure: Exception | None = None
    calls: list[tuple[PromptRef, Mapping[str, str], RunContext]] = field(default_factory=list)
    # Answers for one schema by its name (an RFQ's wording, a supplier's
    # offer), where the keys could meet another schema's.
    by_schema: dict[str, Mapping[str, Mapping[str, Any]]] = field(default_factory=dict)
    model_profile: str = "onprem"
    route: str = "structured_extraction"
    max_input_tokens: int = 6000

    async def interpret[OutputT: BaseModel](
        self,
        prompt: PromptRef,
        inputs: Mapping[str, str],
        schema: type[OutputT],
        *,
        run: RunContext,
        max_output_tokens: int,
    ) -> OutputT:
        self.calls.append((prompt, inputs, run))
        if self.failure is not None:
            raise self.failure
        text = "\n".join(inputs.values())
        for key, answer in self.by_schema.get(schema.__name__, self.answers).items():
            if key in text:
                return schema.model_validate(answer)
        raise ModelUnavailableError("no scripted answer")


def services_of(world: World) -> PurchasingServices:
    """The bundle the router mounts, over ``world``."""
    return PurchasingServices(
        requests=world.service,
        approvals=world.approvals,
        sourcing=world.sourcing,
        orders=world.orders,
        rules=world.rules,
        switches=world.switches,
        requester=world.requester,
        words=world.words,
        master_data=world.master_data,
        rfq_mails=world.rfq_mails,
        follow_up=world.follow_up,
        assistant=world.assistant,
    )


@dataclass
class World:
    service: PurchaseRequests
    store: MemoryStore
    model: ScriptedModel
    tenant_policies: TenantPolicies
    clock: FixedClock
    approvals: RequestApprovals
    decisions: RequestDecisions
    settlement: RequestSettlement
    sourcing: SupplierSourcing
    orders: PurchaseOrders
    rules: PurchasingRulesService
    rule_decisions: RuleDecisions
    rule_settlement: RuleSettlement
    switches: SwitchesService
    measurements: MemoryMeasurements
    requester: RequesterDesk
    people: Directory
    reapproval_decisions: ReapprovalDecisions
    reapproval_settlement: ReapprovalSettlement
    words: RuleWordsDesk
    master_data: MasterDataService
    master_imports: MemoryMasterImports
    rfq_mails: RfqMailService
    rfq_mail_rows: MemoryRfqMails
    follow_up: OrderFollowUp
    assistant: AssistantService


def open_world(
    repo: Path, answers: Mapping[str, Mapping[str, Any]], *, with_model: bool = True
) -> World:
    from datetime import UTC, datetime

    store = MemoryStore()
    measurements = MemoryMeasurements()
    people = Directory()
    model = ScriptedModel(answers)
    policies = TenantPolicies(store)
    clock = FixedClock(datetime(2026, 11, 2, 7, 0, tzinfo=UTC))
    book = platform_rule_book(repo / "configs" / "policies", store)
    automation = Automation(measurements, FixedModel())
    checks = AutomationChecks(automation, book)
    ids = Uuid4Generator()
    service = PurchaseRequests(
        uow=store,
        gate=Gate(Authz()),
        rules=book,
        inbox=MockInbox.load(tenant_id=ALPHA[0], workspace_id=ALPHA[1]),
        model=model if with_model else None,
        worker=Worker("purchasing-dw2", "1.0.0"),
        clock=clock,
        ids=ids,
    )
    master = MockMasterData.load(tenant_id=ALPHA[0], workspace_id=ALPHA[1])
    approvals = RequestApprovals(
        uow=store, gate=Gate(Authz()), rules=book, master=master, clock=clock, ids=ids
    )
    sourcing = SupplierSourcing(
        uow=store,
        gate=Gate(Authz()),
        rules=book,
        master=master,
        inbox=service.inbox,
        model=model if with_model else None,
        worker=Worker("purchasing-dw2", "1.0.0"),
        clock=clock,
        ids=ids,
        reapprovals=Reapprovals(
            model if with_model else None, Worker("purchasing-dw2", "1.0.0"), clock, ids
        ),
    )
    rules = PurchasingRulesService(
        uow=store, gate=Gate(Authz()), book=book, clock=clock, ids=ids, checks=checks
    )
    master_imports = MemoryMasterImports()
    rfq_mail_rows = MemoryRfqMails()
    follow_up = OrderFollowUp(
        uow=store,
        gate=Gate(Authz()),
        master=master,
        inbox=service.inbox,
        model=model if with_model else None,
        worker=Worker("purchasing-dw2", "1.0.0"),
        clock=clock,
        ids=ids,
    )
    return World(
        service,
        store,
        model,
        policies,
        clock,
        approvals,
        RequestDecisions(store),
        RequestSettlement(store, clock, ids),
        sourcing,
        PurchaseOrders(
            uow=store,
            gate=Gate(Authz()),
            rules=book,
            master=master,
            spreadsheet=BravoFile(),
            clock=clock,
            ids=ids,
        ),
        rules,
        RuleDecisions(store, book, checks),
        RuleSettlement(store, book, clock, ids, checks),
        SwitchesService(Gate(Authz()), book, automation),
        measurements,
        RequesterDesk(
            uow=store,
            gate=Gate(Authz()),
            rules=book,
            people=people,
            model=model if with_model else None,
            worker=Worker("purchasing-dw2", "1.0.0"),
            clock=clock,
            ids=ids,
        ),
        people,
        ReapprovalDecisions(store),
        ReapprovalSettlement(store, clock, ids),
        RuleWordsDesk(
            Gate(Authz()),
            book,
            model if with_model else None,
            Worker("purchasing-dw2", "1.0.0"),
            ids,
        ),
        MasterDataService(
            gate=Gate(Authz()),
            imports=master_imports,
            rules=rules,
            book=book,
            template=XlsxMasterTemplate(),
            clock=clock,
            ids=ids,
        ),
        master_imports,
        RfqMailService(
            uow=store,
            gate=Gate(Authz()),
            mails=rfq_mail_rows,
            master=master,
            people=people,
            clock=clock,
            ids=ids,
            enabled=True,
        ),
        rfq_mail_rows,
        follow_up,
        AssistantService(
            store=MemoryAssistantStore(),
            gate=Gate(Authz()),
            requests=service,
            follow_up=follow_up,
            model=model if with_model else None,
            worker=Worker("purchasing-dw2", "1.0.0"),
            clock=clock,
            ids=ids,
        ),
    )
