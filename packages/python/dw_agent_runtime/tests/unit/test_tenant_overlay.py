"""Per-tenant artifacts: a customer's own version wins, everyone else's does not.

This is the axis the whole "one deployment, many customers, no fork" claim rests
on, so it is tested at the registries rather than only at the data structure:
what matters is that `resolve` on the real objects reads the right layer, and
that a tenant with no override still gets the platform's.

The last test is the one that would be a breach.
"""

from __future__ import annotations

import uuid

import pytest

from dw_agent_runtime.model.profiles import ModelProfile, ModelProfileRegistry
from dw_agent_runtime.model.prompts import PromptArtifact, PromptRegistry
from dw_agent_runtime.registry import ConfigError
from dw_kernel.errors import NotFoundError
from dw_kernel.overlay import TenantOverlay

pytestmark = pytest.mark.unit

ACME = uuid.UUID("11111111-1111-5111-8111-111111111111")
OTHER = uuid.UUID("22222222-2222-5222-8222-222222222222")


def _prompt(text: str) -> PromptArtifact:
    return PromptArtifact(
        schema_version="1.0",
        prompt_id="platform.greeting",
        version="1.0.0",
        system=text,
        template="{name}",
        variables=frozenset({"name"}),
    )


def _profile(profile_id: str, model: str) -> ModelProfile:
    return ModelProfile.model_validate(
        {
            "schema_version": "1.0",
            "profile_id": profile_id,
            "routing_policy_version": "1.0.0",
            "structured_extraction": {"provider": "mock", "model": model},
            "reasoning": {"provider": "mock", "model": model},
        }
    )


def test_a_tenant_without_an_override_reads_the_platform_artifact() -> None:
    registry = PromptRegistry()
    registry.register(_prompt("platform wording"))

    rendered = registry.render("platform.greeting", "1.0.0", {"name": "An"}, tenant_id=ACME)

    assert rendered.system == "platform wording"


def test_a_tenants_own_artifact_wins_over_the_platforms() -> None:
    registry = PromptRegistry()
    registry.register(_prompt("platform wording"))
    registry.register(_prompt("acme wording"), tenant_id=ACME)

    assert (
        registry.render("platform.greeting", "1.0.0", {"name": "An"}, tenant_id=ACME).system
        == "acme wording"
    )


def test_one_tenants_override_is_invisible_to_another() -> None:
    """The breach this whole mechanism must not become.

    An override is customer data — their wording, their rules, sometimes their
    model contract. A lookup that fell through to *another* tenant's layer would
    leak it, and the fall-through is exactly the feature, so it is asserted.
    """
    registry = PromptRegistry()
    registry.register(_prompt("platform wording"))
    registry.register(_prompt("acme wording"), tenant_id=ACME)

    assert (
        registry.render("platform.greeting", "1.0.0", {"name": "An"}, tenant_id=OTHER).system
        == "platform wording"
    )


def test_a_tenant_may_define_what_the_platform_does_not() -> None:
    registry = ModelProfileRegistry()
    registry.register(_profile("acme_private", "gpt-on-their-contract"), tenant_id=ACME)

    assert registry.resolve("acme_private", tenant_id=ACME).profile_id == "acme_private"
    with pytest.raises(NotFoundError):
        registry.resolve("acme_private")
    with pytest.raises(NotFoundError):
        registry.resolve("acme_private", tenant_id=OTHER)


def test_overriding_is_allowed_but_defining_twice_in_one_layer_is_not() -> None:
    """Two files claiming one version inside a layer is a mistake, not an override."""
    registry = ModelProfileRegistry()
    registry.register(_profile("balanced", "a"))
    registry.register(_profile("balanced", "b"), tenant_id=ACME)  # the feature

    with pytest.raises(ConfigError, match="already registered"):
        registry.register(_profile("balanced", "c"), tenant_id=ACME)
    with pytest.raises(ConfigError, match="already registered"):
        registry.register(_profile("balanced", "d"))


def test_the_platform_layer_is_readable_on_its_own() -> None:
    """An operator's inventory must not change with whoever is asking.

    The release manifest and `/v1/integrations` answer "what can this deployment
    do", which is a property of the deployment.
    """
    overlay: TenantOverlay[str, str] = TenantOverlay()
    overlay.put("a", "platform")
    overlay.put("a", "acme", tenant_id=ACME)
    overlay.put("b", "acme only", tenant_id=ACME)

    assert sorted(overlay.platform_values()) == ["platform"]
