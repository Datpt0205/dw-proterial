"""A rule changed in words (dw_sales ADR 0006, decision 3): what code lets a
model's proposed changes become a draft, and what it refuses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.application.rule_words import (
    ModelRuleChange,
    ModelRuleChanges,
    WordsApplied,
    WordsRefused,
    apply_changes,
    focus_of,
    leaf_paths,
)
from dw_sales.application.rules import RuleKey

REPO = Path(__file__).resolve().parents[5]
POLICIES = load_sales_policies(REPO / "configs" / "policies", REPO / "configs" / "copy")


def _doc(key: RuleKey) -> dict[str, Any]:
    return POLICIES.current()[key].model_dump(mode="json", by_alias=True)


def _answer(*changes: tuple[str, Any], understood: bool = True) -> ModelRuleChanges:
    return ModelRuleChanges(
        understood=understood,
        changes=tuple(ModelRuleChange(path=p, value=v) for p, v in changes),
    )


def _codes(result: WordsApplied | WordsRefused) -> set[str]:
    assert isinstance(result, WordsRefused), result
    return {str(p) for p in result.problems}


def test_a_number_the_person_asked_for_becomes_the_draft() -> None:
    base = _doc(RuleKey.FOLLOWUPS)
    asked = "nhắc PIC sau 6 giờ thay vì 4 giờ"

    result = apply_changes(
        RuleKey.FOLLOWUPS,
        base,
        _answer(("order_unconfirmed.remind.after_hours", 6)),
        request=asked,
    )

    assert isinstance(result, WordsApplied)
    assert result.document["order_unconfirmed"]["remind"]["after_hours"] == 6
    assert result.changed == ("order_unconfirmed.remind.after_hours",)
    # The document in force is left as it was.
    assert base["order_unconfirmed"]["remind"]["after_hours"] == 4


def test_a_path_the_document_lacks_is_never_created() -> None:
    result = apply_changes(
        RuleKey.FOLLOWUPS,
        _doc(RuleKey.FOLLOWUPS),
        _answer(("order_unconfirmed.remind.auto_confirm", True)),
        request="tự xác nhận đơn",
    )
    assert _codes(result) == {"path_unknown:order_unconfirmed.remind.auto_confirm"}


def test_a_field_keeps_its_type() -> None:
    result = apply_changes(
        RuleKey.FOLLOWUPS,
        _doc(RuleKey.FOLLOWUPS),
        _answer(("morning_brief.enabled", "có")),
        request="bật bản tin",
    )
    assert _codes(result) == {"type_changed:morning_brief.enabled"}


def test_the_whole_document_is_still_validated() -> None:
    result = apply_changes(
        RuleKey.FOLLOWUPS,
        _doc(RuleKey.FOLLOWUPS),
        _answer(("working_hours.start", "25:99")),
        request="bắt đầu lúc 25:99",
    )
    assert any(code.startswith("document_invalid") for code in _codes(result))


def test_nothing_understood_drafts_nothing() -> None:
    result = apply_changes(
        RuleKey.FOLLOWUPS,
        _doc(RuleKey.FOLLOWUPS),
        _answer(understood=False),
        request="làm cho tốt hơn",
    )
    assert _codes(result) == {"nothing_understood"}


# ------------------------------------------------- a mail from an example --

FOCUS = "emails.confirmation_draft"


def test_a_mail_rewritten_from_an_example_keeps_every_fact_code_fills() -> None:
    base = _doc(RuleKey.EMAILS)
    old = focus_of(base, FOCUS)["vi"]["body"]
    new = old.replace("Chúng tôi xác nhận", "Phòng Kinh doanh trân trọng xác nhận")

    result = apply_changes(
        RuleKey.EMAILS,
        base,
        _answer(("vi.body", new)),
        request="Viết giống thư ví dụ: Phòng Kinh doanh trân trọng xác nhận đơn hàng của Quý khách",
        focus=FOCUS,
    )

    assert isinstance(result, WordsApplied)
    assert result.changed == (f"{FOCUS}.vi.body",)
    assert focus_of(result.document, FOCUS)["vi"]["body"] == new


def test_a_mail_that_drops_or_invents_a_fact_is_refused() -> None:
    base = _doc(RuleKey.EMAILS)
    old = focus_of(base, FOCUS)["vi"]["body"]
    dropped = old.replace("${bravo_so_no}", "")
    invented = old + "\nHạn thanh toán: ${payment_terms}"

    for body in (dropped, invented):
        result = apply_changes(
            RuleKey.EMAILS, base, _answer(("vi.body", body)), request="thân thiện hơn", focus=FOCUS
        )
        assert _codes(result) == {f"placeholder_changed:{FOCUS}.vi.body"}


def test_a_mail_may_not_print_a_number_the_model_made_up() -> None:
    base = _doc(RuleKey.EMAILS)
    old = focus_of(base, FOCUS)["vi"]["body"]
    priced = old + "\nĐơn giá đã giảm 15% cho đơn này."

    refused = apply_changes(
        RuleKey.EMAILS, base, _answer(("vi.body", priced)), request="thêm lời cảm ơn", focus=FOCUS
    )
    assert _codes(refused) == {f"digit_invented:{FOCUS}.vi.body"}
    # A number the person wrote in their own words may be printed.
    asked = apply_changes(
        RuleKey.EMAILS,
        base,
        _answer(("vi.body", old + "\nVui lòng phản hồi trong 2 ngày làm việc.")),
        request="nhờ khách phản hồi trong 2 ngày làm việc",
        focus=FOCUS,
    )
    assert isinstance(asked, WordsApplied)


def test_a_change_outside_the_part_asked_about_finds_nothing_to_change() -> None:
    result = apply_changes(
        RuleKey.EMAILS,
        _doc(RuleKey.EMAILS),
        _answer(("emails.decline_draft.vi.body", "Xin lỗi.")),
        request="sửa thư xác nhận",
        focus=FOCUS,
    )
    assert _codes(result) == {f"path_unknown:{FOCUS}.emails.decline_draft.vi.body"}


def test_the_prompt_is_offered_only_the_leaves_of_the_part_asked_about() -> None:
    paths = leaf_paths(focus_of(_doc(RuleKey.EMAILS), FOCUS))
    assert "vi.body" in paths and "en.subject" in paths
    assert not any(p.startswith("decline_draft") for p in paths)


def test_the_prompt_file_is_the_one_the_step_names_and_fits_its_room() -> None:
    from dw_agent_runtime.model.prompts import PromptRegistry
    from dw_kernel.ids import TenantId
    from dw_sales.application.model_reading import estimated_tokens
    from dw_sales.application.rule_words import PROMPT_TOKENS, RULE_CHANGE_IN_WORDS
    from dw_sales.evals.world import ALPHA

    prompts = PromptRegistry()
    prompts.load_directory(REPO / "configs" / "prompts")
    rendered = prompts.render(
        RULE_CHANGE_IN_WORDS.prompt_id,
        RULE_CHANGE_IN_WORDS.version,
        {"rule_name": "", "document": "", "paths": "", "request": ""},
        tenant_id=TenantId(ALPHA.tenant_id.value),
    )
    assert estimated_tokens(rendered.system + rendered.user) < PROMPT_TOKENS
