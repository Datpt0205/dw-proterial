"""Sales' HTTP adapter to the Bravo gateway (ADR 0027 decision 1, ticket 53).

The only way Sales reaches Bravo: typed envelopes from `dw_bravo.contract`
to the gateway on DW's internal network, never a driver or a connection
string. A read carries no token; a write carries the approval token the
decision signed, and the gateway trusts nothing else.

What it answers:
- `BravoOrdersPort`: an SO by its number (`so.by_number`);
- `BravoUsersPort`: the active Bravo users for an employee code, and the
  count of them for ticket 64's `BravoPeoplePort` (`user.by_employee_code`).
  An e-mail's employee codes are not read yet: that read waits on the
  employee record's columns (ticket 50), so it answers "could not ask";
- `BravoGatewayPort`: a write, with the gateway's answer;
- `BravoCustomerPoPort`: a customer's PO as Bravo holds it, for the
  read-back (`so.by_customer_po`, ticket 51);
- `dw_bravo.sync.SyncSource`: the facts DW copies (`sync.changes`, ticket
  50), for the `bravo_sync` lane of this client's tenant.

No answer, a timeout or a 5xx is "could not ask" (`BravoUnreachableError`),
never a pass.

**One tenant.** A gateway reaches one tenant's Bravo, and the client is
built for that tenant (`tenant_id`): asked for any other tenant it answers
"not connected" and sends nothing, so another tenant's case can never read
this Bravo's orders, prices or users. The gateway refuses another tenant's
write token itself.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import TypeAdapter, ValidationError

from dw_bravo.contract import (
    BravoUserQuery,
    BravoUsers,
    CustomerPoQuery,
    CustomerPoRows,
    SalesOrderQuery,
    SalesOrderState,
    canonical_json,
)
from dw_bravo.sync import SyncPage, SyncQuery, SyncUnavailableError
from dw_kernel.errors import ConflictError
from dw_sales.application.bravo_line_writes import (
    BravoSo,
    BravoSoLine,
    BravoUnreachableError,
    GatewayAnswer,
)
from dw_sales.application.identity_links import BravoPeopleUnavailableError
from dw_sales.application.ports import SalesScope
from dw_sales.domain.bravo_sales_orders import BravoSalesOrder, BravoSoRow


@dataclass(frozen=True)
class BravoGatewayClient:
    client: httpx.AsyncClient
    base_url: str
    tenant_id: uuid.UUID
    read_timeout_seconds: float = 15.0
    # A write waits its turn behind the document's lock and the pace.
    write_timeout_seconds: float = 60.0

    async def _post(self, path: str, body: dict[str, Any], timeout: float) -> httpx.Response:
        try:
            response = await self.client.post(
                f"{self.base_url.rstrip('/')}{path}", json=body, timeout=timeout
            )
        except httpx.HTTPError as failed:
            raise BravoUnreachableError(type(failed).__name__) from None
        if response.status_code >= 500:
            raise BravoUnreachableError(f"gateway answered {response.status_code}")
        return response

    def _for(self, tenant_id: uuid.UUID) -> None:
        if tenant_id != self.tenant_id:
            raise BravoUnreachableError("this gateway reaches another tenant's Bravo")

    async def _read(self, query: object) -> httpx.Response:
        envelope = json.loads(canonical_json(query))
        return await self._post("/v1/reads", {"query": envelope}, self.read_timeout_seconds)

    async def sales_order(self, tenant_id: uuid.UUID, so_no: str) -> BravoSo | None:
        self._for(tenant_id)
        response = await self._read(SalesOrderQuery(so_no=so_no))
        if response.status_code == 404:
            return None
        if response.status_code == 409:
            raise ConflictError(
                "Bravo có nhiều SO cùng số này: không chọn thay", details={"so_no": so_no}
            )
        state = _parsed(SalesOrderState, response)
        return BravoSo(
            so_id=state.so_id,
            so_no=state.so_no,
            lines=tuple(
                BravoSoLine(
                    line_id=x.line_id,
                    po_line=x.po_line,
                    item_code=x.item_code,
                    quantity=x.quantity,
                    confirmed_date=x.confirmed_date,
                    rowversion=x.rowversion,
                    cancel_state=x.cancel_state,
                )
                for x in state.lines
            ),
        )

    async def by_customer_po(
        self, scope: SalesScope, customer_code: str, po_no: str
    ) -> tuple[BravoSalesOrder, str] | None:
        """ticket 51's `BravoCustomerPoPort`. The gateway reaches one tenant's
        Bravo: ``scope`` is the caller's, checked against it, and not sent."""
        self._for(scope.tenant_id.value)
        response = await self._read(CustomerPoQuery(customer_code=customer_code, po_no=po_no))
        found = _parsed(CustomerPoRows, response)
        if not found.rows:
            return None
        digest = hashlib.sha256(response.content).hexdigest()
        order = BravoSalesOrder(
            customer_code=customer_code,
            po_no=po_no,
            rows=tuple(
                BravoSoRow(
                    row=n,
                    so_no=r.so_no,
                    customer_code=customer_code,
                    po_no=po_no,
                    po_line=r.po_line,
                    item_code=r.item_code,
                    quantity=r.quantity,
                    unit_price=r.unit_price,
                    requested_date=r.requested_date,
                    confirmed_date=r.confirmed_date,
                )
                for n, r in enumerate(found.rows, start=1)
            ),
        )
        return order, digest

    async def bravo_user_ids(self, tenant_id: uuid.UUID, employee_code: str) -> tuple[int, ...]:
        self._for(tenant_id)
        response = await self._read(BravoUserQuery(employee_code=employee_code))
        return _parsed(BravoUsers, response).active_user_ids

    # ---- ticket 64's `BravoPeoplePort`

    async def active_users(self, tenant_id: uuid.UUID, employee_code: str) -> int:
        try:
            return len(await self.bravo_user_ids(tenant_id, employee_code))
        except BravoUnreachableError:
            raise BravoPeopleUnavailableError() from None

    async def codes_for_email(self, tenant_id: uuid.UUID, email: str) -> Sequence[str]:
        raise BravoPeopleUnavailableError()

    # ---- ticket 50's `dw_bravo.sync.SyncSource`, for the lane of this
    # client's own tenant

    async def changes(self, query: SyncQuery) -> SyncPage:
        try:
            return _parsed(SyncPage, await self._read(query))
        except BravoUnreachableError as down:
            raise SyncUnavailableError(str(down)) from None

    # ---- writes

    async def write(self, kind: str, content: dict[str, Any], token: str) -> GatewayAnswer:
        name, _, version = kind.rpartition("@")
        envelope = {"kind": name, "version": int(version), "content": content}
        response = await self._post(
            "/v1/writes", {"command": envelope, "token": token}, self.write_timeout_seconds
        )
        if response.status_code != 200:
            # The gateway refused the envelope itself (422): nothing was written.
            return GatewayAnswer("refused", "contract", f"gateway_{response.status_code}")
        body = response.json()
        try:
            return GatewayAnswer(
                outcome=str(body["outcome"]),
                check=body.get("check"),
                reason=body.get("reason"),
                warnings=tuple(str(w) for w in body.get("warnings") or ()),
                differences=tuple(str(d) for d in body.get("differences") or ()),
            )
        except (KeyError, TypeError):
            raise BravoUnreachableError("an answer the gateway does not give") from None


def _parsed[T](shape: type[T], response: httpx.Response) -> T:
    if response.status_code != 200:
        raise BravoUnreachableError(f"gateway answered {response.status_code}")
    try:
        return TypeAdapter(shape).validate_python(response.json())
    except (ValidationError, ValueError):
        raise BravoUnreachableError("an answer the contract does not allow") from None
