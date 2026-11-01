"""A rule changed in words (dw_sales ADR 0006, decision 3).

A person who may propose a version of a key types what they want changed
("nhắc khách sau 3 ngày thôi"; for a mail, a letter to write it like). The
model answers with **changes**, each a path of the document in force and the
value it should hold; code decides whether the draft exists:

- every path is one that document already has, under the part the person
  asked about (``focus``), and the value has the type the field holds now;
- in the company's copy (mails, sheets, hand-offs) a changed text keeps every
  ``${value}`` it had and names no other, so a fact the draft printed is
  still printed by code and none is made up; and it holds no digit that
  neither the text it replaces nor the person's words hold, so a number is
  never the model's;
- the whole document, changed, is then validated by the key's schema, as any
  proposal is.

What passes is a **draft**: it opens in the rules editor as a start option,
the person reads the diff and sends it through the one door every version
takes (`rules.SalesRulesService.propose`): the head's applies at once, the
admin's waits for the head. The model proposes; it never applies.

The checks themselves are the platform's since ADR 0013/0014
(`dw_platform.application.rule_words`); what is Sales' is the prompt and
which keys are the company's copy.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from dw_agent_runtime.model.interpretation import PromptRef
from dw_platform.application import rule_words as words
from dw_platform.application.rule_words import (
    MAX_CHANGES,
    MAX_REQUEST_CHARS,
    ModelRuleChange,
    ModelRuleChanges,
    WordsApplied,
    WordsProblem,
    WordsRefused,
    focus_of,
    leaf_paths,
    placeholders,
)
from dw_sales.application.rules import OVERRIDABLE, RuleKey

__all__ = [
    "MAX_CHANGES",
    "MAX_REQUEST_CHARS",
    "ModelRuleChange",
    "ModelRuleChanges",
    "WordsApplied",
    "WordsProblem",
    "WordsRefused",
    "focus_of",
    "leaf_paths",
    "placeholders",
]

# The prompt a change in words is read with. Its file is
# `configs/prompts/sales/rule_change_in_words@1.0.0.yaml`; a test holds the
# two together.
RULE_CHANGE_IN_WORDS: Final = PromptRef("sales.rule_change_in_words", "1.0.0")
# What the prompt itself costs, held above its rendered size by a test.
PROMPT_TOKENS: Final = 1400
# Up to a dozen changes, a mail's three templates among them.
OUTPUT_TOKENS: Final = 2500

# The keys whose texts are the company's copy: what a draft prints.
COPY_KEYS: Final = frozenset({RuleKey.EMAILS, RuleKey.DOCUMENTS, RuleKey.HANDOFFS})


def apply_changes(
    key: RuleKey,
    base: Mapping[str, Any],
    answer: ModelRuleChanges,
    *,
    request: str,
    focus: str | None = None,
) -> WordsApplied | WordsRefused:
    """``base`` with the model's changes made, checked by the platform's
    rules for ``key``'s schema and, for the company's copy, its texts."""
    return words.apply_changes(
        OVERRIDABLE[key],
        base,
        answer,
        request=request,
        focus=focus,
        copy_text=key in COPY_KEYS,
    )
