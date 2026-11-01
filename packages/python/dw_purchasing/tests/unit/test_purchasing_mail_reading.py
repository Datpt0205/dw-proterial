"""What code makes of a span (`dw_purchasing.domain.mail_reading`), and the
files DW2's code names (prompt, worker, rules) held to it."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from dw_purchasing.adapters.policy_files import PolicyFiles, load_rules
from dw_purchasing.application.intake import PR_MAIL_READING
from dw_purchasing.domain.mail_reading import (
    ModelPrMail,
    fold,
    parse_currency,
    parse_date,
    parse_quantity,
    read_pr_mail,
)

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ARRIVED = date(2026, 11, 2)


@pytest.mark.parametrize(
    ("span", "value"),
    [
        ("4", Decimal(4)),
        ("1.200", Decimal(1200)),
        ("1,200 m", Decimal(1200)),
        ("2,5", Decimal("2.5")),
        ("2.5 kg", Decimal("2.5")),
        ("0", None),
        ("4 cái, 5 hộp", None),
        ("bốn", None),
        ("1.2.3", None),
    ],
)
def test_a_quantity_is_one_number_as_people_group_it(span: str, value: Decimal | None) -> None:
    assert parse_quantity(span) == value


@pytest.mark.parametrize(
    ("span", "value"),
    [
        ("20/11/2026", date(2026, 11, 20)),
        ("cần trước 2026-11-20", date(2026, 11, 20)),
        ("20.11.26", date(2026, 11, 20)),
        ("20/11", date(2026, 11, 20)),
        # Before the day the mail arrived: next year's.
        ("01/02", date(2027, 2, 1)),
        ("31/02/2026", None),
        ("tuần sau", None),
    ],
)
def test_a_date_is_read_day_first(span: str, value: date | None) -> None:
    assert parse_date(span, received_on=ARRIVED) == value


@pytest.mark.parametrize(
    ("span", "value"), [("VND", "VND"), ("đồng", "VND"), ("US$", "USD"), ("円", "JPY"), ("€", None)]
)
def test_a_currency_is_one_of_the_words_for_it(span: str, value: str | None) -> None:
    assert parse_currency(span) == value


def _answer(**changes: object) -> ModelPrMail:
    line = {
        "line_span": "Dây AWG24, 12 cuộn",
        "item_code_span": None,
        "description_span": "Dây AWG24",
        "quantity_span": "12",
        "unit_span": "cuộn",
        "need_by_span": None,
    }
    base: dict[str, object] = {
        "pr_no_span": "PR-12",
        "department_span": "Kho",
        "budget_code_span": None,
        "currency_span": None,
        "need_by_span": None,
        "lines": [line],
    }
    return ModelPrMail.model_validate({**base, **changes})


def _read(text: str, answer: ModelPrMail) -> str | None:
    verdict = read_pr_mail(
        text, answer, requester="Lan", received_on=ARRIVED, default_currency="VND"
    )
    return verdict.not_read


def test_a_span_is_found_only_as_whole_tokens() -> None:
    text = "PR-123 Kho\nDây AWG24, 12 cuộn"
    # `PR-12` is inside `PR-123`, not a token of the mail.
    assert _read(text, _answer()) == "no_pr_number"
    assert _read(text.replace("PR-123", "PR-12"), _answer()) is None
    # `24` of `AWG24` is no quantity.
    line = {**_answer().lines[0].model_dump(), "quantity_span": "24"}
    assert _read("PR-12 Kho\nDây AWG24, 12 cuộn", _answer(lines=[line])) == "line_unreadable"


def test_the_same_line_twice_refuses_the_request() -> None:
    line = _answer().lines[0].model_dump()
    assert _read("PR-12 Kho\nDây AWG24, 12 cuộn", _answer(lines=[line, line])) == "line_unreadable"


def test_comparison_folds_case_width_and_spaces() -> None:
    wide = "".join(chr(0xFEE0 + ord(c)) for c in "PR-12")  # full-width, as an IME types it
    assert fold(f"{wide}  Kho") == fold("pr-12 kho")


def test_the_prompt_file_is_the_one_the_step_names() -> None:
    path = REPO / "configs/prompts/purchasing" / f"pr_mail_reading@{PR_MAIL_READING.version}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert (raw["prompt_id"], raw["version"]) == (
        PR_MAIL_READING.prompt_id,
        PR_MAIL_READING.version,
    )
    assert raw["variables"] == ["mail"]


def test_the_worker_config_names_the_worker_dw2_records_its_calls_under() -> None:
    raw = yaml.safe_load((REPO / "configs/workers/purchasing.yaml").read_text(encoding="utf-8"))
    assert (raw["worker_id"], raw["worker_version"]) == ("purchasing-dw2", "1.0.0")
    assert raw["toolset_version"] is None


def test_every_released_rules_file_loads_and_one_named_for_another_version_is_refused(
    tmp_path: Path,
) -> None:
    files = PolicyFiles.load(REPO / "configs/policies")
    versions = {r.version for r in files.released}
    newest = max(versions, key=lambda v: tuple(int(p) for p in v.split(".")))
    assert files.current().version == newest and {"1.0.0", "1.1.0"} <= versions
    wrong = tmp_path / "purchasing_rules@9.9.9.yaml"
    wrong.write_bytes((REPO / "configs/policies/purchasing_rules@1.0.0.yaml").read_bytes())
    with pytest.raises(ValueError, match="holds"):
        load_rules(wrong)
