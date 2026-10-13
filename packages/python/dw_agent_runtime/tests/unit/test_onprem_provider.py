"""The `onprem` provider: a model server the deployment runs itself.

Its endpoint is guarded like the gateway's: localhost only outside a deployed
profile, and a deployed server only when the deployment names its host. The
`onprem` profile keeps every route on that server, thinking off, and has no
fallback, because a step routed there is one whose input may not leave.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dw_agent_runtime.adapters.model_stack import ModelProviderConfig, build_model_adapters
from dw_agent_runtime.adapters.openai_compatible import OpenAICompatibleAdapter
from dw_agent_runtime.model.profiles import ModelProfile, Provider
from dw_kernel.net_guard import OutboundUrlError

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[5]
FIXTURES = REPO_ROOT / "evals" / "fixtures" / "mock_model"
GATEWAY = "https://gateway.example/v1"


def _config(
    *, deployed: bool, onprem: str | None, allowed: tuple[str, ...] = ()
) -> ModelProviderConfig:
    return ModelProviderConfig(
        provider="openai_compatible",
        model_profile="onprem",
        profile="production" if deployed else "local",
        is_deployed=deployed,
        openai_api_key="sk-test",
        openai_base_url=GATEWAY,
        # The gateway's own host is allow-listed so the test resolves no name.
        outbound_allowed_hosts=("gateway.example", *allowed),
        onprem_base_url=onprem,
    )


def test_a_local_profile_reaches_a_model_server_on_localhost() -> None:
    adapters = build_model_adapters(
        _config(deployed=False, onprem="http://localhost:11434/v1"), mock_fixtures_dir=FIXTURES
    )
    onprem = adapters[Provider.ONPREM]
    assert isinstance(onprem, OpenAICompatibleAdapter)
    assert (onprem.base_url, onprem.provider_name) == ("http://localhost:11434/v1", "onprem")
    # Its own adapter: the gateway's stays where it was.
    gateway = adapters[Provider.OPENAI_COMPATIBLE]
    assert isinstance(gateway, OpenAICompatibleAdapter)
    assert gateway.base_url == GATEWAY


def test_a_deployed_profile_refuses_localhost() -> None:
    with pytest.raises(OutboundUrlError):
        build_model_adapters(
            _config(deployed=True, onprem="http://localhost:11434/v1"), mock_fixtures_dir=FIXTURES
        )


def test_a_deployed_profile_reaches_the_server_it_names() -> None:
    adapters = build_model_adapters(
        _config(
            deployed=True,
            onprem="http://llm.plant.internal:8000/v1",
            allowed=("llm.plant.internal",),
        ),
        mock_fixtures_dir=FIXTURES,
    )
    assert Provider.ONPREM in adapters


def test_no_server_configured_means_no_onprem_adapter() -> None:
    adapters = build_model_adapters(
        _config(deployed=False, onprem=None), mock_fixtures_dir=FIXTURES
    )
    assert Provider.ONPREM not in adapters


def test_the_onprem_profile_stays_on_the_server_with_thinking_off() -> None:
    profile = ModelProfile.model_validate(
        yaml.safe_load((REPO_ROOT / "configs" / "models" / "onprem.yaml").read_bytes())
    )
    routes = [
        profile.structured_extraction,
        profile.reasoning,
        profile.chat,
        profile.deep_reasoning,
    ]
    declared = [route for route in routes if route is not None]
    assert {route.provider for route in declared} == {Provider.ONPREM}
    assert {route.reasoning_effort for route in declared} == {"none"}
    # Down means a person, never someone else's model.
    assert profile.fallback is None
    assert profile.embedding is None
