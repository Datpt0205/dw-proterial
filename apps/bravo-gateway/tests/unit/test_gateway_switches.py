"""The gateway reads a tenant's switches as `dw_sales.domain.bravo_writes`
writes them, and anything else as off (ticket 63 g)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from dw_bravo_gateway.adapters.postgres import SqlSwitches, switched_on, target_of
from dw_sales.domain.bravo_writes import BravoWrites, BravoWriteSwitch

pytestmark = pytest.mark.unit


def _document(**kinds: BravoWriteSwitch) -> dict[str, object]:
    policy = BravoWrites(
        schema_version="1.0",
        policy_id="sales_bravo_writes",
        policy_version="1.1.0",
        kinds={k.replace("__", ".").replace("_at_", "@"): v for k, v in kinds.items()},
    )
    return policy.model_dump(mode="json")


def test_a_kind_switched_on_by_the_schema_reads_as_on() -> None:
    document = _document(
        so__line__set_quantity_at_1=BravoWriteSwitch(enabled=True, uat_proof="UAT run 1")
    )

    assert switched_on(document, "so.line.set_quantity@1")
    assert not switched_on(document, "so.line.set_confirmed_date@1")


@pytest.mark.parametrize(
    "switch",
    [
        {"enabled": "true", "uat_proof": "run"},
        {"enabled": 1, "uat_proof": "run"},
        {"enabled": True},
        {"enabled": True, "uat_proof": "  "},
        "on",
    ],
    ids=["string", "number", "no_proof", "blank_proof", "not_an_object"],
)
def test_anything_the_schema_would_not_write_reads_as_off(switch: object) -> None:
    assert not switched_on({"kinds": {"so.create@1": switch}}, "so.create@1")


@dataclass
class _Pauses:
    kinds: frozenset[str] = frozenset()

    async def paused(self, tenant_id: uuid.UUID, kind: str) -> bool:
        return kind in self.kinds


@dataclass
class _Version:
    document: dict[str, Any]


@dataclass
class _Lookup:
    version: _Version | None
    asked: list[str]

    async def approved(self, scope: object, key: str) -> _Version | None:
        self.asked.append(key)
        return self.version


async def test_no_approved_version_is_the_platforms_file_every_kind_off() -> None:
    lookup = _Lookup(None, [])
    switches = SqlSwitches(lookup, _Pauses())  # type: ignore[arg-type]

    state = await switches.state(uuid.uuid4(), uuid.uuid4(), "so.line.set_quantity@1")

    assert state == "off" and lookup.asked == ["sales_bravo_writes"]


async def test_a_kind_no_key_covers_is_off_without_asking() -> None:
    lookup = _Lookup(_Version({"kinds": {}}), [])

    state = await SqlSwitches(lookup, _Pauses()).state(uuid.uuid4(), uuid.uuid4(), "po.create@1")  # type: ignore[arg-type]

    assert state == "off" and lookup.asked == []


async def test_an_approved_version_that_switches_the_kind_on_enables_it() -> None:
    document = _document(
        so__line__set_quantity_at_1=BravoWriteSwitch(enabled=True, uat_proof="UAT run 1")
    )
    switches = SqlSwitches(_Lookup(_Version(document), []), _Pauses())  # type: ignore[arg-type]

    assert await switches.state(uuid.uuid4(), uuid.uuid4(), "so.line.set_quantity@1") == "enabled"
    assert await switches.state(uuid.uuid4(), uuid.uuid4(), "so.create@1") == "off"


async def test_a_kind_the_watch_paused_reads_paused_even_when_switched_on() -> None:
    document = _document(
        so__line__set_quantity_at_1=BravoWriteSwitch(enabled=True, uat_proof="UAT run 1")
    )
    switches = SqlSwitches(
        _Lookup(_Version(document), []),  # type: ignore[arg-type]
        _Pauses(frozenset({"so.line.set_quantity@1"})),
    )

    assert await switches.state(uuid.uuid4(), uuid.uuid4(), "so.line.set_quantity@1") == "paused"


# ------------------------------------------------------------ target (85)


async def test_no_approved_version_is_uat() -> None:
    lookup = _Lookup(None, [])

    assert await SqlSwitches(lookup, _Pauses()).target(uuid.uuid4()) == "uat"  # type: ignore[arg-type]
    assert lookup.asked == ["sales_bravo_writes"]


def test_production_as_the_schema_writes_it_reads_as_production() -> None:
    document = BravoWrites(
        schema_version="1.0",
        policy_id="sales_bravo_writes",
        policy_version="1.1.0",
        kinds={},
        target="production",
        target_uat_proof="UAT 2026-12-01 run 3",
    ).model_dump(mode="json")

    assert target_of(document) == "production"


def test_a_version_from_before_the_target_is_uat() -> None:
    assert target_of(_document()) == "uat"
    assert target_of({"kinds": {}}) == "uat"


@pytest.mark.parametrize(
    ("document", "target"),
    [
        ({"target": "production", "target_uat_proof": "UAT run 3"}, "production"),
        ({"target": "production"}, None),
        ({"target": "production", "target_uat_proof": "  "}, None),
        ({"target": "Production", "target_uat_proof": "run"}, None),
        ({"target": None}, None),
        ({"target": ["production"]}, None),
    ],
    ids=["with_proof", "no_proof", "blank_proof", "another_spelling", "null", "a_list"],
)
def test_production_reads_only_as_the_schema_writes_it(document: object, target: object) -> None:
    assert target_of(document) == target  # type: ignore[arg-type]


async def test_the_target_is_read_from_the_approved_version() -> None:
    document = {"target": "production", "target_uat_proof": "UAT run 3", "kinds": {}}
    switches = SqlSwitches(_Lookup(_Version(document), []), _Pauses())  # type: ignore[arg-type]

    assert await switches.target(uuid.uuid4()) == "production"
