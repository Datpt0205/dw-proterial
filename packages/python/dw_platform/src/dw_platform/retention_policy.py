"""How long this deployment keeps data — the contract, not the sweeps.

The rules live here rather than beside any one sweep because "how long do you
keep our data" is one question with one answer. `memory` expires items,
`knowledge` expires deleted documents, and if each owned its own copy of the
schedule the two would drift and the release manifest would carry two versions
of one commitment. Both packages already depend on this one; the kernel, which
is the only layer below it, is deliberately dependency-free and stays that way.

The sweeps themselves stay where the tables are: `dw_memory.retention` and
`dw_knowledge.retention`. This module knows no SQL.

**Deleting, not closing.** `valid_until` answers "this stopped being true" — it
is what supersession writes, and the row stays so a past decision can still be
explained. Retention answers a different question: "we are no longer allowed to
hold this." The two must not share a mechanism, because the second one is what
goes in a contract.

**A class with no `days` never expires.** `legal_hold` is that, deliberately: an
obligation to keep can outlive the ordinary schedule, and the safe way to express
it is a class the sweep cannot touch rather than a flag the sweep must remember
to honour.

**An unknown class is kept, not guessed.** A row naming a class this build does
not have is more likely a newer config than a mistake, and deleting on that
guess is irreversible. It is kept and counted, so the mismatch shows up as a
number rather than as missing data.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "KnowledgeRetention",
    "RetentionClass",
    "RetentionPolicy",
    "load_retention_policy",
]


class RetentionClass(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # `None` means never swept. Not zero, and not absent — an explicit null, so
    # "keep forever" is something somebody wrote rather than something omitted.
    days: int | None = Field(default=None, ge=1)
    description: str


class KnowledgeRetention(BaseModel):
    """Two windows, because two different things expire on the knowledge side.

    `deleted_grace_days` is how long a document survives somebody marking it
    deleted — marking is a user action and users change their minds.

    `orphan_evidence_grace_days` is how long an evidence row survives losing its
    last citation. It exists because `evidence -> documents` is RESTRICT: until
    orphaned evidence goes, a document that was ever cited can never be hard
    deleted, and the document window above would be a promise the schema cannot
    keep. Today evidence and its `item_evidence` link are written in one
    transaction, so an unlinked row is genuinely unlinked; the window is what
    keeps that from being load-bearing for a writer that later splits them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    deleted_grace_days: int = Field(ge=1)
    orphan_evidence_grace_days: int = Field(ge=1)


class RetentionPolicy(BaseModel):
    """The versioned answer to "how long do you keep our data"."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: str
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    classes: dict[str, RetentionClass]
    knowledge: KnowledgeRetention
    batch_limit: int = Field(gt=0, le=10_000)

    def cutoff_for(self, name: str, *, now: datetime) -> datetime | None:
        """The instant before which rows of this class have outlived their term.

        `None` for a class that never expires and for one this build does not
        know — the caller keeps the row either way, and only the second is worth
        a log line.
        """
        found = self.classes.get(name)
        if found is None or found.days is None:
            return None
        return now - timedelta(days=found.days)


def load_retention_policy(path: Path) -> RetentionPolicy:
    return RetentionPolicy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
