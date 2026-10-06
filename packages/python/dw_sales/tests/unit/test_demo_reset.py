"""The demo reset deletes Sales cases, so it refuses every deployed profile,
and touches only the tenants the demo personas sign in to."""

from __future__ import annotations

import pytest

from dw_platform.testing.seed_env import sid
from dw_sales.testing import demo_reset

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("profile", ["uat", "production", "staging"])
def test_the_reset_refuses_any_profile_but_local_and_test(
    monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    def must_not_run(url: str) -> None:
        raise AssertionError("the reset ran outside local/test")

    monkeypatch.setenv("DW_API_PROFILE", profile)
    monkeypatch.setenv("DW_DATABASE_URL", "postgresql+asyncpg://nobody@127.0.0.1:1/none")
    monkeypatch.setattr(demo_reset, "_reset", must_not_run)

    with pytest.raises(SystemExit, match="refusing"):
        demo_reset.main()


def test_the_reset_clears_only_the_demo_personas_tenants() -> None:
    assert demo_reset.demo_tenants() == sorted(
        [sid("tenant", "tenant-alpha"), sid("tenant", "tenant-beta")], key=str
    )
