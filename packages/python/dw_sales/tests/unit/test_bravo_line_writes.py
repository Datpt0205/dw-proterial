"""Ticket 53 on DW's side: a line's change proposed against what Bravo holds,
decided by the one person whose Bravo user writes it, signed in the
decision, and carried out through the gateway with its answer kept.

The gateway's own checks are its tests (`apps/bravo-gateway`); here the
gateway is a fake that records what it was sent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace, TracebackType
from typing import Any, Self

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from dw_agent_runtime.approval_flow import ApproveAndResumeService, ProposedDecision
from dw_bravo.approval_token import ApprovalTokenSigner, ApprovalTokenVerifier
from dw_bravo.contract import CancelLine, LineRef, SetConfirmedDate, SetQuantity, content_hash
from dw_kernel.errors import ConflictError, NotFoundError, PermissionDeniedError
from dw_platform.application.access_context import AccessContext
from dw_platform.application.authorization import ScopeAuthorizationService
from dw_platform.domain.approval import ApprovalRequest, ApprovalStatus
from dw_platform.domain.audit import AuditEvent
from dw_sales.adapters.bravo_contract import BravoContract, ContractSigner
from dw_sales.application.access import Gate
from dw_sales.application.bravo_line_writes import (
    BRAVO_WRITE_APPROVAL,
    BravoCommandsPort,
    BravoLineWrite,
    BravoLineWrites,
    BravoSo,
    BravoSoLine,
    BravoUnreachableError,
    BravoWriteDecisions,
    BravoWriteSettlement,
    BravoWriteStamp,
    CancelChange,
    ConfirmedDateChange,
    GatewayAnswer,
    PreparedWrite,
    QuantityChange,
    write_bravo_versions,
)
from dw_sales.application.runs import APPROVAL_PREFIX
from dw_sales.application.stages import Stage, StageHandlers

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 21, 3, tzinfo=UTC)
TENANT, WORKSPACE, CASE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PIC = uuid.uuid4()
VERSION = 3
ROWVERSION = "0x00000000000007D2"
SO = BravoSo(
    so_id=10,
    so_no="SO2611-000161",
    lines=(
        BravoSoLine(20, 1, "PRV-1", Decimal(1200), date(2026, 12, 1), ROWVERSION),
        BravoSoLine(21, 2, "PRV-2", Decimal(5), None, "0x00000000000007D3"),
        # PO line 3 split in Bravo: two rows.
        BravoSoLine(22, 3, "PRV-3", Decimal(2), None, "0x00000000000007D4"),
        BravoSoLine(23, 3, "PRV-3", Decimal(1), None, "0x00000000000007D5"),
    ),
)
KEY = Ed25519PrivateKey.generate()


def _context(*scopes: str, who: uuid.UUID = PIC) -> AccessContext:
    return AccessContext(
        tenant_id=TENANT,
        workspace_id=WORKSPACE,
        principal_id=who,
        roles=frozenset(),
        scopes=frozenset(scopes),
        plan_id="professional",
    )


PIC_CONTEXT = _context("sales.case.read", "sales.bravo.write")


# ------------------------------------------------------------------ fakes


@dataclass
class Store:
    rows: dict[uuid.UUID, BravoLineWrite] = field(default_factory=dict)

    async def get(self, approval_id: uuid.UUID) -> BravoLineWrite | None:
        return self.rows.get(approval_id)

    async def add(self, write: BravoLineWrite) -> None:
        if any(
            r.status == "proposed" and (r.case_id, r.line_no) == (write.case_id, write.line_no)
            for r in self.rows.values()
        ):
            raise ConflictError("open", details={"rule": "bravo_write_open"})
        self.rows[write.approval_id] = write

    async def save(self, write: BravoLineWrite, *, expected: str) -> None:
        if self.rows[write.approval_id].status != expected:
            raise ConflictError("settled meanwhile")
        self.rows[write.approval_id] = write

    async def of_case(self, case_id: uuid.UUID) -> list[BravoLineWrite]:
        return [r for r in self.rows.values() if r.case_id == case_id]


@dataclass
class Approvals:
    requests: dict[uuid.UUID, ApprovalRequest] = field(default_factory=dict)

    async def add(self, request: ApprovalRequest) -> None:
        self.requests[request.id] = request

    async def get(
        self, approval_id: uuid.UUID, *, workspace_id: uuid.UUID, audience: object
    ) -> ApprovalRequest | None:
        return self.requests.get(approval_id)

    async def latest_decision(self, approval_id: uuid.UUID) -> None:
        raise NotImplementedError("not exercised by these tests")


@dataclass
class Audit:
    events: list[AuditEvent] = field(default_factory=list)

    async def append(self, event: AuditEvent) -> None:
        self.events.append(event)


@dataclass
class Orders:
    so_no: str | None = SO.so_no
    assigned_to: uuid.UUID = PIC
    # What the case was stamped with when it opened (ticket 61).
    stage_versions: dict[str, str] = field(default_factory=lambda: {"write_bravo": "1.0.0"})

    async def get(self, case_id: uuid.UUID) -> object:
        if case_id != CASE:
            return None
        lines = tuple(SimpleNamespace(line_no=n) for n in (1, 2, 3))
        return SimpleNamespace(
            case=SimpleNamespace(
                lines=lines,
                bravo_so_no=self.so_no,
                case_version=VERSION,
                status=SimpleNamespace(value="checked"),
            ),
            origin=SimpleNamespace(
                assigned_to=self.assigned_to, stage_versions=self.stage_versions
            ),
        )


@dataclass
class World:
    store: Store = field(default_factory=Store)
    approvals: Approvals = field(default_factory=Approvals)
    audit_log: Audit = field(default_factory=Audit)
    orders_: Orders = field(default_factory=Orders)
    commits: int = 0

    def __call__(self, scope: object) -> Work:
        return Work(self)


@dataclass
class Work:
    world: World

    @property
    def orders(self) -> Orders:
        return self.world.orders_

    @property
    def approvals(self) -> Approvals:
        return self.world.approvals

    @property
    def bravo_writes(self) -> Store:
        return self.world.store

    @property
    def audit(self) -> Audit:
        return self.world.audit_log

    async def commit(self) -> None:
        self.world.commits += 1

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


@dataclass
class Bravo:
    orders: dict[str, BravoSo] = field(default_factory=lambda: {SO.so_no: SO})
    users: dict[str, tuple[int, ...]] = field(default_factory=lambda: {"NV001": (2413,)})
    down: bool = False

    async def sales_order(self, tenant_id: uuid.UUID, so_no: str) -> BravoSo | None:
        if self.down:
            raise BravoUnreachableError("no answer")
        return self.orders.get(so_no)

    async def bravo_user_ids(self, tenant_id: uuid.UUID, employee_code: str) -> tuple[int, ...]:
        if self.down:
            raise BravoUnreachableError("no answer")
        return self.users.get(employee_code, ())


@dataclass
class Codes:
    links: dict[uuid.UUID, str] = field(default_factory=lambda: {PIC: "NV001"})

    async def employee_code(self, tenant_id: uuid.UUID, subject: uuid.UUID) -> str | None:
        return self.links.get(subject)


@dataclass
class Gateway:
    answers: list[GatewayAnswer | Exception] = field(
        default_factory=lambda: [GatewayAnswer("written")]
    )
    sent: list[tuple[str, dict[str, Any], str]] = field(default_factory=list)

    async def write(self, kind: str, content: dict[str, Any], token: str) -> GatewayAnswer:
        self.sent.append((kind, content, token))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@dataclass
class Notices:
    told: list[dict[str, Any]] = field(default_factory=list)

    async def deliver(self, context: AccessContext, **notice: Any) -> None:
        self.told.append(notice)


class _Clock:
    def __init__(self) -> None:
        self.at = NOW

    def now(self) -> datetime:
        return self.at


class _Ids:
    def new_uuid(self) -> uuid.UUID:
        return uuid.uuid4()


def _service(world: World, bravo: Bravo | None = None) -> BravoLineWrites:
    return BravoLineWrites(
        world,  # type: ignore[arg-type]
        Gate(ScopeAuthorizationService()),
        bravo or Bravo(),
        write_bravo_versions(BravoContract()),
        _Clock(),
        _Ids(),
    )


async def _proposed(
    world: World,
    change: object | None = None,
    line: int = 1,
    *,
    service: BravoLineWrites | None = None,
) -> ApprovalRequest:
    view = await (service or _service(world)).propose(
        PIC_CONTEXT,
        CASE,
        line,
        change or ConfirmedDateChange(field="confirmed_date", value=date(2026, 12, 8)),  # type: ignore[arg-type]
        case_version=VERSION,
    )
    return world.approvals.requests[view.approval_id]


# --------------------------------------------------------------- proposing


async def test_a_date_change_is_proposed_against_the_row_bravo_holds() -> None:
    world = World()

    request = await _proposed(world)

    expected = SetConfirmedDate(
        line=LineRef(so_id=10, line_id=20, line_rowversion=ROWVERSION),
        confirmed_date=date(2026, 12, 8),
    )
    payload = request.payload
    assert request.approval_type == BRAVO_WRITE_APPROVAL
    assert request.required_scope == "sales.bravo.write"
    assert payload["kind"] == "so.line.set_confirmed_date@1"
    assert payload["content_hash"] == content_hash(expected)
    assert (payload["before"], payload["after"]) == ("2026-12-01", "2026-12-08")
    assert payload["makers"] == []
    assert world.store.rows[request.id].status == "proposed"
    assert [e.action for e in world.audit_log.events] == ["sales.bravo_write.proposed"]


async def test_a_quantity_change_names_the_quantity_column_bravo_holds() -> None:
    world = World()

    request = await _proposed(world, QuantityChange(field="quantity", value=Decimal("1100")))

    expected = SetQuantity(
        line=LineRef(so_id=10, line_id=20, line_rowversion=ROWVERSION), quantity=Decimal(1100)
    )
    assert request.payload["content_hash"] == content_hash(expected)
    assert (request.payload["before"], request.payload["after"]) == ("1200", "1100")


async def test_a_cancel_is_proposed_with_its_reason_against_the_row_bravo_holds() -> None:
    # Ticket 71: the gateway runs the cancel since the 11-25 UAT trace.
    world = World()

    request = await _proposed(world, CancelChange(field="cancel", reason="Khách hủy dòng"))

    expected = CancelLine(
        line=LineRef(so_id=10, line_id=20, line_rowversion=ROWVERSION), reason="Khách hủy dòng"
    )
    payload = request.payload
    assert payload["kind"] == "so.line.cancel@1"
    assert payload["content_hash"] == content_hash(expected)
    assert (payload["before"], payload["after"]) == ("1200", "Hủy: Khách hủy dòng")


def test_a_cancel_without_its_reason_is_not_a_change() -> None:
    with pytest.raises(ValidationError):
        CancelChange(field="cancel", reason="")


@pytest.mark.parametrize(
    ("line", "orders", "bravo", "change"),
    [
        (3, Orders(), Bravo(), None),  # split in Bravo: which row is not guessed
        (
            1,
            Orders(),
            Bravo(),
            ConfirmedDateChange(field="confirmed_date", value=date(2026, 12, 1)),
        ),
        (1, Orders(so_no=None), Bravo(), None),
        (1, Orders(so_no="SO-OTHER"), Bravo(), None),
        (1, Orders(), Bravo(down=True), None),
    ],
    ids=["split_line", "nothing_to_write", "no_so_yet", "so_not_in_bravo", "bravo_down"],
)
async def test_what_cannot_be_proposed_exactly_is_refused_and_opens_nothing(
    line: int, orders: Orders, bravo: Bravo, change: object | None
) -> None:
    world = World(orders_=orders)

    with pytest.raises(ConflictError):
        await _service(world, bravo).propose(
            PIC_CONTEXT,
            CASE,
            line,
            change or ConfirmedDateChange(field="confirmed_date", value=date(2026, 12, 8)),  # type: ignore[arg-type]
            case_version=VERSION,
        )
    assert world.approvals.requests == {} and world.store.rows == {}


async def test_proposing_needs_the_right_where_it_is_checked() -> None:
    world = World()

    with pytest.raises(PermissionDeniedError):
        await _service(world).propose(
            _context("sales.case.read"),
            CASE,
            1,
            ConfirmedDateChange(field="confirmed_date", value=date(2026, 12, 8)),
            case_version=VERSION,
        )
    assert world.approvals.requests == {}


async def test_a_line_or_case_not_in_the_workspace_is_not_found() -> None:
    world = World()
    change = ConfirmedDateChange(field="confirmed_date", value=date(2026, 12, 8))

    with pytest.raises(NotFoundError):
        await _service(world).propose(PIC_CONTEXT, uuid.uuid4(), 1, change, case_version=VERSION)
    with pytest.raises(NotFoundError):
        await _service(world).propose(PIC_CONTEXT, CASE, 9, change, case_version=VERSION)


async def test_a_case_the_caller_may_not_see_is_not_found_to_propose_or_list() -> None:
    # Record visibility: someone who sees only another person's cases finds
    # neither the case to write against nor its proposals.
    world = World()
    await _proposed(world)
    restricted = PIC_CONTEXT.model_copy(
        update={"record_visibility": "restricted", "visible_owners": frozenset({uuid.uuid4()})}
    )
    change = ConfirmedDateChange(field="confirmed_date", value=date(2026, 12, 9))

    with pytest.raises(NotFoundError):
        await _service(world).propose(restricted, CASE, 2, change, case_version=VERSION)
    with pytest.raises(NotFoundError):
        await _service(world).of_case(restricted, CASE)
    assert len(await _service(world).of_case(PIC_CONTEXT, CASE)) == 1
    assert len(world.store.rows) == 1


async def test_a_proposal_made_on_an_older_case_version_is_refused() -> None:
    world = World()

    with pytest.raises(ConflictError) as refused:
        await _service(world).propose(
            PIC_CONTEXT,
            CASE,
            1,
            ConfirmedDateChange(field="confirmed_date", value=date(2026, 12, 8)),
            case_version=VERSION - 1,
        )
    assert refused.value.details["rule"] == "stale_case_version"
    assert world.approvals.requests == {}


async def test_one_open_proposal_per_line() -> None:
    world = World()
    await _proposed(world)

    with pytest.raises(ConflictError):
        await _proposed(world)


# ---------------------------------------------------------------- deciding


def test_the_type_is_decided_by_one_person_not_under_sales_strict_rule() -> None:
    flow = ApproveAndResumeService(
        uow_factory=None,  # type: ignore[arg-type]
        runner=None,  # type: ignore[arg-type]
        run_store=None,  # type: ignore[arg-type]
        clock=_Clock(),
        id_generator=_Ids(),
        strict_approval_prefixes=frozenset({APPROVAL_PREFIX}),
    )

    assert not flow.is_strict(BRAVO_WRITE_APPROVAL)


async def test_a_decision_on_a_settled_proposal_is_refused_before_it_is_recorded() -> None:
    world = World()
    request = await _proposed(world)
    guard = BravoWriteDecisions(world)  # type: ignore[arg-type]
    decision = ProposedDecision(approve=True, comment="", reasons={}, subject_version=None)

    await guard.check(request, decision, PIC_CONTEXT)
    row = world.store.rows[request.id]
    world.store.rows[request.id] = row.model_copy(
        update={"status": "refused", "decided_by": PIC, "settled_at": NOW}
    )
    with pytest.raises(ConflictError):
        await guard.check(request, decision, PIC_CONTEXT)


def _stamp(
    bravo: Bravo | None = None, codes: Codes | None = None, *, key: bool = True
) -> BravoWriteStamp:
    return BravoWriteStamp(
        ContractSigner(ApprovalTokenSigner(KEY, "k1")) if key else None,
        write_bravo_versions(BravoContract()),
        codes or Codes(),
        bravo or Bravo(),
        _Clock(),
    )


async def test_the_decision_signs_the_exact_command_for_the_deciders_bravo_user() -> None:
    world = World()
    request = await _proposed(world)

    stamp = await _stamp().stamp(request, object(), PIC_CONTEXT)

    claims = ApprovalTokenVerifier({"k1": KEY.public_key()}).verify(
        str(stamp["token"]), now=NOW + timedelta(minutes=1)
    )
    assert (claims.approval_id, claims.tenant_id, claims.workspace_id) == (
        request.id,
        TENANT,
        WORKSPACE,
    )
    assert claims.content_hash == request.payload["content_hash"]
    assert (claims.bravo_user_id, claims.employee_code) == (2413, "NV001")


@pytest.mark.parametrize(
    ("stamp", "who"),
    [
        (_stamp(key=False), PIC),
        (_stamp(), uuid.uuid4()),  # a decider with no employee code
        (_stamp(Bravo(users={"NV001": (2413, 2414)})), PIC),
        (_stamp(Bravo(users={})), PIC),
        (_stamp(Bravo(down=True)), PIC),
    ],
    ids=["no_signing_key", "no_link", "two_bravo_users", "no_bravo_user", "bravo_down"],
)
async def test_a_decision_that_cannot_be_signed_is_refused(
    stamp: BravoWriteStamp, who: uuid.UUID, request: pytest.FixtureRequest
) -> None:
    world = World()
    approval = await _proposed(world)

    with pytest.raises(ConflictError) as refused:
        await stamp.stamp(approval, object(), _context("sales.bravo.write", who=who))
    expected = {
        "no_signing_key": "no_signing_key",
        "no_link": "no_employee_code",
        "two_bravo_users": "one_bravo_user",
        "no_bravo_user": "one_bravo_user",
        "bravo_down": None,
    }[request.node.callspec.id]
    assert refused.value.details.get("rule") == expected


async def test_a_payload_whose_command_no_longer_hashes_as_proposed_is_not_signed() -> None:
    world = World()
    request = await _proposed(world)
    request.payload["command"]["confirmed_date"] = "2027-01-01"  # type: ignore[index]

    with pytest.raises(ConflictError):
        await _stamp().stamp(request, object(), PIC_CONTEXT)


# ------------------------------------------------------------- carrying out


async def _decided(world: World, *, approve: bool = True) -> tuple[ApprovalRequest, str]:
    request = await _proposed(world)
    token = str((await _stamp().stamp(request, object(), PIC_CONTEXT))["token"])
    request.status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
    return request, token


def _settlement(
    world: World, gateway: Gateway, notices: Notices | None = None
) -> BravoWriteSettlement:
    return BravoWriteSettlement(world, gateway, notices or Notices(), _Clock(), _Ids())  # type: ignore[arg-type]


async def test_an_approved_write_sends_the_exact_command_and_keeps_bravos_answer() -> None:
    world, gateway, notices = World(), Gateway(), Notices()
    request, token = await _decided(world)

    status = await _settlement(world, gateway, notices).settle(request.id, PIC_CONTEXT, token)

    [(kind, content, sent)] = gateway.sent
    assert BravoContract().hash_of(kind, content) == request.payload["content_hash"]
    assert sent == token
    row = world.store.rows[request.id]
    assert status == row.status == "written" and row.decided_by == PIC
    assert notices.told[0]["recipients"] == [PIC]
    assert world.audit_log.events[-1].action == "sales.bravo_write.written"


async def test_a_redelivered_decision_sends_nothing_again() -> None:
    world, gateway = World(), Gateway()
    request, token = await _decided(world)
    settlement = _settlement(world, gateway)

    await settlement.settle(request.id, PIC_CONTEXT, token)
    await settlement.settle(request.id, PIC_CONTEXT, token)

    assert len(gateway.sent) == 1


async def test_a_rejected_write_sends_nothing() -> None:
    world, gateway = World(), Gateway()
    request, token = await _decided(world, approve=False)

    assert await _settlement(world, gateway).settle(request.id, PIC_CONTEXT, token) == "rejected"
    assert gateway.sent == []


async def test_an_approval_without_its_token_writes_nothing() -> None:
    world, gateway = World(), Gateway()
    request, _ = await _decided(world)

    assert await _settlement(world, gateway).settle(request.id, PIC_CONTEXT, None) == "refused"
    assert gateway.sent == []


async def test_the_gateways_refusal_is_kept_with_its_reason() -> None:
    world = World()
    gateway = Gateway([GatewayAnswer("refused", "switch", "write_kind_off")])
    request, token = await _decided(world)

    await _settlement(world, gateway).settle(request.id, PIC_CONTEXT, token)

    row = world.store.rows[request.id]
    assert (row.status, row.check, row.reason) == ("refused", "switch", "write_kind_off")


async def test_a_refusal_after_a_lost_answer_is_in_doubt_not_refused() -> None:
    world = World()
    gateway = Gateway(
        [BravoUnreachableError("timeout"), GatewayAnswer("refused", "token", "expired")]
    )
    request, token = await _decided(world)
    settlement = _settlement(world, gateway)

    with pytest.raises(BravoUnreachableError):
        await settlement.settle(request.id, PIC_CONTEXT, token)
    assert world.store.rows[request.id].transport_failures == 1
    await settlement.settle(request.id, PIC_CONTEXT, token)

    assert world.store.rows[request.id].status == "in_doubt"


def test_dw1_registers_the_guard_and_the_stamp_and_signs_nothing_without_a_key() -> None:
    from pathlib import Path

    from dw_sales.evals.graders import CALLERS, OUTSIDER
    from dw_sales.evals.world import SampleSet, open_world

    repo = Path(__file__).resolve().parents[5]
    flow = open_world(repo, SampleSet.of(repo, None), (*CALLERS, OUTSIDER)).runtime.approval_flow

    assert isinstance(flow.decision_guards[BRAVO_WRITE_APPROVAL], BravoWriteDecisions)
    stamp = flow.decision_stamps[BRAVO_WRITE_APPROVAL]
    assert isinstance(stamp, BravoWriteStamp) and stamp.signer is None


async def test_a_kind_the_gateway_does_not_run_yet_is_not_proposed() -> None:
    class _Pending(BravoContract):
        def prepare(self, change: object, so: BravoSo, line: BravoSoLine) -> PreparedWrite:
            return PreparedWrite("so.line.cancel@1", {}, "0" * 64, pending="not traced")

    world = World()
    service = BravoLineWrites(
        world,  # type: ignore[arg-type]
        Gate(ScopeAuthorizationService()),
        Bravo(),
        write_bravo_versions(_Pending()),
        _Clock(),
        _Ids(),
    )

    with pytest.raises(ConflictError):
        await service.propose(
            PIC_CONTEXT,
            CASE,
            1,
            QuantityChange(field="quantity", value=Decimal(3)),
            case_version=VERSION,
        )
    assert world.approvals.requests == {}


# -------------------------------------- the stage version a case runs on (61) --


class _Other(BravoContract):
    """A second command set, as a new write-Bravo version would bring."""

    def prepare(self, change: object, so: BravoSo, line: BravoSoLine) -> PreparedWrite:
        raise AssertionError("a case pinned to 1.0.0 is prepared by 1.0.0")


def _served(**versions: BravoCommandsPort) -> StageHandlers[BravoCommandsPort]:
    return StageHandlers(
        Stage.WRITE_BRAVO, {k.removeprefix("v").replace("_", "."): v for k, v in versions.items()}
    )


async def test_the_proposal_names_the_stage_version_the_case_runs_on() -> None:
    request = await _proposed(World())
    assert request.payload["stage_version"] == "1.0.0"


async def test_a_case_keeps_its_versions_command_set_when_a_newer_one_is_served() -> None:
    """Acceptance 1: a case opened on 1.0.0 finishes on it after 1.1.0 ships."""
    world = World()
    service = _service(world)
    service = BravoLineWrites(
        service.uow,
        service.gate,
        service.orders,
        _served(v1_0_0=BravoContract(), v1_1_0=_Other()),
        service.clock,
        service.ids,
    )
    request = await _proposed(world, service=service)
    assert request.payload["kind"] == "so.line.set_confirmed_date@1"


async def test_a_case_pinned_to_a_version_no_longer_served_is_refused_and_opens_nothing() -> None:
    world = World(orders_=Orders(stage_versions={"write_bravo": "0.9.0"}))
    with pytest.raises(ConflictError) as refused:
        await _proposed(world)
    assert refused.value.details["rule"] == "stage_version_unavailable"
    assert world.approvals.requests == {} and world.store.rows == {}


async def test_a_case_with_no_write_bravo_stamp_is_refused() -> None:
    world = World(orders_=Orders(stage_versions={}))
    with pytest.raises(ConflictError) as refused:
        await _proposed(world)
    assert refused.value.details["rule"] == "stage_not_pinned"


async def test_a_decision_on_a_stage_version_no_longer_served_is_not_signed() -> None:
    """The hash is checked by the command set of the version the proposal
    names; one this deployment does not serve signs nothing."""
    request = await _proposed(World())
    request.payload["stage_version"] = "0.9.0"
    with pytest.raises(ConflictError) as refused:
        await _stamp().stamp(request, object(), PIC_CONTEXT)
    assert refused.value.details["rule"] == "stage_version_unavailable"
