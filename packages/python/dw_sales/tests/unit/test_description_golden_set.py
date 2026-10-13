"""The golden descriptions of ticket 28's eval say what they claim.

Each line is one DW1's own vocabulary does not read (so it is a line the model
step exists for), and the reading it intends fits its gold item in the
fictional item master. A fixture that failed either would score the model
against an answer nobody could reach.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from dw_sales.adapters.mock.fixtures import DATA_DIR, read_records
from dw_sales.domain.catalog import Item
from dw_sales.domain.descriptions import StatedAttributes, candidates, read_description

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
GOLDEN = json.loads(
    (REPO / "evals" / "fixtures" / "cases" / "sales_descriptions_golden.json").read_text(
        encoding="utf-8"
    )
)["lines"]
ITEMS = read_records(DATA_DIR / "items.json", Item)


def test_the_set_is_at_least_sixty_lines_in_three_languages() -> None:
    assert len(GOLDEN) >= 60
    assert len({line["id"] for line in GOLDEN}) == len(GOLDEN)
    assert set(Counter(line["lang"] for line in GOLDEN)) == {"vi", "en", "ja"}


@pytest.mark.parametrize("line", GOLDEN, ids=lambda line: line["id"])
def test_each_line_is_one_the_vocabulary_rejects_and_its_reading_fits_its_gold(
    line: dict[str, object],
) -> None:
    assert read_description(str(line["description"])) is None
    stated = StatedAttributes.model_validate(line["intended"])
    assert line["gold"] in {item.prv_code for item in candidates(stated, ITEMS)}
