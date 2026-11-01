"""The words a person reads for a mail sent to them are CONTEXT.md's, the same
line the web's labels are tested against, so the notice and the inbox never
say two things for one reason."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dw_purchasing.application.automation_lane import _MAIL_REASONS, mail_reason

pytestmark = pytest.mark.unit

CONTEXT = Path(__file__).resolve().parents[2] / "CONTEXT.md"


def _line(lead: str) -> dict[str, str]:
    text = CONTEXT.read_text(encoding="utf-8")
    start = text.index(f"\n{lead}:")
    paragraph = text[start:].split("\n\n")[0].replace("\n", " ")
    return dict(re.findall(r"`([a-z_]+)`\s*\(([^)]*)\)", paragraph))


def test_the_mail_reasons_are_the_glossary_s_word_for_word() -> None:
    assert _line("Mail reasons") == _MAIL_REASONS


def test_a_form_rule_names_the_field_and_an_unknown_code_is_not_hidden() -> None:
    assert mail_reason("missing:budget_code").startswith("thiếu budget_code")
    assert mail_reason("something_new") == "something_new"
