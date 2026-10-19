"""Who is calling, what they may do, and which amounts they may see.

Everything here is resolved from the platform's verified `AccessContext`,
never from a request: the tenant and workspace a call reads, the principal a
decision is stamped with, and the scopes a step needs. The scope names are the
ones the sales migration declares (spec "Actors, roles and scopes"); which
role holds which is the platform catalogue's to say, not this module's.

Authorization and price visibility are separate questions. `require` refuses
a step (403); `PriceView` decides what a response may carry, so a caller who
may read a case without its prices gets the case with every amount marked
hidden, never a 403 and never a zero (spec decision 8, dw_sales ADR 0003).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol

from dw_kernel.ids import TenantId, WorkspaceId
from dw_platform.application.access_context import AccessContext
from dw_sales.application.ports import SalesScope
from dw_sales.domain.orders import Actor, Capability


class SalesScopes(StrEnum):
    """The `sales.*` scopes a route or a step asks for."""

    OVERVIEW_READ = "sales.overview.read"
    CASE_READ = "sales.case.read"
    PRICE_READ = "sales.price.read"
    PRICE_OTHER_CUSTOMERS_READ = "sales.price.other_customers.read"
    INBOX_PROCESS = "sales.inbox.process"
    ORDER_PREPARE = "sales.order.prepare"
    ORDER_CROSS_CHECK = "sales.order.cross_check"
    # Raise an order's cross-check again for its Bravo recorder (ticket 14).
    ORDER_RESEND_CROSS_CHECK = "sales.order.resend_cross_check"
    QUOTE_PREPARE = "sales.quote.prepare"
    QUOTE_APPROVE = "sales.quote.approve"
    COMPLIANCE_ACK = "sales.compliance.ack"
    WORKER_PAUSE = "sales.worker.pause"
    WORKER_RESUME = "sales.worker.resume"
    # Reassign a case to another member who works it (ticket 17, the head's).
    CASE_ASSIGN = "sales.case.assign"
    # Approve or reject a customer's PO layout a PIC mapped (ticket 30): the
    # checker of a maker/checker pair, never its proposer (the head's).
    LAYOUT_APPROVE = "sales.layout.approve"
    # Propose a tenant version of a Sales rule (PIC and head), and approve or
    # reject one (the head's): a maker/checker pair (ticket 19).
    RULES_PROPOSE = "sales.rules.propose"
    RULES_APPROVE = "sales.rules.approve"
    # Import a master-data list from a file and send it to be approved (PIC
    # and head), and approve or reject one (the head's): a maker/checker pair
    # (ticket 41).
    MASTER_DATA_IMPORT = "sales.master_data.import"
    MASTER_DATA_APPROVE = "sales.master_data.approve"


# What a customer may grant FPT support in Sales (dw_sales ADR 0003 §5, ADR
# 0024): the overview and the cases, never a price and never a write, for the
# whole workspace. The composition root registers it in the platform's support
# catalog; the platform stamps these scopes on the grant, so a support context
# holds exactly them and `PriceView` hides every amount from it, as from any
# caller without `sales.price.read`. Only `sales_head` holds `support.grant`
# (migration 7c8ba908575f), so only the head can issue it.
SUPPORT_SCOPE_SET_KEY: Final = "sales.case_support"
SUPPORT_SCOPE_SET_LABEL: Final = "Xem hồ sơ Sales (không xem giá)"
SUPPORT_SCOPES: Final = frozenset({SalesScopes.OVERVIEW_READ.value, SalesScopes.CASE_READ.value})
SUPPORT_RESOURCE_TYPES: Final = frozenset({"workspace"})


class SalesAuthorizationPort(Protocol):
    """The platform's scope check, as this context uses it.

    The platform's `ScopeAuthorizationService` satisfies it: `require` raises
    `PermissionDeniedError`, `is_allowed` answers without raising.
    """

    async def require(
        self,
        *,
        context: AccessContext,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
    ) -> None: ...

    def is_allowed(self, context: AccessContext, action: str) -> bool: ...


def sales_scope(context: AccessContext) -> SalesScope:
    """The tenant and workspace a call reads: the verified context's, only."""
    return SalesScope(TenantId(context.tenant_id), WorkspaceId(context.workspace_id))


@dataclass(frozen=True, slots=True)
class PriceView:
    """Which amounts a response may carry for this caller.

    ``amounts``: any price, amount, LME figure or copper basis band
    (`sales.price.read`). ``other_customers``: another customer's price, and
    anything formed from one (`sales.price.other_customers.read`, on top of
    the first).
    """

    amounts: bool
    other_customers: bool

    @classmethod
    def of(cls, context: AccessContext, authz: SalesAuthorizationPort) -> PriceView:
        amounts = authz.is_allowed(context, SalesScopes.PRICE_READ)
        return cls(
            amounts=amounts,
            other_customers=amounts
            and authz.is_allowed(context, SalesScopes.PRICE_OTHER_CUSTOMERS_READ),
        )


@dataclass(frozen=True)
class Gate:
    """Scope checks, raised as the platform raises them (403, naming the scope)."""

    authz: SalesAuthorizationPort

    async def require(
        self,
        context: AccessContext,
        *scopes: SalesScopes,
        resource_type: str = "sales",
        resource_id: str | None = None,
    ) -> None:
        for scope in scopes:
            await self.authz.require(
                context=context,
                action=scope.value,
                resource_type=resource_type,
                resource_id=resource_id,
            )

    def allows(self, context: AccessContext, scope: SalesScopes) -> bool:
        return self.authz.is_allowed(context, scope.value)

    def prices(self, context: AccessContext) -> PriceView:
        return PriceView.of(context, self.authz)


# The scope that verifies each capability an order case asks for.
_CAPABILITIES: Final[Mapping[Capability, SalesScopes]] = MappingProxyType(
    {
        Capability.ACKNOWLEDGE_EXPORT_CONTROL: SalesScopes.COMPLIANCE_ACK,
        Capability.RESEND_CROSS_CHECK: SalesScopes.ORDER_RESEND_CROSS_CHECK,
    }
)


def order_actor(context: AccessContext, gate: Gate) -> Actor:
    """The caller as an order case knows them: their principal id, and each
    capability whose scope (`_CAPABILITIES`) their verified context holds."""
    capabilities = frozenset(c for c, scope in _CAPABILITIES.items() if gate.allows(context, scope))
    return Actor(user_id=context.principal_id, capabilities=capabilities)
