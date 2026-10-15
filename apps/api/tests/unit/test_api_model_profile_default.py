"""The API runs on the platform's default model profile when none is named,
the same one the worker does (`DEFAULT_PROFILE_ID`)."""

from __future__ import annotations

import pytest

from dw_agent_runtime.model.profiles import DEFAULT_PROFILE_ID
from dw_api.settings import ApiSettings

pytestmark = pytest.mark.unit


def test_the_api_defaults_to_the_platform_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DW_API_MODEL_PROFILE", "DW_MODEL_PROFILE_ID"):
        monkeypatch.delenv(name, raising=False)

    assert ApiSettings(profile="test").model_profile == DEFAULT_PROFILE_ID
