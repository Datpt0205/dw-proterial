"""DW2's rows past the term each tenant's rules give them
(`purchasing_rules.retention`, since 1.6.0), deleted by the worker's
`purchasing_retention` lane.

The term is the tenant's own number, changed like any rule and decided by a
second person, so the accountant's answer is a setting. The lane visits each
workspace that holds DW2 rows, resolves that tenant's rules there, and
deletes a case received before its term (its mail outcomes with it), a mail
outcome settled before its own, and stored mail received before the
mailbox's (`RetentionRules.mailbox_term_days`).

Fails closed, the way that loses nothing: rules that set no term, or rules
that no longer read, delete nothing in that workspace; the next workspace is
still visited.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from dw_kernel.errors import DomainError
from dw_kernel.ids import TenantId, WorkspaceId
from dw_kernel.ports import UtcClock
from dw_platform.application.rule_versions import ContextScope
from dw_purchasing.application.rules import PurchasingRuleBook, PurchasingRuleKey

_LOG = logging.getLogger("dw_purchasing.retention")


@dataclass(frozen=True)
class Pruned:
    cases: int
    outcomes: int
    mail: int


class RetentionStorePort(Protocol):
    """The two reads across tenants the lane needs, ids and counts only."""

    async def scopes(self) -> Sequence[tuple[uuid.UUID, uuid.UUID]]:
        """Every (tenant, workspace) holding a case, a mail outcome or
        stored mail."""
        ...

    async def prune(
        self,
        scope: tuple[uuid.UUID, uuid.UUID],
        *,
        cases_before: datetime,
        outcomes_before: datetime,
        mail_before: datetime,
    ) -> Pruned: ...


@dataclass(frozen=True)
class PurchasingRetention:
    """Implements the worker's `RetentionPrunePort`."""

    store: RetentionStorePort
    book: PurchasingRuleBook
    clock: UtcClock

    async def prune(self) -> None:
        now = self.clock.now()
        for tenant_id, workspace_id in await self.store.scopes():
            scope = ContextScope(TenantId(tenant_id), WorkspaceId(workspace_id))
            try:
                rules = (await self.book.current(scope, PurchasingRuleKey.RULES)).policy
            except (DomainError, ValueError):
                # A stored version today's schema refuses (pydantic's error is
                # a ValueError): keep everything there until it is fixed.
                _LOG.warning(
                    "purchasing rules unreadable; nothing deleted",
                    extra={"tenant_id": str(tenant_id), "workspace_id": str(workspace_id)},
                )
                continue
            term = rules.retention
            if term is None:
                continue
            pruned = await self.store.prune(
                (tenant_id, workspace_id),
                # A year is 365 days here: a day kept longer harms no one.
                cases_before=now - timedelta(days=365 * term.case_years),
                outcomes_before=now - timedelta(days=term.mail_outcome_days),
                mail_before=now - timedelta(days=term.mailbox_term_days),
            )
            if pruned.cases or pruned.outcomes or pruned.mail:
                _LOG.info(
                    "deleted purchasing rows past their term",
                    extra={
                        "tenant_id": str(tenant_id),
                        "workspace_id": str(workspace_id),
                        "cases": pruned.cases,
                        "outcomes": pruned.outcomes,
                        "mail": pruned.mail,
                        "rules_ref": rules.ref,
                    },
                )
