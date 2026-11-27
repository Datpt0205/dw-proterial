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
  that the caller may take: they are the one asked to check it;
- an order held on an open `missing_noc_esf` (`OrderCase.awaits_export_control`)
  to the export-control PIC (`EXPORT_CONTROL_SCOPES`): they are told of it
  (ticket 78) and must be able to open and decide it. Only while it holds,
  and only for a read or the acknowledgement itself (the caller says so,
  `support.stored_order`'s ``export_control``): seeing it is not owning it,
  so every other step on another PIC's order reads as not found as before.
  Acknowledged, it is the assignee's again.

A case outside these reads as not found, never as forbidden: a 403 would
confirm the case exists.

**A reader's rule, not a lane's** (Đạt, 2026-11-27, kept by recommendation).
A step driven by a mail or a file changes a case whoever owns it: the
processing of a customer's mail revising an order (`inbox_lane`, then
`inbox_service`), PC's reply proposed on the case (`pc_replies`), a matching
read-back passing the cross-check (`cross_check_on_match`), the customer's
silence recorded as agreement (`followups`, `confirmations.record_implied`).
Each acts for no person: it audits as its own system actor
(`lane_audit_event`, ADR 0011) and loads the workspace's cases with no viewer
(`support.stored_order(viewer=None)`, or the store directly), so this module
is never asked. Narrowing a lane to one person's records would leave
another PIC's order unprocessed, which is a lost mail, not a kept secret.
What it changes is still read only through this rule: the person who may
not see the case does not see the change either
(`test_case_visibility.py`).
"""

from __future__ import annotations

import uuid

from dw_platform.application.access_context import AccessContext
from dw_sales.application.access import EXPORT_CONTROL_SCOPES
from dw_sales.application.next_steps import checker_scope
from dw_sales.domain.dispositions import CaseKind


def sees_case(
    viewer: AccessContext,
    kind: CaseKind,
    status: str,
    assigned_to: uuid.UUID | None,
    *,
    export_held: bool = False,
) -> bool:
    """``export_held``: the order awaits the export-control PIC
    (`OrderCase.awaits_export_control`) and the call is one the hold opens
    to them (a read, or its acknowledgement); False for a quote, for every
    other step, and the narrow reading when a caller does not say."""
    owners = viewer.visible_owners
    if owners is None or assigned_to is None or assigned_to in owners:
        return True
    if export_held and all(viewer.has_scope(scope.value) for scope in EXPORT_CONTROL_SCOPES):
        return True
    checker = checker_scope(kind, status)
    return checker is not None and viewer.has_scope(checker.value)
