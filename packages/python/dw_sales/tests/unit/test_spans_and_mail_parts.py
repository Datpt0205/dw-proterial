"""Where a span a model copied is, and what of a message a model is shown
(tickets 29 and 31, dw_sales ADR 0005)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dw_sales.domain.mail_parts import newest_part
from dw_sales.domain.messages import EmailAddress, InboundMessage
from dw_sales.domain.spans import FoldedText

pytestmark = pytest.mark.unit


# ------------------------------------------------------------------ spans --


@pytest.mark.parametrize(
    ("text", "span", "found"),
    [
        ("2C AWG24 BLK, 1,200 m", "24", False),  # part of AWG24
        ("2C AWG24 BLK, 1,200 m", "200", False),  # part of 1,200
        ("2C AWG24 BLK, 1,200 m", "1,2", False),
        ("2C AWG24 BLK, 1,200 m", "1,200", True),
        ("2C AWG24 BLK, 1,200 m", "m", True),
        ("数量1200m 納期", "1200", True),  # a number before its unit
        ("cuộn 300 mét", "m", False),  # a letter of a word
        # A number followed by its unit is a token: a reel length read as the
        # quantity passes here, and is flagged for Sales (ticket 29).
        ("cut 305M reel", "305", True),
        ("REF VLX-PO-2609-0118", "VLX-PO-2609-0118", True),
        ("REF XVLX-PO-2609-0118", "VLX-PO-2609-0118", False),
    ],
)
def test_a_bounded_span_is_a_whole_token(text: str, span: str, found: bool) -> None:
    assert bool(FoldedText(text).occurrences(span, bounded=True)) is found


def test_a_span_is_located_exactly_once_within_its_line() -> None:
    text = FoldedText("1. Cáp 2C, 1.200 m\n2. Dây AWG22, 3.000 m")
    line = text.locate("2. Dây AWG22, 3.000 m", bounded=True)

    assert line == (19, 40)
    assert text.locate("m", bounded=True) == "span_repeated"
    assert text.locate("m", bounded=True, within=line) == (39, 40)
    assert text.locate("1.200 m", bounded=True, within=line) == "span_not_found"


def test_folding_keeps_the_original_offsets() -> None:
    text = FoldedText("Straße 1,200 M")

    assert text.locate("1,200 m", bounded=True) == (7, 14)


# ------------------------------------------------------------- the part --


def _message(body: str, *, html: str | None = None, subject: str = "RFQ") -> InboundMessage:
    return InboundMessage(
        message_id="T1",
        sender=EmailAddress(address="an.trinh@velatrix.example"),
        subject=subject,
        received_at=datetime(2026, 10, 2, 9, 0, tzinfo=UTC),
        body_text=body,
        body_html=html,
    )


@pytest.mark.parametrize(
    "history",
    [
        "On Mon, 21 Sep 2026 at 10:00, Sales wrote:\nOld offer 5,000 m.",
        "Vào Thứ Hai, 21/09/2026 lúc 09:00, Vy đã viết:\nBáo giá cũ 5.000 m.",
        "2026年9月20日 10:00 営業 のメッセージ:\n前回 5,000m。",
        "-----Original Message-----\nOld offer 5,000 m.",
        "---------- Forwarded message ---------\nOld offer 5,000 m.",
        "From: Sales\nSent: 21/09/2026\nSubject: offer\nOld offer 5,000 m.",
        "> Old offer 5,000 m.\n> Sales",
    ],
    ids=[
        "en_wrote",
        "vi_wrote",
        "ja_wrote",
        "outlook_original",
        "forward",
        "outlook_header",
        "quoted",
    ],
)
def test_quoted_history_is_cut_from_the_plain_text(history: str) -> None:
    part = newest_part(_message(f"Please quote 1,200 m.\n\nThanks\n\n{history}"))

    assert "5,000" not in part.text and "5.000" not in part.text
    assert part.text == "RFQ\n\nPlease quote 1,200 m.\n\nThanks"
    assert part.cut


@pytest.mark.parametrize(
    "html",
    [
        "<div>Please quote 1,200 m.</div><blockquote>Old offer 5,000 m.</blockquote>",
        '<div>Please quote 1,200 m.</div><div class="gmail_quote"><div>On Mon wrote:</div>'
        "<div>Old offer 5,000 m.</div></div>",
        '<div>Please quote 1,200 m.</div><div id="appendonsend"></div><hr>'
        '<div id="divRplyFwdMsg"><b>From:</b> Sales</div><div>Old offer 5,000 m.</div>',
        '<p>Please quote 1,200 m.</p><div class="moz-cite-prefix">On Mon, Sales wrote:</div>'
        "<blockquote><p>Old offer 5,000 m.</p></blockquote>",
    ],
    ids=["blockquote", "gmail", "outlook", "thunderbird"],
)
def test_quoted_history_is_cut_by_the_html_structure(html: str) -> None:
    # The plain alternative says otherwise: the HTML's structure decides.
    part = newest_part(_message("Please quote 1,200 m. Old offer 5,000 m.", html=html))

    assert part.body == "Please quote 1,200 m."
    assert part.cut


def test_a_table_in_the_body_keeps_its_rows_and_cells() -> None:
    html = (
        "<p>Please quote:</p><table><tr><td>2C AWG24 BLK</td><td>1,200 m</td></tr>"
        "<tr><td>AWG22 RED</td><td>3,000 m</td></tr></table><style>p {color: red}</style>"
    )

    part = newest_part(_message("", html=html))

    assert part.body == "Please quote:\n2C AWG24 BLK | 1,200 m\nAWG22 RED | 3,000 m"
    assert not part.cut


def test_the_part_is_normalised_and_its_digest_is_of_what_a_model_reads() -> None:
    part = newest_part(
        _message("Line   one\t\twith  spaces\n\n\n\nLine two  ", subject="  Hỏi   giá ")
    )

    assert part.text == "Hỏi giá\n\nLine one with spaces\n\nLine two"
    assert len(part.sha256) == 64
