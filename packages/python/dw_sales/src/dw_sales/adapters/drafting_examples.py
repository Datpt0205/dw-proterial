"""The platform's examples a proposed version of the ``handoffs`` or the
``reply-drafts`` skill is replayed on (ticket 42 family 5), read from the
eval fixtures the worker image ships (`infra/docker/worker.Dockerfile`
copies `evals/fixtures`).

- **The hand-offs** (`FixtureHandoffKindExamples`): ticket 33's fictional
  golden mails (`evals/fixtures/cases/sales_handoff_golden.json`), each with
  the kind it is routed as and what a person copies from it, and the new
  kind's mails of the family's eval (`sales_handoff_kinds.json`), so a
  version adding that kind is graded on mails of it.
- **The reply drafts** (`FixtureReplyKindExamples`): ticket 32's twelve
  drafts of the fictional M04 order, the facts, letter and question code
  builds for each (`evals/fixtures/cases/sales_reply_kinds_examples.json`).

A file that is missing gives no examples, and a replay with none stores
nothing to compare (the page says so); a file that does not hold to the
shape fails at startup.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from pydantic import TypeAdapter

from dw_platform.domain.messages import EmailAddress, InboundMessage, MailAuthentication
from dw_sales.application.handoff_kinds import HandoffKindExample
from dw_sales.application.reply_drafts import ReplyKindExample
from dw_sales.domain.reply_kinds import ReplyKind

__all__ = ["FixtureHandoffKindExamples", "FixtureReplyKindExamples"]

_CASES: Final = Path("evals") / "fixtures" / "cases"
HANDOFF_GOLDEN: Final = _CASES / "sales_handoff_golden.json"
HANDOFF_KINDS: Final = _CASES / "sales_handoff_kinds.json"
REPLY_EXAMPLES: Final = _CASES / "sales_reply_kinds_examples.json"
_RECEIVED: Final = datetime(2026, 10, 10, 2, 0, tzinfo=UTC)
_DRAFT: Final[TypeAdapter[ReplyKind]] = TypeAdapter(ReplyKind)


def _message(spec: Mapping[str, Any]) -> InboundMessage:
    return InboundMessage(
        message_id=str(spec["id"]),
        sender=EmailAddress(address=str(spec["sender"])),
        subject=str(spec.get("subject", "")),
        received_at=_RECEIVED,
        body_text=str(spec["body"]),
        authentication=MailAuthentication(spf="pass", dkim="pass", dmarc="pass"),
    )


def _handoff(spec: Mapping[str, Any], kind: str) -> HandoffKindExample:
    gold: Mapping[str, Any] = spec["gold"]
    phrases = (*gold.get("problem", ()), *gold.get("items", ()), *gold.get("phrases", ()))
    return HandoffKindExample(
        example_id=str(spec["id"]),
        message=_message(spec),
        kind=kind,
        po_no=gold.get("po_no"),
        lot=gold.get("lot_no", gold.get("lot")),
        phrases=tuple(str(p).casefold() for p in phrases),
        lines=len(gold.get("lines", ())),
    )


@dataclass(frozen=True)
class FixtureHandoffKindExamples:
    """Implements `HandoffKindExamplesPort` from the fixtures under ``root``
    (the repository, or the image's `/app`), read once at startup."""

    held: tuple[HandoffKindExample, ...]

    @classmethod
    def load(cls, root: Path) -> FixtureHandoffKindExamples:
        found: list[HandoffKindExample] = []
        if (root / HANDOFF_GOLDEN).is_file():
            golden = json.loads((root / HANDOFF_GOLDEN).read_text(encoding="utf-8"))["mails"]
            found.extend(_handoff(spec, str(spec["kind"])) for spec in golden)
        if (root / HANDOFF_KINDS).is_file():
            new = json.loads((root / HANDOFF_KINDS).read_text(encoding="utf-8"))["new_kind"]
            name = new["block"].split("\n", 1)[0].removeprefix("- kind:").strip()
            found.extend(_handoff(spec, name) for spec in new["mails"])
        return cls(tuple(found))

    def examples(self) -> Sequence[HandoffKindExample]:
        return self.held


@dataclass(frozen=True)
class FixtureReplyKindExamples:
    """Implements `ReplyKindExamplesPort` from the fixtures under ``root``,
    read once at startup."""

    held: tuple[ReplyKindExample, ...]

    @classmethod
    def load(cls, root: Path) -> FixtureReplyKindExamples:
        if not (root / REPLY_EXAMPLES).is_file():
            return cls(())
        specs = json.loads((root / REPLY_EXAMPLES).read_text(encoding="utf-8"))["examples"]
        return cls(
            tuple(
                ReplyKindExample(
                    example_id=str(spec["id"]),
                    drafts=_DRAFT.validate_python(spec["drafts"]),
                    facts=str(spec["facts"]),
                    example=str(spec["example"]),
                    question=str(spec["question"]),
                    po_no=str(spec["po_no"]),
                )
                for spec in specs
            )
        )

    def examples(self) -> Sequence[ReplyKindExample]:
        return self.held
