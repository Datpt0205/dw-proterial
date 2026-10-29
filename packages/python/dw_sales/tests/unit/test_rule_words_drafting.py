"""A rule draft from a person's words (dw_sales ADR 0006, decision 3), through
the request, the worker and the draft the editor opens."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from dw_kernel.errors import DomainError, PermissionDeniedError, QuotaExceededError
from dw_sales.application.access import SalesScopes
from dw_sales.application.rule_drafts import RuleDraftView
from dw_sales.application.rule_words import RULE_CHANGE_IN_WORDS
from dw_sales.application.rules import RuleKey
from dw_sales.evals.graders import AN as _AN
from dw_sales.evals.recorded import Recorded
from dw_sales.evals.rule_drafts import Bench
from dw_sales.evals.world import ALPHA, Caller

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[5]
AN = replace(_AN, scopes=_AN.scopes | {SalesScopes.RULES_PROPOSE})
FOCUS = "emails.confirmation_draft"


def _drafted(
    model: Recorded | None,
    key: RuleKey,
    words: str,
    *,
    focus: str | None = None,
    caller: Caller = AN,
) -> RuleDraftView:
    bench = Bench.of(REPO, model, (caller,))
    requested = asyncio.run(bench.service().request_words(caller.context(), key, words, focus))
    assert requested.status == "queued" and requested.request == words
    asyncio.run(bench.drafting().draft(ALPHA, requested.draft_id))
    return asyncio.run(bench.service().get(caller.context(), requested.draft_id))


def _answer(*changes: tuple[str, Any], understood: bool = True) -> dict[str, Any]:
    return {"understood": understood, "changes": [{"path": p, "value": v} for p, v in changes]}


def test_what_the_person_asked_is_drafted_ready_for_the_editor() -> None:
    model = Recorded(raw=_answer(("order_unconfirmed.remind.after_hours", 6)))

    view = _drafted(model, RuleKey.FOLLOWUPS, "nhắc PIC sau 6 giờ")

    assert view.status == "ready", view.problems
    assert view.document is not None
    assert view.document["order_unconfirmed"]["remind"]["after_hours"] == 6
    assert view.machine_read == ["order_unconfirmed.remind.after_hours"]
    assert (view.prompt_ref, view.model_profile) == (str(RULE_CHANGE_IN_WORDS), "onprem")
    # The model was shown the words and the document, as data.
    (_, _, inputs) = model.calls[0]
    assert inputs["request"] == "nhắc PIC sau 6 giờ"
    assert "order_unconfirmed.remind.after_hours" in inputs["paths"]


def test_a_mail_rewritten_from_an_example_is_shown_only_its_own_kind() -> None:
    model = Recorded(raw=_answer(("vi.subject", "Xác nhận đơn ${po_no} (lần sửa ${revision})")))

    view = _drafted(
        model, RuleKey.EMAILS, "Viết ngắn gọn như thư này: Xác nhận đơn ...", focus=FOCUS
    )

    assert view.status == "ready", view.problems
    assert view.focus == FOCUS
    (_, _, inputs) = model.calls[0]
    assert "decline_draft" not in inputs["document"]
    assert view.machine_read == [f"{FOCUS}.vi.subject"]


def test_a_refused_change_still_opens_the_version_in_force_with_why() -> None:
    model = Recorded(raw=_answer(("order_unconfirmed.remind.auto_confirm", True)))

    view = _drafted(model, RuleKey.FOLLOWUPS, "tự xác nhận đơn")

    assert view.status == "refused"
    assert [(p.code, p.where) for p in view.problems] == [
        ("path_unknown", "order_unconfirmed.remind.auto_confirm")
    ]
    assert view.document is not None and view.machine_read == []


@pytest.mark.parametrize(
    ("model", "why"),
    [
        (None, "model_not_configured"),
        (Recorded(failure=QuotaExceededError("hết lượt")), "model_quota"),
    ],
)
def test_without_a_usable_answer_the_version_in_force_is_offered(
    model: Recorded | None, why: str
) -> None:
    view = _drafted(model, RuleKey.FOLLOWUPS, "nhắc sau 6 giờ")
    assert (view.status, [p.code for p in view.problems]) == ("unavailable", [why])


def test_a_price_rule_is_drafted_only_for_someone_who_reads_prices() -> None:
    no_price = Caller(
        AN.user_id,
        AN.name,
        AN.email,
        frozenset({SalesScopes.RULES_PROPOSE.value, SalesScopes.CASE_READ.value}),
    )
    bench = Bench.of(REPO, Recorded(raw=_answer()), (no_price,))
    with pytest.raises(PermissionDeniedError):
        asyncio.run(
            bench.service().request_words(no_price.context(), RuleKey.PRICING, "giảm sàn giá")
        )
    assert bench.store.state(ALPHA).drafts == {}


def test_an_asker_who_lost_the_price_scope_gets_nothing_drafted() -> None:
    model = Recorded(raw=_answer())
    bench = Bench.of(REPO, model, (AN,))
    requested = asyncio.run(bench.service().request_words(AN.context(), RuleKey.PRICING, "x"))
    demoted = Caller(AN.user_id, AN.name, AN.email, frozenset({SalesScopes.RULES_PROPOSE.value}))
    drafting = Bench.of(REPO, model, (demoted,))
    drafting.store = bench.store
    asyncio.run(drafting.drafting().draft(ALPHA, requested.draft_id))
    view = asyncio.run(bench.service().get(AN.context(), requested.draft_id))
    assert (view.status, model.calls) == ("failed", [])


@pytest.mark.parametrize(
    ("words", "focus", "rule"),
    [("   ", None, "request_empty"), ("x" * 2001, None, "request_long"), ("x", "a/b", "focus")],
)
def test_a_request_is_refused_with_its_reason(words: str, focus: str | None, rule: str) -> None:
    bench = Bench.of(REPO, None, (AN,))
    with pytest.raises(DomainError) as refused:
        asyncio.run(bench.service().request_words(AN.context(), RuleKey.FOLLOWUPS, words, focus))
    assert refused.value.details["rule"] == rule
