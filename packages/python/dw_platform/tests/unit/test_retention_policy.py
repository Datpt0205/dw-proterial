"""The retention table's own answers, without a database.

`prune` never asks about a class the policy does not name, so the unknown-class
branch of `cutoff_for` is unreachable from there — a mutation proved it by
changing that branch and breaking nothing. It is still the right behaviour for
the next caller, so it is tested where it can actually fail.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from dw_platform.retention_policy import (
    AuditRetention,
    KnowledgeRetention,
    RetentionClass,
    RetentionPolicy,
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
        knowledge=KnowledgeRetention(deleted_grace_days=30, orphan_evidence_grace_days=7),
        audit=AuditRetention(
            months_ahead=3,
            tables={"audit_events": RetentionClass(days=None, description="giữ")},
        ),
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
