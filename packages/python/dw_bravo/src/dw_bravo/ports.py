"""What the rule runner asks Bravo, as ports.

The runner never reaches Bravo's database itself (ADR 0026 still forbids a
driver; ticket 49 amends it). A server constraint's procedure, a lookup and a
unique-key check go through these Protocols; the offline adapter answers from
what a trace recorded (`dw_bravo.adapters.recorded`), and a live adapter waits
on ticket 49.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class ProcedurePort(Protocol):
    """Runs a Bravo procedure or function a rule names, read-only.

    Returns one value per name in `outputs`, in the rule's `DataMember` order.
    Raises `dw_bravo.expression.UndecidableError` when it has no answer.
    """

    def call(
        self, command: str, parameters: Mapping[str, object], outputs: Sequence[str]
    ) -> Mapping[str, object]: ...


class ReferencePort(Protocol):
    """Bravo's lookups (`LookupKey`) and unique keys."""

    def find(
        self, lookup_key: str, code: object, filter_key: str | None
    ) -> Mapping[str, object] | None: ...

    def key_taken(
        self, table: str, values: Mapping[str, object], filter_key: str | None, own_id: object
    ) -> bool: ...


@dataclass(frozen=True)
class Session:
    """Who is editing, where and when — what USER(), BRANCH(), GETDATE() read.

    `currency` holds the base currency's attributes (`Currency('DecimalRound')`)
    and `config` Bravo's `CONFIG()` keys; both come from Bravo, never a guess.
    """

    user: Mapping[str, object]
    branch: str
    now: datetime
    lang_id: int = 0
    currency: Mapping[str, object] = field(default_factory=dict)
    config: Mapping[str, object] = field(default_factory=dict)
    # The current branch's own attributes (`B00Branch`, by `branch`), what
    # `BRANCH('<column>')` reads (the template's `BRANCH('IsGroup')`).
    branch_info: Mapping[str, object] = field(default_factory=dict)
