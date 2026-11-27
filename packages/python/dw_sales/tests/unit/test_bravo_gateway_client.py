"""Sales' client speaks the gateway's own envelope (ticket 53): run against
the gateway's real HTTP face in-process, the reads parse into Sales' types and
a write arrives as the very command DW hashed and signed."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from dw_bravo.contract import (
    CustomerPoRow,
    CustomerPoRows,
    SalesOrderState,
    SoLineState,
    content_hash,
)
from dw_bravo.sync import SyncPage, SyncQuery, SyncRow, SyncUnavailableError
from dw_bravo_gateway.api import create_app
from dw_bravo_gateway.pipeline import WriteResult
from dw_bravo_gateway.ports import BravoUser, DocumentNotFoundError
from dw_bravo_gateway.targets import TargetBravo, Targets
from dw_kernel.ids import TenantId, WorkspaceId
from dw_sales.adapters.bravo_contract import BravoContract
from dw_sales.adapters.bravo_gateway_client import BravoGatewayClient
from dw_sales.application.bravo_line_writes import (
    BravoSo,
    BravoUnreachableError,
    ConfirmedDateChange,
)
from dw_sales.application.ports import SalesScope

pytestmark = pytest.mark.unit

TENANT = uuid.UUID(int=0xA)
SCOPE = SalesScope(TenantId(TENANT), WorkspaceId(uuid.UUID(int=0xB)))

SO = SalesOrderState(
    so_id=10,
    so_no="SO-1",
    lines=(
        SoLineState(20, 1, "PRV-1", Decimal("12.5"), date(2026, 12, 1), "0x00000000000007D2", ""),
    ),
)


@dataclass
class _Bravo:
    async def sales_order(self, so_no: str) -> SalesOrderState:
        if so_no != SO.so_no:
            raise DocumentNotFoundError(so_no)
        return SO

    async def customer_po(self, customer_code: str, po_no: str) -> CustomerPoRows:
        if po_no != "PO-1":
            return CustomerPoRows(())
        return CustomerPoRows(
            (
                CustomerPoRow(
                    "SO-1", 1, "PRV-1", Decimal(5), Decimal("4.3285"), None, date(2026, 12, 1)
                ),
            )
        )

    async def users_by_employee_code(self, employee_code: str) -> list[BravoUser]:
        return [
            BravoUser(2413, "pic", employee_code, True),
            BravoUser(9, "x", employee_code, False),
        ]


@dataclass
class _Pipeline:
    received: list[tuple[object, str]] = field(default_factory=list)

    async def execute(self, command: object, token: str) -> WriteResult:
        self.received.append((command, token))
        return WriteResult("refused", "switch", "write_kind_off")


@dataclass
class _Switches:
    target_: str | None = "uat"

    async def target(self, tenant_id: uuid.UUID) -> str | None:
        return self.target_


def _targets(pipeline: object, current: str | None = "uat", **reads: object) -> Targets:
    return Targets(TENANT, _Switches(current), {"uat": TargetBravo(pipeline, **reads)})  # type: ignore[arg-type]


def _client(pipeline: _Pipeline | None = None) -> BravoGatewayClient:
    app = create_app(_targets(pipeline or _Pipeline(), orders=_Bravo(), directory=_Bravo()))
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))
    return BravoGatewayClient(http, "http://gateway", TENANT)


async def test_an_so_read_through_the_gateway_is_sales_own_type() -> None:
    so = await _client().sales_order(TENANT, "SO-1")

    assert isinstance(so, BravoSo) and so.lines[0].quantity == Decimal("12.5")
    assert so.target == "uat"  # the Bravo the gateway read it from (ticket 85)
    assert await _client().sales_order(TENANT, "SO-404") is None


async def test_an_so_answer_that_names_no_bravo_is_could_not_ask() -> None:
    def unnamed(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"so_id": 10, "so_no": "SO-1", "lines": []})

    def another(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"so_id": 10, "so_no": "SO-1", "lines": []},
            headers={"Bravo-Target": "staging"},
        )

    for handler in (unnamed, another):
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(BravoUnreachableError):
            await BravoGatewayClient(http, "http://gateway", TENANT).sales_order(TENANT, "SO-1")


async def test_a_target_without_logins_is_could_not_ask() -> None:
    app = create_app(_targets(_Pipeline(), current="production", orders=_Bravo()))
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))

    with pytest.raises(BravoUnreachableError):
        await BravoGatewayClient(http, "http://gateway", TENANT).sales_order(TENANT, "SO-1")


async def test_only_active_bravo_users_are_counted() -> None:
    assert await _client().bravo_user_ids(TENANT, "NV001") == (2413,)
    assert await _client().active_users(TENANT, "NV001") == 1


async def test_a_write_arrives_as_the_command_dw_hashed() -> None:
    pipeline = _Pipeline()
    so = await _client().sales_order(TENANT, "SO-1")
    assert so is not None
    prepared = BravoContract().prepare(
        ConfirmedDateChange(field="confirmed_date", value=date(2026, 12, 8)), so, so.lines[0]
    )

    answer = await _client(pipeline).write(prepared.kind, prepared.content, "a.token")

    [(command, token)] = pipeline.received
    assert content_hash(command) == prepared.content_hash and token == "a.token"
    assert (answer.outcome, answer.check, answer.reason) == ("refused", "switch", "write_kind_off")


async def test_a_gateway_that_does_not_answer_is_could_not_ask() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    client = BravoGatewayClient(
        httpx.AsyncClient(transport=httpx.MockTransport(down)), "http://g", TENANT
    )

    with pytest.raises(BravoUnreachableError):
        await client.sales_order(TENANT, "SO-1")
    with pytest.raises(BravoUnreachableError):
        await client.write("so.line.set_quantity@1", {}, "t")


async def test_an_answer_outside_the_contract_is_could_not_ask() -> None:
    def odd(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = {"so_id": "x", "so_no": "SO-1", "lines": []}
        return httpx.Response(200, json=body)

    client = BravoGatewayClient(
        httpx.AsyncClient(transport=httpx.MockTransport(odd)), "http://g", TENANT
    )

    with pytest.raises(BravoUnreachableError):
        await client.sales_order(TENANT, "SO-1")


async def test_a_gateway_error_on_a_write_is_retried_not_recorded_as_refused() -> None:
    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "could not read Bravo"})

    client = BravoGatewayClient(
        httpx.AsyncClient(transport=httpx.MockTransport(failing)), "http://g", TENANT
    )

    with pytest.raises(BravoUnreachableError):
        await client.write("so.line.set_quantity@1", {}, "t")


async def test_a_customers_po_read_through_the_gateway_is_the_read_backs_own_type() -> None:
    found = await _client().by_customer_po(SCOPE, "FG1", "PO-1")

    assert found is not None
    order, digest = found
    assert order.so_no == "SO-1" and len(digest) == 64
    assert order.rows[0].unit_price == Decimal("4.3285")
    assert order.rows[0].confirmed_date == date(2026, 12, 1)
    assert await _client().by_customer_po(SCOPE, "FG1", "PO-2") is None


async def test_another_tenant_is_not_connected_and_nothing_is_sent() -> None:
    """The gateway reaches one tenant's Bravo: another tenant's case reads
    none of its orders, prices or users."""
    sent: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"active_user_ids": [1]})

    client = BravoGatewayClient(
        httpx.AsyncClient(transport=httpx.MockTransport(record)), "http://g", TENANT
    )
    other = uuid.UUID(int=0xC)

    with pytest.raises(BravoUnreachableError):
        await client.sales_order(other, "SO-1")
    with pytest.raises(BravoUnreachableError):
        await client.bravo_user_ids(other, "NV001")
    with pytest.raises(BravoUnreachableError):
        await client.by_customer_po(SalesScope(TenantId(other), SCOPE.workspace_id), "FG1", "PO-1")
    assert sent == []


async def test_the_sync_lane_reads_its_page_and_a_silent_gateway_is_could_not_read() -> None:
    class _Sync:
        async def changes(self, query: SyncQuery) -> SyncPage:
            return SyncPage((SyncRow(3, "0x0000000000000003", {"Code": "X"}),))

    app = create_app(_targets(_Pipeline(), sync=_Sync()))
    client = BravoGatewayClient(
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app)), "http://g", TENANT
    )

    page = await client.changes(SyncQuery("B20BlackList"))

    assert page.rows[0].row_id == 3

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    silent = BravoGatewayClient(
        httpx.AsyncClient(transport=httpx.MockTransport(down)), "http://g", TENANT
    )
    with pytest.raises(SyncUnavailableError):
        await silent.changes(SyncQuery("B20BlackList"))


async def test_the_targets_are_the_gateways_own_answer() -> None:
    answer = await _client().targets(TENANT)

    assert (answer.connected, answer.current, answer.uat, answer.production) == (
        True,
        "uat",
        True,
        False,
    )
    with pytest.raises(BravoUnreachableError):
        await _client().targets(uuid.uuid4())  # another tenant's: nothing sent


async def test_the_targets_of_no_gateway_read_as_not_connected() -> None:
    from dw_sales.application.bravo_line_writes import BravoNotConnected, BravoTargets

    class _Open:
        async def require(self, *args: object, **kwargs: object) -> None:
            return None

    caller = SimpleNamespace(tenant_id=TENANT, workspace_id=uuid.UUID(int=0xB))
    view = await BravoTargets(_Open(), BravoNotConnected()).now(caller)  # type: ignore[arg-type]

    assert (view.connected, view.current, view.uat, view.production) == (
        False,
        None,
        False,
        False,
    )
