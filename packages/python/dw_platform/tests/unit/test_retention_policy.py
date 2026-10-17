"""The retention table's own answers, without a database.

`prune` never asks about a class the policy does not name, so the unknown-class
branch of `cutoff_for` is unreachable from there — a mutation proved it by
changing that branch and breaking nothing. It is still the right behaviour for
the next caller, so it is tested where it can actually fail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from dw_platform.retention_policy import (
    AuditRetention,
    ChannelDeliveryRetention,
    CheckpointRetention,
    KnowledgeRetention,
    OffboardingExportRetention,
    RetentionClass,
    RetentionPolicy,
    load_retention_policy,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 18, tzinfo=UTC)


def _policy() -> RetentionPolicy:
    return RetentionPolicy(
        schema_version="1.0",
        policy_id="retention",
        policy_version="1.0.0",
        classes={
            # `default` is here so the unknown-class test can actually fail: a
            # policy without one makes "fall back to default" a no-op, and the
            # test would pass whatever the code did.
            "default": RetentionClass(days=730, description="thường"),
            "ephemeral": RetentionClass(days=30, description="ngắn"),
            "legal_hold": RetentionClass(days=None, description="giữ vô hạn"),
        },
        knowledge=KnowledgeRetention(
            deleted_grace_days=30, orphan_evidence_grace_days=7, superseded_versions_kept=5
        ),
        audit=AuditRetention(
            months_ahead=3,
            enforced=True,
            tables={"audit_events": RetentionClass(days=None, description="giữ")},
        ),
        checkpoints=CheckpointRetention(superseded_days=7, idle_thread_days=730),
        channel_deliveries=ChannelDeliveryRetention(pending_expiry_days=7),
        offboarding_exports=OffboardingExportRetention(retain_days=30),
        batch_limit=100,
    )


def test_a_term_becomes_a_cutoff_in_the_past() -> None:
    assert _policy().cutoff_for("ephemeral", now=NOW) == datetime(2026, 8, 19, tzinfo=UTC)


def test_a_class_with_no_term_has_no_cutoff() -> None:
    """`None` is "never sweep", not "sweep everything" — the difference between
    honouring a legal hold and destroying evidence."""
    assert _policy().cutoff_for("legal_hold", now=NOW) is None


def test_an_unknown_class_has_no_cutoff_either() -> None:
    """Kept, not guessed. A name this build does not have is more likely a newer
    config than a mistake, and deleting on that guess cannot be undone."""
    assert _policy().cutoff_for("from_a_later_release", now=NOW) is None


def test_a_term_of_zero_days_is_refused_by_the_schema() -> None:
    """Zero would mean "delete everything on sight", which is never what someone
    means to write, and is one keystroke from a real term."""
    with pytest.raises(ValueError):
        RetentionClass(days=0, description="x")


def test_a_term_that_is_not_enforced_has_no_cutoff() -> None:
    """`days` records the decision; `enforced` says whether it may run. Reading
    only the first would turn writing a number into destroying a month."""
    decided = AuditRetention(
        months_ahead=3,
        enforced=False,
        tables={"audit_events": RetentionClass(days=1095, description="ba năm")},
    )
    assert decided.cutoff_for("audit_events", now=NOW) is None


def test_the_same_term_has_a_cutoff_once_enforced() -> None:
    """Or the flag would be a way to disable retention that nothing switches
    back on — the test has to be able to fail in both directions."""
    live = AuditRetention(
        months_ahead=3,
        enforced=True,
        tables={"audit_events": RetentionClass(days=1095, description="ba năm")},
    )
    # 1095 = 3*365, and 2024 was a leap year, so this is three years less a day.
    assert live.cutoff_for("audit_events", now=NOW) == datetime(2023, 9, 19, tzinfo=UTC)


def test_an_idle_term_shorter_than_the_superseded_one_is_refused() -> None:
    """The checkpoint sweep selects by the shorter term and decides by the
    longer: reversed, a thread would be emptied before its own superseded
    checkpoints expire."""
    with pytest.raises(ValueError, match="idle_thread_days"):
        CheckpointRetention(superseded_days=30, idle_thread_days=7)


@pytest.mark.parametrize("days", [0, -1])
def test_a_pending_delivery_term_is_at_least_a_day(days: int) -> None:
    """Zero would fail a delivery the moment it is queued, before any lane
    could try it."""
    with pytest.raises(ValueError, match="pending_expiry_days"):
        ChannelDeliveryRetention(pending_expiry_days=days)


POLICIES = Path(__file__).resolve().parents[5] / "configs" / "policies"


def test_the_pinned_policy_carries_the_terms_dat_decided_on_2026_10_18() -> None:
    """Offboarding export bundles go 30 days after they are written, and a
    document keeps its newest five superseded versions (retention 1.8.0)."""
    policy = load_retention_policy(POLICIES / "retention@1.8.0.yaml")
    assert policy.policy_version == "1.8.0"
    assert policy.offboarding_exports.retain_days == 30
    assert policy.knowledge.superseded_versions_kept == 5


@pytest.mark.parametrize("days", [0, -1, 366])
def test_an_export_bundle_term_is_a_day_to_a_year(days: int) -> None:
    """Zero would delete a bundle before anybody could hand it over; past a
    year it is no longer a handover copy, just the tenant's data kept."""
    with pytest.raises(ValueError, match="retain_days"):
        OffboardingExportRetention(retain_days=days)


@pytest.mark.parametrize("kept", [0, -1])
def test_at_least_one_superseded_version_is_kept(kept: int) -> None:
    """Zero would erase every document's history on the next pass."""
    with pytest.raises(ValueError, match="superseded_versions_kept"):
        KnowledgeRetention(
            deleted_grace_days=30, orphan_evidence_grace_days=7, superseded_versions_kept=kept
        )


def test_neither_new_term_has_a_default() -> None:
    """A file without them must not load: a default here would be a term
    nobody wrote, and its absence would read as "never deleted" again."""
    fields = _policy().model_dump()
    del fields["offboarding_exports"]
    with pytest.raises(ValueError, match="offboarding_exports"):
        RetentionPolicy.model_validate(fields)
    fields = _policy().model_dump()
    del fields["knowledge"]["superseded_versions_kept"]
    with pytest.raises(ValueError, match="superseded_versions_kept"):
        RetentionPolicy.model_validate(fields)
