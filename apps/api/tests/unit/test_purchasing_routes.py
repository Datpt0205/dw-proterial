"""`/api/v1/purchasing/*` over the real app and scope check, the store and
the model in memory (`dw_purchasing.testing.world`).

What the routes own: every one needs a verified caller, a scope is refused
before anything is read or written, the tenant comes from the context and a
body naming one is refused, and an unconfigured source answers 503.
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from test_support_endpoint import PRINCIPAL, SECRET, FakeLookup, FakeRepo, NoScopes

from dw_api.bootstrap import ApiContainer
from dw_api.health import CheckState, HealthService
from dw_api.main import create_app
from dw_api.settings import ApiSettings
from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.identity.dev_token import DevTokenVerifier
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.application.entitlement import DEFAULT_PLANS, PlanEntitlementService
from dw_platform.application.identity import DbAccessContextFactory
from dw_platform.application.support_access import SupportGrantService, SupportScopeCatalog
from dw_purchasing.adapters.policy_files import PolicyFiles
from dw_purchasing.application.access import Gate
from dw_purchasing.application.services import PurchasingServices
from dw_purchasing.domain.requests import PurchaseRequest
from dw_purchasing.presentation.routes import PurchasingMount
from dw_purchasing.testing.world import ALPHA, EVERY_SCOPE, World, open_world
from dw_purchasing.testing.world import caller as world_caller

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[4]
# The rules a case is stamped with: the newest the checkout ships.
CURRENT = PolicyFiles.load(REPO / "configs/policies").current().ref
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]
FORM: dict[str, Any] = {
    "pr_no": "PR-2611-020",
    "department": "Kho",
    "requester": "Trần Văn Kho",
    "budget_code": "CC-WH-01",
    "currency": "VND",
    "lines": [{"line_no": 1, "description": "Pallet nhựa", "quantity": "20", "unit": "cái"}],
}


def _world() -> World:
    world = open_world(REPO, ANSWERS)
    # The platform's own scope check, as the app runs it.
    world.service = dataclasses.replace(world.service, gate=Gate(ScopeAuthorizationService()))
    return world


def _container(scopes: frozenset[str], mount: PurchasingMount | None) -> ApiContainer:
    async def ok() -> CheckState:
        return "ok"

    catalog = SupportScopeCatalog()
    catalog.freeze()
    return ApiContainer(
        settings=ApiSettings(profile="test", dev_secret=SECRET),
        engine=None,
        health_service=HealthService(probes={"database": ok}),
        token_verifier=DevTokenVerifier(SECRET),
        access_context_factory=DbAccessContextFactory(FakeLookup(scopes, frozenset())),
        identity_bootstrap=None,
        uow_factory=None,
        authorization=ScopeAuthorizationService(),
        entitlement=PlanEntitlementService(DEFAULT_PLANS),
        support_catalog=catalog,
        support_grants=SupportGrantService(
            repo=FakeRepo(),
            member_scopes=NoScopes(),
            catalog=catalog,
            clock=SystemClock(),
            ids=Uuid4Generator(),
        ),
        purchasing=mount,
    )


async def _call(
    container: ApiContainer,
    method: str,
    path: str,
    body: Any = None,
    *,
    signed_in: bool = True,
    tenant: tuple[uuid.UUID, uuid.UUID] = ALPHA,
) -> httpx.Response:
    headers = {"X-Tenant-Id": str(tenant[0]), "X-Workspace-Id": str(tenant[1])}
    if signed_in:
        token = DevTokenVerifier(SECRET).issue("dev|buyer", email="buyer@example.test")
        headers["Authorization"] = f"Bearer {token}"
    app = create_app(container)
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.request(
                method, f"/api/v1/purchasing{path}", json=body, headers=headers
            )


def _mounted(world: World) -> PurchasingMount:
    return PurchasingMount(
        services=PurchasingServices(
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
    )


async def test_a_buyer_submits_a_form_reads_it_back_and_has_a_mail_read() -> None:
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))

    created = await _call(container, "POST", "/requests", FORM)
    assert created.status_code == 201, created.text
    case_id = created.json()["case_id"]
    listed = await _call(container, "GET", "/requests")
    assert [c["case_id"] for c in listed.json()["items"]] == [case_id]
    detail = await _call(container, "GET", f"/requests/{case_id}")
    assert detail.json()["rules_ref"] == CURRENT

    read = await _call(container, "POST", "/mail/P01/read")
    assert read.status_code == 200 and read.json()["disposition"] == "opened"
    mail = await _call(container, "GET", "/mail")
    assert [m["message_id"] for m in mail.json()][:2] == ["P01", "P02"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "/requests", None),
        ("GET", f"/requests/{uuid.uuid4()}", None),
        ("POST", "/requests", FORM),
        ("GET", "/mail", None),
        ("GET", "/suppliers", None),
        (
            "POST",
            f"/requests/{uuid.uuid4()}/rfq/KIMURA",
            {"case_version": 1, "subject": "s", "body": "b"},
        ),
        ("POST", "/mail/P01/read", None),
        ("GET", f"/requests/{uuid.uuid4()}/check", None),
        ("POST", f"/requests/{uuid.uuid4()}/review", {"case_version": 1}),
        ("POST", f"/requests/{uuid.uuid4()}/submit", {"case_version": 1}),
        ("POST", f"/requests/{uuid.uuid4()}/rfq", {"case_version": 1}),
        ("POST", f"/requests/{uuid.uuid4()}/offers/from-mail/Q01", {"case_version": 1}),
        ("GET", f"/requests/{uuid.uuid4()}/comparison", None),
        ("POST", f"/requests/{uuid.uuid4()}/po", {"case_version": 1}),
        ("GET", f"/requests/{uuid.uuid4()}/po/bravo.xlsx", None),
        ("GET", "/rules", None),
        ("GET", "/automation", None),
        ("POST", "/rules/purchasing_rules/words", {"request": "hỏi giá tối đa 4 nhà cung cấp"}),
        ("POST", "/requests/mine/draft", {"words": "Tôi cần mua 10 hộp găng tay"}),
        (
            "POST",
            "/requests/mine",
            {"currency": "VND", "lines": FORM["lines"], "budget_code": "CC-1"},
        ),
        ("GET", "/rules/purchasing_rules/schema", None),
        ("POST", "/rules/purchasing_rules/versions", {"document": {"policy_version": "9.0.0"}}),
        (
            "POST",
            f"/requests/{uuid.uuid4()}/selection",
            {"case_version": 1, "choices": [{"line_no": 1, "supplier_code": "KIMURA"}]},
        ),
        (
            "POST",
            f"/requests/{uuid.uuid4()}/offers",
            {
                "case_version": 1,
                "offer": {
                    "supplier_code": "KIMURA",
                    "line_no": 1,
                    "unit_price": "1",
                    "currency": "VND",
                    "lead_time_days": 1,
                },
            },
        ),
    ],
)
async def test_every_route_refuses_a_caller_without_its_scope_and_touches_nothing(
    method: str, path: str, body: Any
) -> None:
    world = _world()
    container = _container(frozenset({"sales.case.read"}), _mounted(world))

    response = await _call(container, method, path, body)
    assert response.status_code == 403, response.text
    unsigned = await _call(container, method, path, body, signed_in=False)
    assert unsigned.status_code == 401
    assert world.store.scopes == {} and world.model.calls == []
    assert world.store.versions == {}


async def test_a_heads_rules_apply_and_the_answer_holds_no_document() -> None:
    """What the idempotency store keeps of a proposal is ids and its status:
    the document holds the company's limits."""
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    listed = await _call(container, "GET", "/rules")
    assert listed.status_code == 200, listed.text
    document = listed.json()["keys"][0]["document"]
    document["policy_version"] = "9.0.0"
    document["pr_form"]["max_lines"] = 7
    proposed = await _call(
        container, "POST", "/rules/purchasing_rules/versions", {"document": document}
    )
    assert proposed.status_code == 200, proposed.text
    assert set(proposed.json()) == {
        "version_id",
        "version",
        "status",
        "approval_id",
        "applied_directly",
    }
    assert proposed.json()["status"] == "approved"
    again = await _call(container, "GET", "/rules")
    assert again.json()["keys"][0]["ref"] == "purchasing_rules@9.0.0"
    unknown = await _call(container, "GET", "/rules/sales_order_rules/schema")
    assert unknown.status_code == 404
    switches = await _call(container, "GET", "/automation")
    assert switches.status_code == 200, switches.text
    drafting = next(s for s in switches.json()["steps"] if s["step"] == "pr_drafting")
    assert (drafting["level"], drafting["why"]) == ("ai_review", "not_measured")


async def test_a_body_naming_a_tenant_is_refused() -> None:
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    response = await _call(container, "POST", "/requests", {**FORM, "tenant_id": str(ALPHA[0])})
    assert response.status_code == 422
    assert world.store.scopes == {}


async def test_an_incomplete_form_is_refused_naming_what_the_rules_require() -> None:
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    response = await _call(container, "POST", "/requests", {**FORM, "budget_code": None})
    assert response.status_code == 422
    assert response.json()["details"]["refusals"] == "missing:budget_code"


async def test_another_tenant_finds_neither_the_case_nor_the_mail() -> None:
    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    case_id = (await _call(container, "POST", "/requests", FORM)).json()["case_id"]
    other = (uuid.UUID(int=0xB1), uuid.UUID(int=0xB2))

    assert (await _call(container, "GET", f"/requests/{case_id}", tenant=other)).status_code == 404
    assert (await _call(container, "POST", "/mail/P01/read", tenant=other)).status_code == 404
    assert (await _call(container, "GET", "/requests", tenant=other)).json()["items"] == []


async def test_without_a_data_source_a_caller_is_told_so_and_a_stranger_learns_nothing() -> None:
    container = _container(EVERY_SCOPE, PurchasingMount(services=None))
    assert (await _call(container, "GET", "/requests")).status_code == 503
    assert (await _call(container, "GET", "/requests", signed_in=False)).status_code == 401


def test_every_route_checks_its_scope_before_its_body_or_idempotency_key() -> None:
    """The service checks again, so a missing route guard answers 403 all the
    same; what the guard adds is refusing before the `Idempotency-Key` is
    claimed, which only its presence on the route shows."""
    from fastapi.routing import APIRoute

    from dw_purchasing.presentation.routes import build_router

    router = build_router(None, access_context=lambda: None, idempotency=lambda: None)
    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    assert len(routes) == 42
    assert all(route.dependencies for route in routes), [
        route.path for route in routes if not route.dependencies
    ]


def test_the_composition_root_makes_purchasing_approvals_strict_and_guarded() -> None:
    """Whether or not the demo's data source is wired: an approval opened
    earlier is never decided by its maker, without a reason, or unchecked."""
    from dw_agent_runtime.approval_flow import ApproveAndResumeService
    from dw_api.bootstrap.wiring import build_purchasing_mount
    from dw_purchasing.application.approvals import APPROVAL_PREFIX, RequestDecisions
    from dw_purchasing.application.reapprovals import ReapprovalDecisions
    from dw_purchasing.application.rules import RuleDecisions

    flow = ApproveAndResumeService(
        uow_factory=None,  # type: ignore[arg-type]
        runner=None,  # type: ignore[arg-type]
        run_store=None,  # type: ignore[arg-type]
        clock=SystemClock(),
        id_generator=Uuid4Generator(),
    )
    mount = build_purchasing_mount(
        ApiSettings(profile="test", dev_secret=SECRET),
        session_factory=None,  # type: ignore[arg-type]
        clock=SystemClock(),
        ids=Uuid4Generator(),
        authorization=ScopeAuthorizationService(),
        approval_flow=flow,
        model=None,
    )
    assert flow.is_strict("purchasing.request") and flow.is_strict("purchasing.rules")
    assert isinstance(flow.decision_guards[APPROVAL_PREFIX], RequestDecisions)
    # A rules approval is checked by the rule engine's guard, the longer prefix,
    # and a choice past the tier by its own.
    assert isinstance(flow.decision_guards["purchasing.rules"], RuleDecisions)
    assert isinstance(flow.decision_guards["purchasing.reapproval"], ReapprovalDecisions)
    assert flow.is_strict("purchasing.reapproval")
    assert isinstance(mount, PurchasingMount)


def _mount(settings: ApiSettings) -> PurchasingMount:
    from dw_agent_runtime.approval_flow import ApproveAndResumeService
    from dw_api.bootstrap.wiring import build_purchasing_mount

    flow = ApproveAndResumeService(
        uow_factory=None,  # type: ignore[arg-type]
        runner=None,  # type: ignore[arg-type]
        run_store=None,  # type: ignore[arg-type]
        clock=SystemClock(),
        id_generator=Uuid4Generator(),
    )
    mount = build_purchasing_mount(
        settings,
        session_factory=None,  # type: ignore[arg-type]
        clock=SystemClock(),
        ids=Uuid4Generator(),
        authorization=ScopeAuthorizationService(),
        approval_flow=flow,
        model=None,
    )
    assert isinstance(mount, PurchasingMount)
    return mount


_DEMO = {"sales_demo_tenant_id": str(ALPHA[0]), "sales_demo_workspace_id": str(ALPHA[1])}


@pytest.mark.parametrize("profile", ["uat", "production"])
def test_a_deployed_dw2_refuses_the_mock_mailbox(profile: str) -> None:
    settings = ApiSettings(profile=profile, purchasing_mailbox="mock", **_DEMO)  # type: ignore[arg-type]
    assert _mount(settings).services is None


@pytest.mark.parametrize("profile", ["uat", "production"])
def test_a_deployed_dw2_reads_stored_mail_and_only_the_tenants_own_master_data(
    profile: str,
) -> None:
    """Where deployed, every check reads the lists a tenant loaded (or the
    platform's empty ones), never the demo's fictional lists."""
    from dw_purchasing.adapters.master_data import RuleMasterData

    settings = ApiSettings(profile=profile, purchasing_mailbox="stored", **_DEMO)  # type: ignore[arg-type]
    services = _mount(settings).services
    assert services is not None
    for master in (services.approvals.master, services.orders.master, services.sourcing.master):
        assert type(master) is RuleMasterData


def test_the_stored_mailbox_is_what_every_service_reads_when_named() -> None:
    from dw_purchasing.adapters.mock.inbox import MockInbox
    from dw_purchasing.adapters.persistence.mailbox import SqlPurchasingMailbox

    stored = _mount(
        ApiSettings(profile="test", dev_secret=SECRET, purchasing_mailbox="stored", **_DEMO)  # type: ignore[arg-type]
    ).services
    mock = _mount(ApiSettings(profile="test", dev_secret=SECRET, **_DEMO)).services  # type: ignore[arg-type]
    assert stored is not None and mock is not None
    assert isinstance(stored.requests.inbox, SqlPurchasingMailbox)
    assert stored.sourcing.inbox is stored.requests.inbox
    assert isinstance(mock.requests.inbox, MockInbox)
    # Not deployed: the demo's lists stand in until a tenant loads its own.
    from dw_purchasing.adapters.master_data import DemoMasterData

    assert isinstance(stored.approvals.master, DemoMasterData)


async def test_the_bravo_file_downloads_as_a_workbook_named_for_the_request() -> None:
    from datetime import UTC, datetime

    from dw_purchasing.domain.sourcing import Choice
    from dw_purchasing.testing.world import caller

    sourcing = json.loads(
        (REPO / "evals/fixtures/cases/purchasing_sourcing.json").read_text(encoding="utf-8")
    )
    world = _world()
    world.model.by_schema = {
        "ModelOffer": sourcing["answers"],
        "RfqWording": {"PR-2611-004": sourcing["rfq_words"]["good"]},
    }
    me = caller()
    case_id = (await world.service.read_mail(me, "P01")).case_id
    assert case_id is not None
    await world.approvals.submit(me, case_id, case_version=1)
    sent = await world.service.case(me, case_id)
    assert sent.approval is not None
    world.store.decide(
        sent.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=uuid.UUID(int=0x4EAD),
        at=datetime(2026, 11, 2, tzinfo=UTC),
    )
    await world.settlement.settle(
        sent.approval.approval_id, caller(principal=uuid.UUID(int=0x4EAD))
    )
    await world.sourcing.draft_rfq(me, case_id, case_version=3)
    for message_id in ("Q01", "Q02", "Q03"):
        version = (await world.service.case(me, case_id)).case_version
        await world.sourcing.read_offer_mail(me, case_id, message_id, case_version=version)
    choices = [
        Choice(line_no=n, supplier_code=s) for n, s in ((1, "KIMURA"), (2, "BAOHO"), (3, "ANPHAT"))
    ]
    version = (await world.service.case(me, case_id)).case_version
    await world.sourcing.select(me, case_id, choices, case_version=version)
    container = _container(EVERY_SCOPE, _mounted(world))
    drafted = await _call(
        container, "POST", f"/requests/{case_id}/po", {"case_version": version + 1}
    )
    assert drafted.status_code == 200, drafted.text

    response = await _call(container, "GET", f"/requests/{case_id}/po/bravo.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert (
        response.headers["content-disposition"]
        == 'attachment; filename="bravo-po-PR-2611-004.xlsx"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.content[:2] == b"PK"


async def test_a_requester_writes_their_request_and_finds_only_theirs() -> None:
    """The requester's two routes, and the reads narrowed to what they wrote:
    the buyer's form and the mailbox stay the buyer's."""
    from test_support_endpoint import PRINCIPAL

    from dw_purchasing.application.ports import Person

    world = _world()
    world.people.people[PRINCIPAL] = Person("Lê Thị Hoa", "Bảo trì")
    own = frozenset({"purchasing.request.create", "purchasing.request.read_own"})
    buyer_case = await world.service.submit_form(
        world_caller(), PurchaseRequest.model_validate(FORM)
    )
    container = _container(own, _mounted(world))
    sent = await _call(
        container,
        "POST",
        "/requests/mine",
        {"currency": "VND", "lines": FORM["lines"], "budget_code": "CC-1"},
    )
    assert sent.status_code == 201, sent.text
    listed = await _call(container, "GET", "/requests")
    assert [c["case_id"] for c in listed.json()["items"]] == [sent.json()["case_id"]]
    hidden = await _call(container, "GET", f"/requests/{buyer_case.case_id}")
    assert hidden.status_code == 404
    for method, path, body in (("POST", "/requests", FORM), ("GET", "/mail", None)):
        refused = await _call(container, method, path, body)
        assert refused.status_code == 403, path


async def test_an_approver_of_the_last_tier_reads_the_case_waiting_on_them_only() -> None:
    """The director holds `purchasing.approve.tier3` and nothing else of DW2's:
    the case route answers the one request whose approval stamped that scope,
    404 for any other, and the list stays refused."""
    world = _world()
    waiting = await world.service.submit_form(world_caller(), PurchaseRequest.model_validate(FORM))
    await world.approvals.submit(world_caller(), waiting.case_id, case_version=1)
    stamped = (await world.service.case(world_caller(), waiting.case_id)).approval
    assert stamped is not None
    other = await world.service.submit_form(
        world_caller(), PurchaseRequest.model_validate({**FORM, "pr_no": "PR-OTHER-1"})
    )
    container = _container(frozenset({stamped.required_scope}), _mounted(world))
    read = await _call(container, "GET", f"/requests/{waiting.case_id}")
    assert read.status_code == 200, read.text
    assert (await _call(container, "GET", f"/requests/{other.case_id}")).status_code == 404
    assert (await _call(container, "GET", "/requests")).status_code == 403


# ------------------------------------------------------------- master data --

_WORKBOOK = b"PK\x03\x04 bytes the API keeps and never opens"


async def test_the_master_data_template_downloads_as_a_workbook() -> None:
    container = _container(EVERY_SCOPE, _mounted(_world()))
    response = await _call(container, "GET", "/master-data/template.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert response.content.startswith(b"PK")


async def test_a_workbook_is_uploaded_as_base64_and_answers_queued() -> None:
    import base64

    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    body = {"file_name": "lists.xlsx", "content_b64": base64.b64encode(_WORKBOOK).decode()}
    response = await _call(container, "POST", "/master-data/imports", body)

    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
    (record, content), *_ = world.master_imports.rows[ALPHA].values()
    assert content == _WORKBOOK
    page = await _call(container, "GET", "/master-data")
    assert page.json()["imports"][0]["import_id"] == str(record.import_id)


async def test_who_may_not_configure_dw2_uploads_nothing() -> None:
    import base64

    world = _world()
    container = _container(
        frozenset({"purchasing.request.read", "purchasing.rules.approve"}), _mounted(world)
    )
    body = {"file_name": "lists.xlsx", "content_b64": base64.b64encode(_WORKBOOK).decode()}
    response = await _call(container, "POST", "/master-data/imports", body)

    assert response.status_code == 403
    assert all(not held for held in world.master_imports.rows.values())
    # Who decides reads the page all the same.
    assert (await _call(container, "GET", "/master-data")).status_code == 200


async def test_another_tenants_import_answers_404() -> None:
    import base64

    world = _world()
    container = _container(EVERY_SCOPE, _mounted(world))
    body = {"file_name": "lists.xlsx", "content_b64": base64.b64encode(_WORKBOOK).decode()}
    import_id = (await _call(container, "POST", "/master-data/imports", body)).json()["import_id"]
    other = (uuid.UUID(int=0xB1), uuid.UUID(int=0xB2))

    seen = await _call(container, "GET", f"/master-data/imports/{import_id}", tenant=other)
    sent = await _call(container, "POST", f"/master-data/imports/{import_id}/submit", tenant=other)
    assert (seen.status_code, sent.status_code) == (404, 404)


# ---------------------------------------------------------------- rfq mail --


async def test_an_rfq_is_sent_from_the_callers_own_mailbox_and_listed_on_its_case() -> None:
    from dw_purchasing.application.ports import Person

    world = _world()
    world.people.people[PRINCIPAL] = Person("Nguyễn Văn Mua", "Mua hàng", "Buyer@Alpha.Local")
    container = _container(EVERY_SCOPE, _mounted(world))
    case_id, supplier = await _rfq_drafted(world)

    sent = await _call(container, "POST", f"/requests/{case_id}/rfq/{supplier}/send")
    listed = await _call(container, "GET", f"/requests/{case_id}/rfq/mails")
    other = (uuid.UUID(int=0xB1), uuid.UUID(int=0xB2))
    theirs = await _call(
        container, "POST", f"/requests/{case_id}/rfq/{supplier}/send", tenant=other
    )

    assert sent.status_code == 202, sent.text
    assert sent.json()["mailbox"] == "buyer@alpha.local"
    assert [m["supplier_code"] for m in listed.json()] == [supplier]
    assert theirs.status_code == 404


async def test_who_does_not_prepare_rfqs_sends_no_mail() -> None:
    world = _world()
    container = _container(frozenset({"purchasing.request.read"}), _mounted(world))
    case_id, supplier = await _rfq_drafted(world)

    response = await _call(container, "POST", f"/requests/{case_id}/rfq/{supplier}/send")

    assert response.status_code == 403
    assert world.rfq_mail_rows.rows == {}


async def _rfq_drafted(world: World) -> tuple[uuid.UUID, str]:
    from datetime import UTC, datetime

    world.model.by_schema = {
        "RfqWording": {"PR-2611-004": SOURCING_WORDS},
    }
    me = world_caller(principal=PRINCIPAL)
    item = await world.service.read_mail(me, "P01")
    assert item.case_id is not None
    await world.approvals.submit(me, item.case_id, case_version=1)
    case = await world.service.case(me, item.case_id)
    assert case.approval is not None
    world.store.decide(
        case.approval.approval_id,
        tenant_id=ALPHA[0],
        workspace_id=ALPHA[1],
        approved=True,
        decided_by=uuid.UUID(int=0x4EAD),
        at=datetime(2026, 11, 2, 9, tzinfo=UTC),
        comment="ok",
    )
    await world.settlement.settle(
        case.approval.approval_id, world_caller(principal=uuid.UUID(int=0x4EAD))
    )
    await world.sourcing.draft_rfq(me, item.case_id, case_version=3)
    drafted = await world.service.case(me, item.case_id)
    assert drafted.rfq is not None
    written = next(d for d in drafted.rfq.drafts if d.written_by != "pending")
    return item.case_id, written.supplier_code


SOURCING_WORDS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_sourcing.json").read_text(encoding="utf-8")
)["rfq_words"]["good"]


async def test_following_an_order_is_refused_to_whoever_does_not_buy() -> None:
    """DW02 function 5's routes ask `purchasing.po.prepare` before the body:
    a reader is refused, the case untouched."""
    from dw_purchasing.testing.flows import orders_drafted, sourcing_world

    world = sourcing_world(REPO)
    case_id = await orders_drafted(world)
    version = (await world.service.case(world_caller(), case_id)).case_version
    container = _container(frozenset({"purchasing.request.read"}), _mounted(world))
    for path, body in (
        (
            f"/requests/{case_id}/po/PR-2611-004-03/bravo-number",
            {"case_version": version, "bravo_no": "PO-1"},
        ),
        (f"/requests/{case_id}/po/confirmations/from-mail/C01", {"case_version": version}),
        (f"/requests/{case_id}/po/PR-2611-004-03/confirmation/accept", {"case_version": version}),
        (
            f"/requests/{case_id}/po/PR-2611-004-03/receipts",
            {"case_version": version, "line_no": 1, "quantity": "1", "received_on": "2026-11-20"},
        ),
    ):
        response = await _call(container, "POST", path, body)
        assert response.status_code == 403, (path, response.text)
    assert (await _call(container, "GET", "/orders/late")).status_code == 403
    confirmations = f"/requests/{case_id}/po/confirmations"
    assert (await _call(container, "GET", confirmations)).status_code == 403
    assert (await world.service.case(world_caller(), case_id)).case_version == version
    buyer = _container(EVERY_SCOPE, _mounted(world))
    late = await _call(buyer, "GET", "/orders/late")
    assert late.status_code == 200, late.text


def _frames(body: str) -> list[tuple[str, dict[str, Any]]]:
    frames = []
    for block in body.strip().split("\n\n"):
        event, data = block.split("\n", 1)
        frames.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return frames


async def test_a_question_streams_its_steps_and_ends_in_the_kept_turn() -> None:
    world = _world()
    world.model.by_schema["QuestionIntent"] = {"giá": {"kind": "out_of_scope"}}
    response = await _call(
        _container(EVERY_SCOPE, _mounted(world)),
        "POST",
        "/assistant/ask/stream",
        {"question": "giá?"},
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    frames = _frames(response.text)
    assert [name for name, _ in frames] == ["step", "step", "delta", "done"]
    assert frames[-1][1]["turn"]["answer"] == frames[2][1]["text"]


async def test_a_refused_question_is_a_status_not_a_frame_in_a_200() -> None:
    world = _world()
    container = _container(frozenset({"sales.case.read"}), _mounted(world))
    refused = await _call(container, "POST", "/assistant/ask/stream", {"question": "giá?"})
    assert refused.status_code == 403, refused.text
    unsigned = await _call(
        container, "POST", "/assistant/ask/stream", {"question": "giá?"}, signed_in=False
    )
    assert unsigned.status_code == 401


async def test_another_session_is_a_404_before_the_stream_starts() -> None:
    world = _world()
    response = await _call(
        _container(EVERY_SCOPE, _mounted(world)),
        "POST",
        "/assistant/ask/stream",
        {"question": "giá?", "session_id": str(uuid.uuid4())},
    )
    assert response.status_code == 404, response.text


async def test_a_failure_after_the_start_is_one_fixed_frame_saying_nothing_more() -> None:
    """Headers are gone: it cannot be a status, and it names nothing inside."""
    world = _world()
    world.model.by_schema["QuestionIntent"] = {"giá": {"kind": "out_of_scope"}}

    async def broken(*_: object, **__: object) -> None:
        raise RuntimeError("postgres://secret@db/leak")

    world.assistant.store.append = broken  # type: ignore[method-assign]
    response = await _call(
        _container(EVERY_SCOPE, _mounted(world)),
        "POST",
        "/assistant/ask/stream",
        {"question": "giá?"},
    )
    assert response.status_code == 200
    frames = _frames(response.text)
    assert frames[-1] == ("error", {"message": "Không trả lời được lúc này. Hãy hỏi lại."})
    assert "secret" not in response.text
