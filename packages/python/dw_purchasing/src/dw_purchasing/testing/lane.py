"""DW2's automation lane over the in-memory world, for the unit tests and the
eval smoke: the platform's service-account lookup with DW2's account where
one is seeded, the workspaces with work, a measurement of the PR mail
reading written as the attesting lane writes one."""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Sequence

from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import Uuid4Generator
from dw_platform.application.identity import MembershipAccess
from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.application.automation import BARS, ModelAttestation
from dw_purchasing.application.automation_lane import AutomationLane, dw2_subject
from dw_purchasing.domain.automation import PurchasingModelStep
from dw_purchasing.testing.world import ALPHA, RecordedNotices, World, services_of

DW2: uuid.UUID = uuid.UUID(int=0xD2)


@dataclasses.dataclass
class Accounts:
    """`ServiceAccessPort`: DW2's account in each seeded workspace, cut to
    the ceiling asked, as the platform's lookup cuts it."""

    seeded: set[tuple[uuid.UUID, uuid.UUID]] = dataclasses.field(default_factory=set)
    asked: list[tuple[str, frozenset[str]]] = dataclasses.field(default_factory=list)

    async def find_service_access(
        self,
        subject: str,
        tenant_id: uuid.UUID,
        workspace_id: uuid.UUID,
        ceiling: frozenset[str],
    ) -> MembershipAccess | None:
        self.asked.append((subject, ceiling))
        if subject != dw2_subject(tenant_id) or (tenant_id, workspace_id) not in self.seeded:
            return None
        return MembershipAccess(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            principal_id=DW2,
            roles=frozenset({"purchasing_dw2"}),
            scopes=ceiling,
            groups=frozenset(),
            clearance="internal",
            plan_id="professional",
            feature_flags=frozenset(),
        )


@dataclasses.dataclass
class Due:
    scopes: list[tuple[uuid.UUID, uuid.UUID]] = dataclasses.field(default_factory=list)

    async def due(self) -> Sequence[tuple[uuid.UUID, uuid.UUID]]:
        return self.scopes


def lane_of(
    world: World,
    notices: RecordedNotices,
    accounts: Accounts | None = None,
    mailboxes: tuple[tuple[uuid.UUID, uuid.UUID], ...] = (ALPHA,),
) -> AutomationLane:
    """The lane over ``world``, every notice into one inbox, as the
    composition root wires it."""
    world.approvals = dataclasses.replace(world.approvals, notices=notices)
    world.settlement = dataclasses.replace(world.settlement, notices=notices)
    return AutomationLane(
        access=accounts if accounts is not None else Accounts({ALPHA}),
        scopes=Due(),
        mailboxes=mailboxes,
        services=services_of(world),
        uow=world.store,
        notices=notices,
        clock=world.clock,
        ids=Uuid4Generator(),
    )


async def measure_pr_reading(
    world: World, scope: tuple[uuid.UUID, uuid.UUID] = ALPHA, value: float = 0.95
) -> None:
    """A live measurement of the PR mail reading for ``scope``'s tenant."""
    await measure(world, PurchasingModelStep.PR_MAIL_READING, scope, value)


async def measure(
    world: World,
    step: PurchasingModelStep,
    scope: tuple[uuid.UUID, uuid.UUID] = ALPHA,
    value: float = 0.95,
) -> None:
    """A live measurement of ``step`` for ``scope``'s tenant, from its own
    dataset (`automation.BARS`)."""
    await ModelAttestation(world.measurements, world.clock, Uuid4Generator()).attest(
        ContextScope(TenantId(scope[0]), WorkspaceId(scope[1])),
        step,
        model="qwen3.5:9b",
        value=value,
        held=True,
        dataset=f"{BARS[step].dataset}@1.0.0",
    )
