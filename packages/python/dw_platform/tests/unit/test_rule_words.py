"""A change in words, checked by the platform for any context's schema (ADR
0013/0014): the model proposes paths and values, code decides."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field

from dw_platform.application.rule_words import (
    ModelRuleChanges,
    WordsApplied,
    WordsRefused,
    apply_changes,
    focus_of,
    leaf_paths,
)

pytestmark = pytest.mark.unit


class Band(BaseModel):
    model_config = ConfigDict(extra="forbid")

    up_to: str | None
    label: str


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    bands: list[Band]
    reply_days: int = Field(ge=1, le=30)
    notice: str


BASE: dict[str, Any] = {
    "version": "1.0.0",
    "bands": [{"up_to": "20000000", "label": "Trưởng phòng"}, {"up_to": None, "label": "GĐ"}],
    "reply_days": 3,
    "notice": "Kính gửi ${supplier}, xin báo giá trong 3 ngày.",
}


def _answer(*changes: tuple[str, Any], understood: bool = True) -> ModelRuleChanges:
    return ModelRuleChanges.model_validate(
        {"understood": understood, "changes": [{"path": p, "value": v} for p, v in changes]}
    )


def _codes(result: WordsApplied | WordsRefused) -> list[str]:
    assert isinstance(result, WordsRefused)
    return [str(p) for p in result.problems]


def test_a_change_to_a_path_the_document_has_is_applied_with_its_type() -> None:
    result = apply_changes(
        Rules,
        BASE,
        _answer(("bands.0.up_to", 50000000), ("reply_days", 5)),
        request="hạn mức trưởng phòng 50 triệu, trả lời trong 5 ngày",
    )
    assert isinstance(result, WordsApplied)
    assert result.document["bands"][0]["up_to"] == "50000000"
    assert result.document["reply_days"] == 5
    assert result.changed == ("bands.0.up_to", "reply_days")
    assert BASE["reply_days"] == 3


def test_a_path_the_document_lacks_or_a_changed_type_is_refused() -> None:
    result = apply_changes(
        Rules,
        BASE,
        _answer(("bands.2.up_to", "1"), ("approver", "Lan"), ("reply_days", "năm")),
        request="x",
    )
    assert _codes(result) == [
        "path_unknown:bands.2.up_to",
        "path_unknown:approver",
        "type_changed:reply_days",
    ]


def test_a_path_outside_the_focus_lands_under_it_and_is_refused() -> None:
    result = apply_changes(Rules, BASE, _answer(("reply_days", 5)), request="5", focus="bands.0")
    assert _codes(result) == ["path_unknown:bands.0.reply_days"]
    assert focus_of(BASE, "bands.0") == BASE["bands"][0]


def test_the_whole_document_is_validated_by_the_schema() -> None:
    result = apply_changes(Rules, BASE, _answer(("reply_days", 90)), request="90 ngày")
    assert _codes(result) == ["document_invalid:reply_days"]


def test_copy_keeps_its_placeholders_and_invents_no_digit() -> None:
    dropped = apply_changes(
        Rules, BASE, _answer(("notice", "Kính gửi quý công ty")), request="ngắn", copy_text=True
    )
    invented = apply_changes(
        Rules,
        BASE,
        _answer(("notice", "Kính gửi ${supplier}, xin báo giá trong 7 ngày.")),
        request="lịch sự hơn",
        copy_text=True,
    )
    asked = apply_changes(
        Rules,
        BASE,
        _answer(("notice", "Kính gửi ${supplier}, xin báo giá trong 7 ngày.")),
        request="đổi thành 7 ngày",
        copy_text=True,
    )
    assert _codes(dropped) == ["placeholder_changed:notice"]
    assert _codes(invented) == ["digit_invented:notice"]
    assert isinstance(asked, WordsApplied)


def test_a_text_that_is_not_copy_is_held_to_its_type_only() -> None:
    result = apply_changes(
        Rules, BASE, _answer(("bands.1.label", "Giám đốc 2")), request="đổi tên bậc"
    )
    assert isinstance(result, WordsApplied)


def test_nothing_understood_drafts_nothing() -> None:
    result = apply_changes(Rules, BASE, _answer(understood=False), request="?")
    assert _codes(result) == ["nothing_understood"]


def test_the_prompt_is_offered_every_leaf_path() -> None:
    assert list(leaf_paths(BASE)) == [
        "version",
        "bands.0.up_to",
        "bands.0.label",
        "bands.1.up_to",
        "bands.1.label",
        "reply_days",
        "notice",
    ]
