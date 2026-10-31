"""Which rules a call runs under: the tenant's version, else the platform's.

`CLAUDE.md` "Per-tenant artifacts": the tenant comes from the verified access
context, never the request; resolution falls back to the platform, never
sideways to another tenant. The tenant's version is stored by the platform
(`PolicyOverridePort`, one whole document per policy id) and validated here
against `PurchasingRules`.

A stored version that does not validate is refused, not skipped: falling back
to the platform's rules would run a tenant under limits it replaced, quietly
(failure-modes #7). Its version must also differ from every platform version,
so a case's stamp names one document.

Until the rule-version engine moves to the platform (ADR 0013 decision 3),
Purchasing has no editor of its own: a tenant's version is written through the
platform's override store.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from pydantic import ValidationError

from dw_kernel.errors import ConflictError
from dw_platform.application.access_context import AccessContext
from dw_purchasing.application.ports import PlatformRulesPort, TenantPolicyPort
from dw_purchasing.domain.rules import POLICY_ID, PurchasingRules

UNREADABLE: Final = "quy tắc mua hàng của công ty không đọc được: báo quản trị, chưa nhận yêu cầu"


@dataclass(frozen=True)
class RuleBook:
    platform: PlatformRulesPort
    tenant: TenantPolicyPort
    # Every version the platform ever shipped: a tenant's may reuse none.
    platform_versions: frozenset[str]

    async def resolve(self, context: AccessContext) -> PurchasingRules:
        document = await self.tenant.get(context, POLICY_ID)
        if document is None:
            return self.platform.current()
        try:
            rules = PurchasingRules.model_validate(document)
        except ValidationError as exc:
            raise ConflictError(UNREADABLE, details={"policy_id": POLICY_ID}) from exc
        if rules.version in self.platform_versions:
            raise ConflictError(
                UNREADABLE, details={"policy_id": POLICY_ID, "reason": "version_shipped"}
            )
        return rules
