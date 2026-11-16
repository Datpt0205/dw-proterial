"""Which line of an order some words name: the one answer the hand-off
(ticket 33), the customer's change request (ticket 27) and PC's internal
change (ticket 10) share (`domain.named_lines`, ticket 42 family 6)."""

from __future__ import annotations

import pytest

from dw_sales.domain.named_lines import LineNames, named_line

pytestmark = pytest.mark.unit

# A synthetic order: line 1 and 3 share the customer's code, as a PO that
# orders one item twice for two dates does.
ORDER = (
    LineNames(1, frozenset({"VX-C4B22", "CB-2007"})),
    LineNames(2, frozenset({"NV-CB4-22-GY", "CB-2008"})),
    LineNames(3, frozenset({"VX-C4B22", "CB-2009"})),
    LineNames(4, frozenset({"KMH-21-0077"})),
)


@pytest.mark.parametrize(
    ("words", "line"),
    [
        # A code of the order written whole, in any words around it.
        ("NV-CB4-22-GY", 2),
        ("cáp CB-2008", 2),
        ("品番KMH-21-0077", 4),
        # Full-width brackets, as Japanese mail writes them.
        ("2行目\uff08KMH-21-0077\uff09", None),  # the code is line 4's, the number line 2's
        ("4行目\uff08KMH-21-0077\uff09", 4),
        # A code only begun is no code of the order, and its digits no number.
        ("NV-CB4-22", None),
        # A code two lines share: the number stated tells them apart.
        ("VX-C4B22", None),
        ("Dòng 3 (mã VX-C4B22)", 3),
        ("Dòng 2 (mã VX-C4B22)", None),
        # A code with a figure that is no line of the order beside it.
        ("CB-2008 3000", 2),
        # No code: the one number the words state, in any language's words.
        ("Dòng 2", 2),
        ("Line 2", 2),
        ("2行目", 2),
        ("#3", 3),
        ("No.2", 2),
        ("Item 4", 4),
        # A number of no line is returned for the caller to refuse.
        ("Dòng 7", 7),
        # Nothing to go by, or more than one number: no line.
        ("mọi dòng", None),
        ("PO NRV-PO-26-0190", None),
        ("dòng 1 và dòng 2", None),
        ("1.5", None),
        ("1,200", None),
    ],
)
def test_one_answer_to_which_line(words: str, line: int | None) -> None:
    assert named_line(ORDER, words) == line


def test_words_the_model_gave_for_the_line_are_read_for_their_number() -> None:
    """No word list decides which words announce a line number: the model
    chose the words naming the line, and code reads the one number in them.
    So "12 cuộn", given as a line's words, is line 12 where the order has
    one, as "Dòng 12" is; the hand-off's old reader, which knew only
    "dòng/line/no/#/行", took it for no line."""
    twelve = [LineNames(n, frozenset()) for n in range(1, 13)]
    assert named_line(twelve, "12 cuộn") == named_line(twelve, "Dòng 12") == 12
