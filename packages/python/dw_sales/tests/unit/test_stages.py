"""A case finishes on the stage versions it was opened with (ticket 61, step 2)."""

from __future__ import annotations

import pytest

from dw_kernel.errors import ConflictError
from dw_sales.application.case_store import CaseOrigin
from dw_sales.application.stages import (
    STAGE_DEFAULTS,
    Stage,
    StageConfigError,
    StageHandlers,
    current_stages,
)

pytestmark = pytest.mark.unit


def test_a_case_is_stamped_with_the_defaults_of_the_day_it_opens() -> None:
    origin = CaseOrigin(assigned_to=None, release_manifest_ref=None)
    assert origin.stage_versions == {"write_bravo": STAGE_DEFAULTS[Stage.WRITE_BRAVO]}
    # A stamp of its own, not the defaults' mapping: nothing moves it later.
    assert origin.stage_versions is not current_stages()


def test_the_default_version_must_be_served() -> None:
    with pytest.raises(StageConfigError, match="no handler serves it"):
        StageHandlers(Stage.WRITE_BRAVO, {"9.9.9": object()})


def test_a_version_is_three_numbers() -> None:
    with pytest.raises(StageConfigError, match="not a version"):
        StageHandlers(Stage.WRITE_BRAVO, {"1.0.0": object(), "latest": object()})


def test_each_case_gets_the_handler_of_the_version_it_was_stamped_with() -> None:
    old, new = object(), object()
    served = StageHandlers(Stage.WRITE_BRAVO, {"1.0.0": old, "1.1.0": new})
    assert served.for_case({"write_bravo": "1.0.0"}) == ("1.0.0", old)
    assert served.for_case({"write_bravo": "1.1.0"}) == ("1.1.0", new)


@pytest.mark.parametrize(
    ("stamp", "rule"),
    [({"write_bravo": "0.9.0"}, "stage_version_unavailable"), ({}, "stage_not_pinned")],
)
def test_a_version_not_served_or_not_stamped_is_refused(stamp: dict[str, str], rule: str) -> None:
    served = StageHandlers(Stage.WRITE_BRAVO, {"1.0.0": object()})
    with pytest.raises(ConflictError) as refused:
        served.for_case(stamp)
    assert refused.value.details["rule"] == rule


def test_start_up_is_refused_while_an_open_case_is_pinned_to_a_dropped_version() -> None:
    served = StageHandlers(Stage.WRITE_BRAVO, {"1.0.0": object()})
    served.refuse_orphans({("write_bravo", "1.0.0"): 12, ("write_bravo", "0.9.0"): 0})
    with pytest.raises(StageConfigError, match=r"0\.9\.0 \(3 open\)"):
        served.refuse_orphans({("write_bravo", "1.0.0"): 12, ("write_bravo", "0.9.0"): 3})
    # Another stage's pins are that stage's to answer for.
    served.refuse_orphans({("check", "7.0.0"): 4})
