"""The gateway's settings refuse to start half-configured, and its HTTP face
takes typed commands only (ticket 63 c, f)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from gateway_fakes import SET_QUANTITY, gateway, token

from dw_bravo.approval_token import generate_key_pair
from dw_bravo.contract import canonical_json
from dw_bravo_gateway.api import create_app
from dw_bravo_gateway.settings import GatewaySettings, SettingsError

pytestmark = pytest.mark.unit

_COMPLETE: dict[str, Any] = {
    "tenant_id": "00000000-0000-0000-0000-00000000a000",
    "database_url": "postgresql+asyncpg://dw_app:x@postgres/dw",
    "bravo_host": "bravo",
    "bravo_database": "B8",
    "bravo_read_user": "dw_read",
    "bravo_read_password": "r",
    "bravo_write_user": "dw_write",
    "bravo_write_password": "w",
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
        {"bravo_write_password": ""},
        {"database_url": None},
        {"bravo_write_user": "dw_read"},
        {"tenant_id": None},
    ],
    ids=["no_write_password", "no_ledger", "one_login_for_both", "no_tenant"],
)
def test_half_configured_does_not_start(change: dict[str, object]) -> None:
    with pytest.raises(SettingsError):
        GatewaySettings(profile="local", **{**_COMPLETE, **change}).check_startable()


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
    app = create_app(gw.pipeline)
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
