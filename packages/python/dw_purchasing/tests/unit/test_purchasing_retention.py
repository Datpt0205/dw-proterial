"""How long DW2 keeps rows is each tenant's rule (`purchasing_rules.retention`):
the lane deletes per workspace by that tenant's term, the platform's where it
set none, and nothing where its rules do not read. Stored mail is kept no
longer than what DW2 did with it (`mailbox_days`, since 1.7.0)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from dw_purchasing.adapters.policy_files import PolicyFiles
from dw_purchasing.application.retention import Pruned, PurchasingRetention
from dw_purchasing.domain.rules import RetentionRules
from dw_purchasing.testing.world import ALPHA, BETA, World, open_world

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
ANSWERS = json.loads(
    (REPO / "evals/fixtures/cases/purchasing_pr_intake.json").read_text(encoding="utf-8")
)["answers"]


@dataclass
class _Store:
    held: list[tuple[uuid.UUID, uuid.UUID]]
    pruned: dict[tuple[uuid.UUID, uuid.UUID], tuple[datetime, datetime, datetime]] = field(
        default_factory=dict
    )

    async def scopes(self) -> Sequence[tuple[uuid.UUID, uuid.UUID]]:
        return self.held

    async def prune(
        self,
        scope: tuple[uuid.UUID, uuid.UUID],
        *,
        cases_before: datetime,
        outcomes_before: datetime,
        mail_before: datetime,
    ) -> Pruned:
        self.pruned[scope] = (cases_before, outcomes_before, mail_before)
        return Pruned(cases=0, outcomes=0, mail=0)


def _rules(**retention: int) -> dict[str, Any]:
    document = PolicyFiles.load(REPO / "configs/policies").current().model_dump(mode="json")
    document["policy_version"] = "9.0.0"
    document["retention"] = retention or None
    return document


def _lane(world: World, store: _Store) -> PurchasingRetention:
    return PurchasingRetention(store=store, book=world.rules.book, clock=world.clock)


async def test_each_tenant_is_pruned_by_its_own_term() -> None:
    world = open_world(REPO, ANSWERS)
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = _rules(
        case_years=2, mail_outcome_days=90, mailbox_days=60
    )
    store = _Store([ALPHA, BETA])
    await _lane(world, store).prune()
    now = world.clock.now()
    assert store.pruned[ALPHA] == (
        now - timedelta(days=730),
        now - timedelta(days=90),
        now - timedelta(days=60),
    )
    # Beta holds no version of its own: the platform's term, ten years, and
    # its stored mail a year.
    platform = PolicyFiles.load(REPO / "configs/policies").current().retention
    assert platform == RetentionRules(case_years=10, mail_outcome_days=365, mailbox_days=365)
    assert store.pruned[BETA] == (
        now - timedelta(days=3650),
        now - timedelta(days=365),
        now - timedelta(days=365),
    )


async def test_a_version_naming_no_mailbox_term_keeps_mail_as_long_as_its_outcomes() -> None:
    """A version written before 1.7.0: a mail kept past its outcome would read
    as unread again, and DW2's lane would open a second case for it."""
    world = open_world(REPO, ANSWERS)
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = _rules(
        case_years=2, mail_outcome_days=90
    )
    store = _Store([ALPHA])
    await _lane(world, store).prune()
    now = world.clock.now()
    assert store.pruned[ALPHA][2] == now - timedelta(days=90)


async def test_rules_that_do_not_read_delete_nothing_and_the_next_tenant_is_still_pruned() -> None:
    world = open_world(REPO, ANSWERS)
    broken = _rules(case_years=2, mail_outcome_days=90)
    broken["pr_form"]["max_lines"] = 0  # today's schema refuses it
    world.tenant_policies.documents[(ALPHA[0], "purchasing_rules")] = broken
    store = _Store([ALPHA, BETA])
    await _lane(world, store).prune()
    assert ALPHA not in store.pruned and BETA in store.pruned


def test_a_term_outside_its_bounds_is_no_version() -> None:
    for bad in (
        {"case_years": 0, "mail_outcome_days": 365},
        {"case_years": 10, "mail_outcome_days": 7},
        {"case_years": 10, "mail_outcome_days": 365, "mailbox_days": 7},
        {"case_years": 10, "mail_outcome_days": 3650, "mailbox_days": 3651},
    ):
        with pytest.raises(ValueError):
            RetentionRules.model_validate(bad)


def test_stored_mail_is_never_kept_past_its_outcome() -> None:
    """Mail kept past its outcome would be read again as new."""
    term = RetentionRules(case_years=10, mail_outcome_days=90, mailbox_days=365)
    assert term.mailbox_term_days == 90
    assert RetentionRules(case_years=10, mail_outcome_days=90).mailbox_term_days == 90
    assert (
        RetentionRules(case_years=1, mail_outcome_days=365, mailbox_days=60).mailbox_term_days == 60
    )
