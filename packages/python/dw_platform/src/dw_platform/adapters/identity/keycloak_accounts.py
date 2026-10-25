"""`LoginAccountsPort` on Keycloak's admin REST API.

The API signs in as the realm's `dw-accounts` client (client credentials),
whose service account holds `manage-users`, `view-users` and `query-users` of
`realm-management` and nothing else (`infra/keycloak/dw-realm.json`). That is
enough to reset the password of ANY user in the realm, a realm administrator
included (measured on 26.7.2), so the tenant check below is the only thing
between one tenant's admin and everyone else's account; it is not a nicety.

Ownership: an account this adapter creates carries `dw_tenant_id`. The realm's
user profile lets only an administrator write an attribute it does not
declare (`unmanagedAttributePolicy: ADMIN_EDIT`), so a person cannot set it on
their own account; without that policy Keycloak drops the attribute silently
and every later call here answers NotFoundError (fails closed). Every call but
`create` finds the account by email and refuses one whose `dw_tenant_id` is
not the caller's tenant.

Measured on 26.7.2 (2026-10-25): a duplicate email answers 409; a temporary
credential sets `UPDATE_PASSWORD`; a partial `PUT {"enabled": ...}` keeps the
other fields; the realm's password policy refuses a short password with 400.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx

from dw_kernel.errors import ConflictError, DomainError, InfrastructureError, NotFoundError
from dw_platform.application.member_accounts import LoginAccount

TENANT_ATTRIBUTE = "dw_tenant_id"
# More accounts than one tenant creates by hand; a page past it is a sign of
# something else, and the list says what it holds rather than failing.
_LIST_MAX = 2000


def _names(display_name: str) -> dict[str, str]:
    # Vietnamese order: family name first, given name last.
    *family, given = display_name.split()
    return {"firstName": given, "lastName": " ".join(family) or given}


@dataclass
class KeycloakLoginAccounts:
    """Implements `LoginAccountsPort`.

    ``base_url`` is Keycloak as the API reaches it (inside compose,
    ``http://keycloak:8080``), not the browser-facing issuer.
    """

    base_url: str
    realm: str
    client_id: str
    client_secret: str
    timeout_seconds: float = 15.0
    _token: str | None = field(default=None, init=False, repr=False)
    _token_expires: float = field(default=0.0, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def create(
        self, *, tenant_id: uuid.UUID, email: str, display_name: str, temporary_password: str
    ) -> None:
        body = {
            "username": email,
            "email": email,
            # The admin vouches for the address: the realm has no mail server,
            # and DW links a sign-in to its person by verified email only.
            "emailVerified": True,
            "enabled": True,
            **_names(display_name),
            "attributes": {TENANT_ATTRIBUTE: [str(tenant_id)]},
            "credentials": [{"type": "password", "value": temporary_password, "temporary": True}],
        }
        response = await self._call("POST", "/users", json=body)
        if response.status_code == 409:
            raise ConflictError(
                "Email này đã có tài khoản đăng nhập. Nếu người này đã đăng nhập được, dùng"
                ' "Cấp quyền" với email đó.',
                details={"reason_code": "login_account_exists"},
            )
        _raise_for(response)

    async def delete(self, *, tenant_id: uuid.UUID, email: str) -> None:
        user_id = await self._owned_id(tenant_id, email)
        _raise_for(await self._call("DELETE", f"/users/{user_id}"))

    async def set_temporary_password(
        self, *, tenant_id: uuid.UUID, email: str, temporary_password: str
    ) -> None:
        user_id = await self._owned_id(tenant_id, email)
        _raise_for(
            await self._call(
                "PUT",
                f"/users/{user_id}/reset-password",
                json={"type": "password", "value": temporary_password, "temporary": True},
            )
        )

    async def set_enabled(self, *, tenant_id: uuid.UUID, email: str, enabled: bool) -> None:
        user_id = await self._owned_id(tenant_id, email)
        _raise_for(await self._call("PUT", f"/users/{user_id}", json={"enabled": enabled}))
        if not enabled:
            # A disabled account cannot refresh, but its open sessions would
            # still show as live in the console until they time out.
            _raise_for(await self._call("POST", f"/users/{user_id}/logout"))

    async def list(self, *, tenant_id: uuid.UUID) -> list[LoginAccount]:
        response = await self._call(
            "GET",
            "/users",
            params={
                "q": f"{TENANT_ATTRIBUTE}:{tenant_id}",
                "briefRepresentation": "true",
                "max": str(_LIST_MAX),
            },
        )
        _raise_for(response)
        return [
            LoginAccount(email=str(u["email"]).lower(), enabled=bool(u.get("enabled")))
            for u in response.json()
            if u.get("email")
        ]

    async def _owned_id(self, tenant_id: uuid.UUID, email: str) -> str:
        response = await self._call(
            "GET",
            "/users",
            params={"email": email, "exact": "true", "briefRepresentation": "false"},
        )
        _raise_for(response)
        for user in response.json():
            owners: list[str] = (user.get("attributes") or {}).get(TENANT_ATTRIBUTE, [])
            same_email = str(user.get("email", "")).lower() == email.lower()
            if same_email and str(tenant_id) in owners:
                return str(user["id"])
        raise NotFoundError(
            "Tài khoản đăng nhập của người này không do DW tạo cho công ty bạn (ví dụ đăng"
            " nhập qua AD), nên đổi ở nơi quản lý tài khoản đó.",
            details={"reason_code": "login_account_not_managed"},
        )

    async def _call(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        token = await self._access_token()
        url = f"{self.base_url.rstrip('/')}/admin/realms/{self.realm}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                return await client.request(
                    method, url, headers={"Authorization": f"Bearer {token}"}, **kwargs
                )
        except httpx.HTTPError as exc:
            raise InfrastructureError(
                "Không kết nối được máy chủ đăng nhập. Hãy thử lại sau.",
                details={"reason": type(exc).__name__},
            ) from exc

    async def _access_token(self) -> str:
        async with self._lock:
            if self._token is not None and time.monotonic() < self._token_expires:
                return self._token
            url = f"{self.base_url.rstrip('/')}/realms/{self.realm}/protocol/openid-connect/token"
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        url,
                        data={
                            "grant_type": "client_credentials",
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                        },
                    )
            except httpx.HTTPError as exc:
                raise InfrastructureError(
                    "Không kết nối được máy chủ đăng nhập. Hãy thử lại sau.",
                    details={"reason": type(exc).__name__},
                ) from exc
            if response.status_code != 200:
                # Wrong secret or a realm without the client: an operator's fix.
                raise InfrastructureError(
                    "Máy chủ chưa đăng nhập được vào Keycloak (cấu hình dw-accounts sai)."
                    " Hãy báo FPT.",
                    details={"status": response.status_code},
                )
            payload = response.json()
            self._token = str(payload["access_token"])
            # Renew 30 s early, so a call never leaves with a token about to lapse.
            self._token_expires = time.monotonic() + max(int(payload["expires_in"]) - 30, 0)
            return self._token


def _raise_for(response: httpx.Response) -> None:
    if response.is_success:
        return
    if response.status_code == 400:
        # The realm refused the value (its password policy, a malformed field).
        raise DomainError(
            "Máy chủ đăng nhập từ chối thay đổi này.",
            details={"reason_code": "login_account_refused"},
        )
    raise InfrastructureError(
        "Máy chủ đăng nhập từ chối yêu cầu. Hãy báo FPT.",
        details={"status": response.status_code},
    )
