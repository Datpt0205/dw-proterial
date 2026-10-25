"""`LoginAccountsPort` in memory, honest about the contract.

It refuses a second account for an email and reaches only accounts created
for the asking tenant, as `KeycloakLoginAccounts` does against a real
Keycloak (`tests/integration/test_keycloak_accounts.py`). For tests only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from dw_kernel.errors import ConflictError, NotFoundError
from dw_platform.application.member_accounts import LoginAccount


@dataclass
class HeldAccount:
    tenant_id: uuid.UUID
    password: str
    enabled: bool = True


@dataclass
class MemoryLoginAccounts:
    held: dict[str, HeldAccount] = field(default_factory=dict)
    # Every call that reached the "identity provider", refused or not.
    calls: int = 0

    async def create(
        self, *, tenant_id: uuid.UUID, email: str, display_name: str, temporary_password: str
    ) -> None:
        self.calls += 1
        if email in self.held:
            raise ConflictError(
                "this email already has a sign-in account",
                details={"reason_code": "login_account_exists"},
            )
        self.held[email] = HeldAccount(tenant_id, temporary_password)

    async def delete(self, *, tenant_id: uuid.UUID, email: str) -> None:
        self._owned(tenant_id, email)
        del self.held[email]

    async def set_temporary_password(
        self, *, tenant_id: uuid.UUID, email: str, temporary_password: str
    ) -> None:
        self._owned(tenant_id, email).password = temporary_password

    async def set_enabled(self, *, tenant_id: uuid.UUID, email: str, enabled: bool) -> None:
        self._owned(tenant_id, email).enabled = enabled

    async def list(self, *, tenant_id: uuid.UUID) -> list[LoginAccount]:
        self.calls += 1
        return [
            LoginAccount(email=email, enabled=held.enabled)
            for email, held in self.held.items()
            if held.tenant_id == tenant_id
        ]

    def _owned(self, tenant_id: uuid.UUID, email: str) -> HeldAccount:
        self.calls += 1
        held = self.held.get(email)
        if held is None or held.tenant_id != tenant_id:
            raise NotFoundError(
                "no sign-in account created for this tenant has this email",
                details={"reason_code": "login_account_not_managed"},
            )
        return held
