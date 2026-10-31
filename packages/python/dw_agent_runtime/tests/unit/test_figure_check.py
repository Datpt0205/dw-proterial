"""The figure and amount checks every context holds a model's prose to
(docs/adr/0013): a figure counts whole or as a whole part, never as a
substring; a name is no figure only when its caller says so."""

from __future__ import annotations

import pytest

from dw_agent_runtime.model.figure_check import names_amount, unsupported

pytestmark = pytest.mark.unit

SOURCE = "Hạn 2026-10-09, đơn giá 0.79, PO NRV-PO-26-0457"


def test_a_figure_counts_whole_or_as_a_whole_part_never_as_a_substring() -> None:
    assert unsupported("trước ngày 9 tháng 10 năm 2026", SOURCE) == set()
    assert unsupported("PO NRV-PO-26-0457, đơn giá 0.79", SOURCE) == set()
    assert unsupported("giảm 7%, còn 045", SOURCE) == {"7", "045"}


def test_a_name_with_a_digit_passes_only_when_the_caller_names_it() -> None:
    assert unsupported("DW2 đã kiểm", SOURCE) == {"DW2"}
    assert unsupported("DW2 đã kiểm", SOURCE, names={"DW2"}) == set()
    # A name is never a licence for the figures beside it.
    assert unsupported("DW2 giảm 7", SOURCE, names={"DW2"}) == {"7"}


@pytest.mark.parametrize("text", ["giảm 5%", "100 USD", "5" + chr(0xFF05), "1.000 đồng", "¥300"])
def test_an_amount_is_named_in_any_of_the_languages(text: str) -> None:
    assert names_amount(text)


def test_a_date_or_a_code_is_no_amount() -> None:
    assert not names_amount(SOURCE)
