"""The gateway's settings refuse to start half-configured, and its HTTP face
takes typed commands only (ticket 63 c, f)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import httpx
import pytest
from gateway_fakes import PIC, SET_QUANTITY, FakeDirectory, gateway, targets, token
from pydantic import TypeAdapter

from dw_bravo.approval_token import generate_key_pair
from dw_bravo.contract import (
    BravoTarget,
    CustomerPoRow,
    CustomerPoRows,
    SalesOrderState,
    SoLineState,
    canonical_json,
)
from dw_bravo.sync import SyncPage, SyncQuery, SyncRow
from dw_bravo_gateway.api import create_app
from dw_bravo_gateway.ports import (
    AmbiguousDocumentError,
    BravoUnavailableError,
    BravoUser,
    DocumentNotFoundError,
)
from dw_bravo_gateway.settings import GatewaySettings, SettingsError

pytestmark = pytest.mark.unit

_COMPLETE: dict[str, Any] = {
    "tenant_id": "00000000-0000-0000-0000-00000000a000",
    "database_url": "postgresql+asyncpg://dw_app:x@postgres/dw",
    "uat_host": "bravo",
    "uat_database": "B8_Hitachi_Cable_UAT",
    "uat_read_user": "dw_read",
    "uat_read_password": "r",
    "uat_write_user": "dw_write",
    "uat_write_password": "w",
}
_PRODUCTION: dict[str, Any] = {
    "production_host": "bravo-prod",
    "production_database": "B8_Hitachi_Cable",
    "production_read_user": "dw_read_p",
    "production_read_password": "rp",
    "production_write_user": "dw_write_p",
    "production_write_password": "wp",
}


@pytest.mark.parametrize("profile", ["uat", "production"])
def test_deployed_without_the_approval_key_does_not_start(profile: str) -> None:
    settings = GatewaySettings(profile=profile, **_COMPLETE)

    with pytest.raises(SettingsError, match="APPROVAL_PUBLIC_KEYS"):
        settings.check_startable()


def test_deployed_with_the_key_starts() -> None:
    _, public = generate_key_pair()
    settings = GatewaySettings(
        profile="production", approval_public_keys=json.dumps({"k1": public}), **_COMPLETE
    )

    settings.check_startable()


def test_locally_without_a_key_it_starts_and_verifies_nothing() -> None:
    GatewaySettings(profile="local", **_COMPLETE).check_startable()


@pytest.mark.parametrize(
    "change",
    [
        {"uat_write_password": ""},
        {"database_url": None},
        {"uat_write_user": "dw_read"},
        {"tenant_id": None},
        {"uat_database": ""},
        {"production_host": "bravo-prod"},
        {**_PRODUCTION, "production_write_user": "dw_read_p"},
    ],
    ids=[
        "no_write_password",
        "no_ledger",
        "one_login_for_both",
        "no_tenant",
        "no_database",
        "production_half_configured",
        "production_one_login_for_both",
    ],
)
def test_half_configured_does_not_start(change: dict[str, object]) -> None:
    with pytest.raises(SettingsError):
        GatewaySettings(profile="local", **{**_COMPLETE, **change}).check_startable()


def test_each_target_has_its_own_logins_and_an_absent_one_is_not_there() -> None:
    uat_only = GatewaySettings(profile="local", **_COMPLETE)
    both = GatewaySettings(profile="local", **_COMPLETE, **_PRODUCTION)
    production_only = GatewaySettings(
        profile="local",
        tenant_id=_COMPLETE["tenant_id"],
        database_url=_COMPLETE["database_url"],
        uat_database="B8_Hitachi_Cable_UAT",  # a name alone is no target
        **_PRODUCTION,
    )

    assert set(uat_only.targets()) == {"uat"}
    assert both.targets()["production"].database == "B8_Hitachi_Cable"
    assert both.targets()["uat"].read_user == "dw_read"
    assert set(production_only.targets()) == {"production"}
    production_only.check_startable()


def test_no_target_at_all_does_not_start() -> None:
    settings = GatewaySettings(
        profile="local",
        tenant_id=_COMPLETE["tenant_id"],
        database_url=_COMPLETE["database_url"],
        uat_database="B8_Hitachi_Cable_UAT",
        production_database="B8_Hitachi_Cable",
    )

    with pytest.raises(SettingsError, match="at least one Bravo"):
        settings.check_startable()


_LEGACY = {k.replace("uat_", "bravo_"): v for k, v in _COMPLETE.items()}


def test_the_single_set_before_ticket_85_is_read_as_uat() -> None:
    settings = GatewaySettings(profile="local", **_LEGACY)

    settings.check_startable()
    assert set(settings.targets()) == {"uat"}
    assert settings.targets()["uat"].host == "bravo"


def test_the_old_set_and_the_uat_set_together_do_not_start() -> None:
    settings = GatewaySettings(profile="local", **_LEGACY, uat_host="other", uat_read_user="x")

    with pytest.raises(SettingsError, match="keep the UAT ones only"):
        settings.check_startable()


def test_deployed_never_talks_to_bravo_in_clear() -> None:
    _, public = generate_key_pair()
    settings = GatewaySettings(
        profile="uat",
        approval_public_keys=json.dumps({"k1": public}),
        bravo_encrypt=False,
        **_COMPLETE,
    )

    with pytest.raises(SettingsError, match="encrypted"):
        settings.check_startable()


def _client() -> tuple[httpx.AsyncClient, object]:
    gw = gateway()
    app = create_app(targets(gw))
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw"), gw


def _body(command: object = SET_QUANTITY, **over: object) -> dict[str, object]:
    envelope = json.loads(canonical_json(command))
    return {"command": envelope, "token": token(command), **over}


async def test_a_typed_command_with_its_token_is_written() -> None:
    client, _ = _client()
    async with client:
        response = await client.post("/v1/writes", json=_body())

    assert response.status_code == 200 and response.json()["outcome"] == "written"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda b: b["command"].update(kind="sql.exec"),
        lambda b: b["command"]["content"].update(sql="DELETE FROM B30BizDoc"),
        lambda b: b["command"]["content"]["line"].update(line_rowversion="7D2"),
        lambda b: b.update(tenant_id="00000000-0000-0000-0000-000000000001"),
    ],
    ids=["unknown_kind", "extra_field", "malformed", "a_tenant_named_in_the_request"],
)
async def test_anything_but_a_typed_command_is_refused_before_the_pipeline(mutate: object) -> None:
    client, gw = _client()
    body = _body()
    mutate(body)  # type: ignore[operator]
    async with client:
        response = await client.post("/v1/writes", json=body)

    assert response.status_code == 422
    assert gw.bravo.batches == []  # type: ignore[attr-defined]


async def test_a_body_past_the_limit_is_refused() -> None:
    client, _ = _client()
    async with client:
        response = await client.post("/v1/writes", json=_body(padding="x" * 70_000))

    assert response.status_code == 413


async def test_the_preview_sends_nothing() -> None:
    client, gw = _client()
    async with client:
        response = await client.post("/v1/writes/preview", json=_body())

    assert response.status_code == 200 and response.json()["check"] is None
    assert len(response.json()["statements"]) == 2
    assert gw.bravo.batches == []  # type: ignore[attr-defined]


async def test_no_openapi_document_is_served_by_default() -> None:
    client, _ = _client()
    async with client:
        assert (await client.get("/openapi.json")).status_code == 404
        assert (await client.get("/healthz")).json() == {"status": "ok"}


class _Fingerprints:
    def __init__(self, down: bool = False) -> None:
        self.down = down

    async def fingerprint(self, environment: BravoTarget) -> object:
        from datetime import UTC, datetime

        from dw_bravo.watch import Component, Fingerprint
        from dw_bravo_gateway.ports import BravoUnavailableError

        if self.down:
            raise BravoUnavailableError("no answer")
        return Fingerprint(
            environment, datetime(2026, 11, 21, tzinfo=UTC), (Component("columns", "T", "d"),)
        )


@pytest.mark.parametrize(
    ("source", "asked", "status"),
    [
        (_Fingerprints(), "uat", 200),
        (_Fingerprints(), "production", 404),
        (_Fingerprints(True), "uat", 503),
        (None, "uat", 404),
    ],
    ids=["served", "a_target_not_configured", "bravo_down", "not_wired"],
)
async def test_the_fingerprint_route(source: object, asked: str, status: int) -> None:
    gw = gateway()
    app = create_app(targets(gw, fingerprints=source))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
        response = await c.get(f"/v1/fingerprint/{asked}")

    assert response.status_code == status
    if status == 200:
        assert response.json()["components"][0]["kind"] == "columns"
        assert response.json()["environment"] == asked


def test_an_empty_tenant_from_compose_reads_as_not_configured() -> None:
    settings = GatewaySettings(profile="local", **{**_COMPLETE, "tenant_id": ""})

    with pytest.raises(SettingsError, match="TENANT_ID"):
        settings.check_startable()


# ---------------------------------------------------------------- reads (53)

_SO = SalesOrderState(
    so_id=10,
    so_no="SO-0001",
    lines=(
        SoLineState(
            20, 1, "PRV-1", Decimal("1200.50"), date(2026, 12, 1), "0x00000000000007D2", ""
        ),
    ),
)


@dataclass
class _Orders:
    found: list[SalesOrderState] = field(default_factory=lambda: [_SO])
    down: bool = False

    async def sales_order(self, so_no: str) -> SalesOrderState:
        if self.down:
            raise BravoUnavailableError("no answer")
        held = [o for o in self.found if o.so_no == so_no]
        if not held:
            raise DocumentNotFoundError(so_no)
        if len(held) > 1:
            raise AmbiguousDocumentError(so_no)
        return held[0]

    async def customer_po(self, customer_code: str, po_no: str) -> CustomerPoRows:
        if self.down:
            raise BravoUnavailableError("no answer")
        if (customer_code, po_no) != ("FG1", "PO-1"):
            return CustomerPoRows(())
        return CustomerPoRows(
            (CustomerPoRow("SO-0001", 1, "PRV-1", Decimal(5), Decimal("4.3285"), None, None),)
        )


async def _read(query: dict[str, object], **wired: object) -> httpx.Response:
    gw = gateway()
    app = create_app(targets(gw, **wired))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://gw") as c:
        return await c.post("/v1/reads", json={"query": query})


def _so(no: str = "SO-0001") -> dict[str, object]:
    return {"kind": "so.by_number", "version": 1, "content": {"so_no": no}}


def _user(code: str = "NV001") -> dict[str, object]:
    return {"kind": "user.by_employee_code", "version": 1, "content": {"employee_code": code}}


async def test_an_so_is_read_by_its_number_with_exact_quantities() -> None:
    response = await _read(_so(), orders=_Orders())

    assert response.status_code == 200
    line = response.json()["lines"][0]
    assert line["quantity"] == "1200.50" and line["rowversion"] == "0x00000000000007D2"
    assert TypeAdapter(SalesOrderState).validate_python(response.json()) == _SO


@pytest.mark.parametrize(
    ("orders", "status"),
    [
        (_Orders(found=[]), 404),
        (_Orders(found=[_SO, _SO]), 409),
        (_Orders(down=True), 503),
        (None, 501),
    ],
    ids=["not_found", "two_with_that_number", "bravo_down", "not_wired"],
)
async def test_an_so_read_that_cannot_answer_says_so(orders: object, status: int) -> None:
    assert (await _read(_so(), orders=orders)).status_code == status


async def test_only_active_users_are_named() -> None:
    directory = FakeDirectory(
        users=[PIC, BravoUser(9, "old", "NV001", active=False), BravoUser(7, "x", "NV002", True)]
    )

    response = await _read(_user(), directory=directory)

    assert response.status_code == 200 and response.json() == {"active_user_ids": [PIC.id]}
    down = await _read(_user(), directory=FakeDirectory(down=True))
    assert down.status_code == 503


@pytest.mark.parametrize(
    "query",
    [
        {"kind": "sql.exec", "version": 1, "content": {}},
        {**_so(), "content": {"so_no": "SO-0001", "filter": "1=1"}},
        _user("x" * 25),
        {"kind": "customer.get", "version": 1, "content": {"customer_code": "C1"}},
    ],
    ids=["unknown_kind", "extra_field", "malformed_code", "a_read_not_served_yet"],
)
async def test_a_read_is_a_typed_query_or_nothing(query: dict[str, object]) -> None:
    response = await _read(query, orders=_Orders(), directory=FakeDirectory())

    assert response.status_code in (422, 501)
    assert response.status_code == (501 if query["kind"] == "customer.get" else 422)


async def test_a_customers_po_is_read_with_its_prices_exact_and_none_is_empty() -> None:
    query = {
        "kind": "so.by_customer_po",
        "version": 1,
        "content": {"customer_code": "FG1", "po_no": "PO-1"},
    }

    found = await _read(query, orders=_Orders())
    none = await _read(
        {**query, "content": {"customer_code": "FG1", "po_no": "PO-2"}}, orders=_Orders()
    )

    assert found.status_code == 200 and found.json()["rows"][0]["unit_price"] == "4.3285"
    assert none.status_code == 200 and none.json() == {"rows": []}
    assert (await _read(query, orders=_Orders(down=True))).status_code == 503


class _Sync:
    async def changes(self, query: SyncQuery) -> SyncPage:
        rows = (SyncRow(1, "0x00000000000007D1", {"Code": "CU", "LMEActual": "9123.50"}),)
        return SyncPage(rows if query.after is None else ())


async def test_the_copy_is_read_by_rowversion_from_allowlisted_tables_only() -> None:
    query = {"kind": "sync.changes", "version": 1, "content": {"table": "B20LME"}}

    first = await _read(query, sync=_Sync())
    after = await _read(
        {**query, "content": {"table": "B20LME", "after": "0x00000000000007D1"}}, sync=_Sync()
    )
    other = await _read({**query, "content": {"table": "B00UserList"}}, sync=_Sync())

    assert first.status_code == 200 and first.json()["rows"][0]["data"]["LMEActual"] == "9123.50"
    assert after.json() == {"rows": []}
    assert other.status_code == 422
