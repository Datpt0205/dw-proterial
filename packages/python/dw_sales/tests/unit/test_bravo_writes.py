"""`sales_bravo_writes` (ticket 63 g): every Bravo write off until a person
switches it on with its UAT proof, and the kinds are the gateway's."""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from dw_bravo.contract import BRAVO_TARGETS, WRITE_KINDS
from dw_sales.domain.bravo_writes import BravoTarget, BravoWriteKind, BravoWrites, BravoWriteSwitch

pytestmark = pytest.mark.unit

PLATFORM = Path(__file__).resolve().parents[5] / "configs" / "policies"


def test_the_kinds_are_the_gateway_contracts_so_kinds() -> None:
    # The second list this module cannot avoid (it may not import dw_bravo):
    # a kind added to the contract and not here, or here and not there, is red.
    assert set(get_args(BravoWriteKind)) == {k for k in WRITE_KINDS if k.startswith("so.")}


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_the_platform_switches_every_kind_off_on_uat(version: str) -> None:
    policy = BravoWrites.model_validate(
        yaml.safe_load((PLATFORM / f"sales_bravo_writes@{version}.yaml").read_bytes())
    )

    assert set(policy.kinds) == set(get_args(BravoWriteKind))
    assert not any(policy.enabled(kind) for kind in get_args(BravoWriteKind))
    assert policy.target == "uat"


def test_a_kind_is_switched_on_only_with_its_uat_proof() -> None:
    with pytest.raises(ValidationError):
        BravoWriteSwitch(enabled=True)
    with pytest.raises(ValidationError):
        BravoWriteSwitch(enabled=True, uat_proof="   ")

    assert BravoWriteSwitch(enabled=True, uat_proof="UAT 2026-12-01 replay R1").enabled


def test_a_kind_the_document_does_not_name_is_off() -> None:
    policy = BravoWrites(
        schema_version="1.0",
        policy_id="sales_bravo_writes",
        policy_version="1.1.0",
        kinds={"so.line.set_quantity@1": BravoWriteSwitch(enabled=True, uat_proof="run 1")},
    )

    assert policy.enabled("so.line.set_quantity@1")
    assert not policy.enabled("so.line.set_confirmed_date@1")
    assert not policy.enabled("so.line.set_quantity@2")


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValidationError):
        BravoWrites.model_validate(
            {
                "schema_version": "1.0",
                "policy_id": "sales_bravo_writes",
                "policy_version": "1.1.0",
                "kinds": {"so.delete@1": {"enabled": False}},
            }
        )


# ------------------------------------------------------------ target (85)


def _writes(**over: object) -> BravoWrites:
    return BravoWrites.model_validate(
        {
            "schema_version": "1.0",
            "policy_id": "sales_bravo_writes",
            "policy_version": "1.1.0",
            "kinds": {},
            **over,
        }
    )


def test_the_targets_are_the_gateway_contracts() -> None:
    assert get_args(BravoTarget) == BRAVO_TARGETS


def test_the_target_defaults_to_uat() -> None:
    assert _writes().target == "uat"


@pytest.mark.parametrize("proof", [None, "   "], ids=["none", "blank"])
def test_production_is_named_only_with_its_uat_proof(proof: str | None) -> None:
    with pytest.raises(ValidationError):
        _writes(target="production", target_uat_proof=proof)

    assert _writes(target="production", target_uat_proof="UAT 2026-12-01 run 3").target == (
        "production"
    )


def test_a_target_the_gateway_does_not_know_is_refused() -> None:
    with pytest.raises(ValidationError):
        _writes(target="staging")
