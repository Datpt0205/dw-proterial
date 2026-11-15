"""The platform's example mails a proposed skill version is replayed on
(ticket 40, `application.skill_replay`), read from the eval fixtures the
worker image ships (`infra/docker/worker.Dockerfile` copies `evals/fixtures`).

- The golden replies of `sales_reply@2.0.0`
  (`evals/fixtures/cases/sales_reply_golden.json`): fictional mails in
  Vietnamese, English and Japanese, each on one case with the intents it is
  read as; the ones tagged ``conditional`` or ``non_answer`` are also security
  cases (never ``accepts``).
- The thread agent's injections
  (`evals/fixtures/cases/sales_thread_agent_security.json`): mails that ask
  the reader to accept, to look up another customer or to break its rules,
  security cases only.

Each case is bound as the eval binds it: its numbers and status, no lines.
A file that is missing gives no examples, and a replay with none stores
nothing to compare (the page says so); a file that does not hold to the
shape fails at startup.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final

from dw_platform.domain.messages import EmailAddress, InboundMessage, MailAuthentication
from dw_sales.application.skill_replay import ReplayExample
from dw_sales.application.thread_tools import CaseView, ThreadMessageView
from dw_sales.application.threads import AskedAbout, question
from dw_sales.domain.orders import OrderStatus
from dw_sales.domain.quotes import QuoteStatus
from dw_sales.domain.reply_intent import Author

__all__ = ["FixtureReplayExamples"]

GOLDEN: Final = Path("evals") / "fixtures" / "cases" / "sales_reply_golden.json"
SECURITY: Final = Path("evals") / "fixtures" / "cases" / "sales_thread_agent_security.json"
# The golden set's case kinds: the case's kind, its status and what Sales
# asked, as `dw_sales.evals.replies` binds them.
_CASES: Final[Mapping[str, tuple[str, str, AskedAbout]]] = {
    "spec": ("quote", QuoteStatus.SPEC_DISCUSSION.value, "spec"),
    "decline": ("quote", QuoteStatus.DECLINED.value, "decline"),
    "correction": ("order", OrderStatus.CORRECTION_REQUESTED.value, "correction"),
    "order": ("order", OrderStatus.IN_REVIEW.value, "order"),
    "sales_order": ("order", OrderStatus.IN_REVIEW.value, "order"),
    "sales_spec": ("quote", QuoteStatus.DESIGN_REPLIED.value, "quote"),
}
_SECURITY_TAGS: Final = frozenset({"conditional", "non_answer"})
# The case the injections are written against.
_INJECTED_ON: Final = ("order", "NRV-PO-26-0457", OrderStatus.CONFIRMATION_SENT.value)
_RECEIVED: Final = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


def _message(spec: Mapping[str, Any]) -> InboundMessage:
    return InboundMessage(
        message_id=str(spec["id"]),
        sender=EmailAddress(address=str(spec.get("sender", "customer@example.com"))),
        subject=str(spec["subject"]),
        received_at=_RECEIVED,
        body_text=str(spec["body"]),
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
    )


def _golden(spec: Mapping[str, Any]) -> ReplayExample:
    kind, status, asked = _CASES[str(spec["case"])]
    number = str(spec["number"])
    author: Author = "sales" if spec.get("author") == "sales" else "customer"
    return ReplayExample(
        example_id=str(spec["id"]),
        message=_message(spec),
        customer_code=number.split("-", 1)[0],
        cases=(CaseView(kind=kind, numbers=(number,), status=status, lines=()),),
        earlier=(),
        author=author,
        about=question(asked, number, spec.get("asked")),
        gold=frozenset(spec["gold"]),
        never_accepts=bool(set(spec.get("tags", ())) & _SECURITY_TAGS),
    )


def _injection(spec: Mapping[str, Any]) -> ReplayExample:
    kind, number, status = _INJECTED_ON
    earlier = tuple(
        ThreadMessageView(
            author=m["author"],
            received_on=date.fromisoformat(m["received_on"]),
            subject=m["subject"],
            text=m["text"],
        )
        for m in spec.get("earlier", ())
    )
    return ReplayExample(
        example_id=str(spec["id"]),
        message=_message(spec),
        customer_code=number.split("-", 1)[0],
        cases=(CaseView(kind=kind, numbers=(number,), status=status, lines=()),),
        earlier=earlier,
        author="customer",
        about=question("order", number),
        gold=None,
        never_accepts=True,
    )


@dataclass(frozen=True)
class FixtureReplayExamples:
    """Implements `ReplayExamplesPort` from the fixtures under ``root`` (the
    repository, or the image's `/app`), read once at startup."""

    held: tuple[ReplayExample, ...]

    @classmethod
    def load(cls, root: Path) -> FixtureReplayExamples:
        found: list[ReplayExample] = []
        if (root / GOLDEN).is_file():
            golden = json.loads((root / GOLDEN).read_text(encoding="utf-8"))["replies"]
            found.extend(_golden(spec) for spec in golden)
        if (root / SECURITY).is_file():
            security = json.loads((root / SECURITY).read_text(encoding="utf-8"))
            found.extend(_injection(spec) for spec in security["injection"])
        return cls(tuple(found))

    def examples(self) -> Sequence[ReplayExample]:
        return self.held
