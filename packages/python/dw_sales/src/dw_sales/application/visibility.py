"""Which cases a person may see, in a tenant that narrows record reads.

Đạt, 2026-10-28: a Sales PIC sees their own cases, the ones nobody has yet,
and the ones they are asked to check; the head sees them all. The platform
already owns "whose records may this person see" (ADR-003): in a tenant set
to `restricted`, the membership lookup resolves `visible_owners`, the person
and everyone who reports up to them, once per context; an open tenant, an
admin, and a support context carry None, no limit. This module only applies
it to a case, whose owner is its assignee:

- a case nobody is assigned is the team's pool, seen by every member;
- an assignee among `visible_owners` (the caller, or one of their reports);
- a case waiting on a checker step (a cross-check, a quotation's approval)
  that the caller may take: they are the one asked to check it.

A case outside these reads as not found, never as forbidden: a 403 would
confirm the case exists.
"""

from __future__ import annotations

import uuid

from dw_platform.application.access_context import AccessContext
from dw_sales.application.next_steps import checker_scope
from dw_sales.domain.dispositions import CaseKind


def sees_case(
    viewer: AccessContext, kind: CaseKind, status: str, assigned_to: uuid.UUID | None
) -> bool:
    owners = viewer.visible_owners
    if owners is None or assigned_to is None or assigned_to in owners:
        return True
    checker = checker_scope(kind, status)
    return checker is not None and viewer.has_scope(checker.value)
