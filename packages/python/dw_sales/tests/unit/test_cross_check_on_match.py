"""Ticket 81: an order's cross-check passed by DW on a matching read-back
from Bravo, off unless the case's rules say so (dw_sales ADR 0016, Proposed).

The verdict (`OrderCase.on_match_exceptions`) reads every fact directly; the
transition (`cross_checked_on_match`) asks it again, so a caller that skipped
it is refused where the effect happens; taking the pass back is a non-maker's
and leaves the order's check to a person. The route a measured step takes
without a confidence (`measured_route`) is tested beside it.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from dw_kernel.errors import ConflictError
from dw_sales.domain.autonomy import OutcomeTally, cases_needed, in_audit_sample, measured_route
from dw_sales.domain.cross_check_on_match import OnMatchException, ReadBackFacts
from dw_sales.domain.orders import (
    Actor,
    FindingCode,
    FlaggedValue,
    OrderCase,
    OrderStatus,
    RegionFlag,
)

from .test_orders import AN, DIEU, T0, _accept, _finding, _line, _review, _uploaded
from .test_value_corrections import _case, _correct

pytestmark = pytest.mark.unit

E = OnMatchException
DW = Actor(user_id=uuid.UUID(int=0xD0))
DIGEST = "d" * 64


def _on(case: OrderCase | None = None, **stamps: Any) -> OrderCase:
    """An order in Bravo whose rules say a matching read-back passes it."""
    return _uploaded(case or _review(cross_check_on_match=True, **stamps))


def _matching(case: OrderCase, **facts: Any) -> ReadBackFacts:
    assert case.bravo_so_no is not None
    return ReadBackFacts(
        **{
            "source": "gateway",
            "case_version": case.case_version,
            "differences": 0,
            "so_no": case.bravo_so_no,
            **facts,
        }
    )


# ------------------------------------------------------------- the verdict --


def test_a_matching_gateway_read_back_of_an_untouched_order_passes() -> None:
    case = _on()

    assert case.on_match_exceptions(_matching(case)) == ()
    passed = case.cross_checked_on_match(_matching(case), DIGEST, DW, T0)

    assert passed.status is OrderStatus.CROSS_CHECKED
    assert (passed.cross_checked_by, passed.cross_checked_on_read_back) == (DW.user_id, DIGEST)


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        ({"source": "export"}, E.NOT_FROM_BRAVO),
        ({"case_version": 1}, E.STALE_READ_BACK),
        ({"differences": 1}, E.DIFFERS),
        ({"so_no": "SO26-9999"}, E.SO_NO_DIFFERS),
    ],
    ids=["an uploaded export", "another version", "a difference", "another SO number"],
)
def test_a_read_back_that_does_not_vouch_for_this_version_goes_to_a_person(
    facts: dict[str, Any], expected: OnMatchException
) -> None:
    case = _on()

    assert case.on_match_exceptions(_matching(case, **facts)) == (expected,)
    with pytest.raises(ConflictError) as refused:
        case.cross_checked_on_match(_matching(case, **facts), DIGEST, DW, T0)
    assert refused.value.details["exceptions"] == [expected.value]


def test_rules_that_do_not_say_so_keep_the_cross_check_a_persons() -> None:
    for case in (_uploaded(_review()), _uploaded(_review(cross_check_on_match=False))):
        assert case.cross_check_on_match is not True
        assert case.on_match_exceptions(_matching(case)) == (E.RULES_OFF,)


def test_a_finding_whatever_was_decided_about_it_goes_to_a_person() -> None:
    reviewed = _review(_finding(FindingCode.REQUESTED_DATE_SHORT_LT, 1), cross_check_on_match=True)
    case = _on(_accept(reviewed, reviewed.findings[0].key))

    assert case.on_match_exceptions(_matching(case)) == (E.FINDING,)


def test_a_value_the_preparer_typed_goes_to_a_person_though_makers_cannot_tell() -> None:
    """The preparer typing a corrected value leaves `makers` what it was (the
    preparer, who recorded the entry too): the verdict reads the correction
    itself."""
    typed = _correct(_case(flagged=("quantity",)), "quantity", "6100")
    stamped = OrderCase.model_validate({**dict(typed), "cross_check_on_match": True})
    case = _uploaded(stamped)

    assert case.makers == frozenset({AN.user_id})
    assert E.TYPED_BY_A_PERSON in case.on_match_exceptions(_matching(case))


def test_a_value_dw_applied_by_itself_goes_to_a_person() -> None:
    """80 and 81 must not stack into an order nobody looked at: a value
    code's gate applied, or a password file taken as read."""
    applied = FlaggedValue(field="quantity", flag=RegionFlag.MODEL_READ, gate="applied")
    case = _on(_review(lines=(_line(1, flags=(applied,)), _line(2)), cross_check_on_match=True))

    assert E.APPLIED_BY_DW in case.on_match_exceptions(_matching(case))


def test_an_order_awaiting_nothing_is_not_passed() -> None:
    crossed = _on().cross_check(DIEU, T0)

    assert E.NOT_AWAITING in crossed.on_match_exceptions(_matching(crossed))


# ------------------------------------------------------------ the stamps --


def test_the_stamp_needs_a_required_cross_check_and_the_read_back_its_checker() -> None:
    with pytest.raises(ValidationError, match="only a cross-check the rules require"):
        _review(cross_check_on_match=True, cross_check_required=False)
    passed = _on().cross_checked_on_match(_matching(_on()), DIGEST, DW, T0)
    with pytest.raises(ValidationError, match="only with its checker"):
        OrderCase.model_validate(
            {
                **dict(passed),
                "status": OrderStatus.UPLOADED_TO_BRAVO,
                "cross_checked_by": None,
                "cross_checked_at": None,
            }
        )


# ------------------------------------------------------------ taking back --


def test_a_non_maker_takes_a_pass_back_and_the_order_is_a_persons_to_check() -> None:
    passed = _on().cross_checked_on_match(_matching(_on()), DIGEST, DW, T0)

    back = passed.reopen_cross_check(DIEU)

    assert back.status is OrderStatus.UPLOADED_TO_BRAVO and back.awaits_cross_check
    assert (back.cross_checked_by, back.cross_checked_on_read_back) == (None, None)
    assert back.cross_check_on_match is False
    assert back.on_match_exceptions(_matching(back)) == (E.RULES_OFF,)


def test_a_maker_does_not_take_a_pass_back_nor_anyone_a_persons_cross_check() -> None:
    passed = _on().cross_checked_on_match(_matching(_on()), DIGEST, DW, T0)
    with pytest.raises(ConflictError) as refused:
        passed.reopen_cross_check(AN)
    assert refused.value.details["rule"] == "maker_checker"
    by_hand = _on().cross_check(DIEU, T0)
    with pytest.raises(ConflictError, match="taken back"):
        by_hand.reopen_cross_check(DIEU)


# ------------------------------------------------------- the measured route --


ALPHA = 0.02
UNSAMPLED = next(f"k{i}" for i in range(1000) if not in_audit_sample(f"k{i}", 0.03))
SAMPLED = next(f"k{i}" for i in range(1000) if in_audit_sample(f"k{i}", 0.03))


def _route(tally: OutcomeTally, key: str = UNSAMPLED) -> str:
    return measured_route(tally, ALPHA, item_key=key, audit_share=0.03)


def test_a_step_is_a_persons_until_its_cases_certify_the_target() -> None:
    needed = cases_needed(ALPHA)

    assert _route(OutcomeTally(cases=needed - 1)) == "person"
    assert _route(OutcomeTally(cases=needed, errors=1)) == "person"
    assert _route(OutcomeTally(cases=needed)) == "applied"


def test_a_certified_step_is_audited_by_sample_and_stopped_by_its_audits() -> None:
    certified = cases_needed(ALPHA)

    assert _route(OutcomeTally(cases=certified), SAMPLED) == "audit"
    stopped = OutcomeTally(cases=certified, audits=10, audit_errors=3)
    assert _route(stopped) == "shadow"


# --------------------------------------------------------------- the rules --


def test_the_platforms_rules_leave_it_off_and_refuse_it_without_a_cross_check() -> None:
    from pathlib import Path

    from dw_sales.adapters.order_rules import load_order_rules

    policies = Path(__file__).resolve().parents[5] / "configs" / "policies"
    shipped = load_order_rules(policies / "sales_order_rules@1.18.0.yaml")
    assert shipped.cross_check_on_match is False
    assert (
        load_order_rules(policies / "sales_order_rules@1.17.0.yaml").cross_check_on_match is False
    )
    with pytest.raises(ValidationError, match="needs cross_check_required"):
        type(shipped).model_validate(
            {**dict(shipped), "cross_check_on_match": True, "cross_check_required": False}
        )
    assert type(shipped).model_validate({**dict(shipped), "cross_check_on_match": True})
