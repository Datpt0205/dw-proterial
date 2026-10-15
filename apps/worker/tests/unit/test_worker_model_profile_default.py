"""The worker and the API run on one default model profile.

They used to differ ("gateway" here, "balanced" in the API), visible only to a
process started without DW_API_MODEL_PROFILE: the worker then embedded
documents with one profile while the API embedded queries with another.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dw_agent_runtime.model.profiles import DEFAULT_PROFILE_ID, ModelProfileRegistry
from dw_worker.settings import WorkerSettings

pytestmark = pytest.mark.unit

MODELS = Path(__file__).resolve().parents[4] / "configs" / "models"


def test_the_worker_defaults_to_the_platform_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DW_WORKER_MODEL_PROFILE", "DW_API_MODEL_PROFILE"):
        monkeypatch.delenv(name, raising=False)

    assert WorkerSettings().model_profile == DEFAULT_PROFILE_ID


def test_the_default_profile_ships() -> None:
    profiles = ModelProfileRegistry()
    profiles.load_directory(MODELS)

    assert profiles.resolve(DEFAULT_PROFILE_ID).profile_id == DEFAULT_PROFILE_ID
