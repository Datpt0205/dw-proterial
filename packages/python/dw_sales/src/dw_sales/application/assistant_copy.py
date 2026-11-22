"""The words DW1's assistant says in its own sentences
(`configs/copy/sales_assistant@<version>.yaml`, ticket 42 family 6).

The assistant (dw_sales ADR 0007) decides what it answers and from which
case; this copy only says it where code answers without the model, or
instead of a wording that did not pass its check. Code fills every
placeholder from what it looked up: a case's number, customer code, status
words, dates and counts. Never an amount: the facts hold none.

A tenant's own wording is its version of this copy, proposed and approved on
/sales/rules like every rule version (`RuleKey.ASSISTANT`), never an edit
here. What the assistant may answer (`QuestionKind`) stays code: it is the
guard on which data a question may reach, not a sentence.

Each template names only the placeholders its own sentence fills, written
`{name}` (`handoffs._plain_placeholders`, the one check of a template's
placeholders), read from the field's own schema, so the rules editor lists
the same set the check holds.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.application.handoffs import _named, _plain_placeholders
from dw_sales.application.ports import SalesScope

_FROZEN = ConfigDict(frozen=True, extra="forbid")


def _words(*names: str, max_length: int = 300) -> Any:
    """A sentence naming at most ``names``."""
    return Field(min_length=1, max_length=max_length, json_schema_extra=_named(frozenset(names)))


class AssistantWords(BaseModel):
    """Every sentence the assistant's code says, by what it answers."""

    model_config = _FROZEN

    # What the assistant answers: the general conversation, a case's own,
    # and where the rest is asked (ticket 46).
    catalog: str = _words()
    case_catalog: str = _words()
    elsewhere: str = _words()
    # Before the catalog: no reading of the question, or one outside it.
    not_understood: str = _words()
    out_of_scope: str = _words()
    out_of_scope_case: str = _words()
    # A status question naming no case.
    which_order: str = _words()
    which_quote: str = _words()
    # ``{what}`` is `order_word` or `quote_word`, ``{reference}`` the number
    # as the person wrote it.
    not_found: str = _words("what", "reference")
    order_word: str = _words(max_length=60)
    quote_word: str = _words(max_length=60)
    # ``{case}``: the case as its page names it.
    only_this_case: str = _words("case")
    linked: str = _words("case")
    # An order's status, then each part that holds.
    order_status: str = _words("po_no", "revision", "customer", "status", "received_on")
    order_flags: str = _words("open_flags", "blocking_flags")
    order_cross_check: str = _words()
    # A quote's status, then each part that holds.
    quote_status: str = _words("request_no", "customer", "status", "received_on")
    no_number: str = _words(max_length=60)
    quote_due: str = _words("due")
    quote_late: str = _words("due")
    quote_ycbg: str = _words("ycbg_no")
    quote_flags: str = _words("open_flags")
    # The person's work: a head line, one line per item, the rest counted.
    no_work: str = _words()
    no_overdue: str = _words()
    work_head: str = _words("count")
    overdue_head: str = _words("count")
    work_item: str = _words("what", "customer", "next_step")
    work_item_due: str = _words("what", "customer", "next_step", "due")
    unknown_customer: str = _words(max_length=60)
    work_more: str = _words("more")
    # A mail waiting on the person, and what they do with it.
    mail_work: str = _words(max_length=60)
    mail_step: str = _words(max_length=60)
    # A step of a case asked for (ticket 46): said above the case page's own
    # control in its conversation; in the general one, where to ask.
    offer_reply: str = _words()
    offer_reminder: str = _words()
    offer_thread: str = _words()
    act_in_case: str = _words()
    # ``{what}`` in `not_found` for a step naming a number no case holds.
    case_word: str = _words(max_length=60)
    # A decision on one of the case's open flags (ticket 56): said back word
    # for word for the PIC to confirm, and what DW1 asks when it cannot yet.
    # ``{flag}``: the flag's words and line; ``{decision}``: one of the two
    # decision words; ``{reason}``: `decide_reason` filled, or empty.
    decide_confirm: str = _words("flag", "decision", "reason")
    decide_accept_word: str = _words(max_length=60)
    decide_ask_word: str = _words(max_length=60)
    decide_reason: str = _words("reason")
    decide_which_flag: str = _words("flags")
    decide_which_way: str = _words("flag")
    decide_need_reason: str = _words("flag")
    decide_no_flag: str = _words()
    decide_orders_only: str = _words()
    decide_done: str = _words("flag", "decision")
    # An SO line's value asked to be written into Bravo (ticket 56 over 53):
    # said back for the PIC to confirm, then proposed for approval.
    # ``{field}``: `write_date_word` or `write_quantity_word`.
    write_confirm: str = _words("so", "line", "field", "value")
    write_date_word: str = _words(max_length=60)
    write_quantity_word: str = _words(max_length=60)
    write_which_line: str = _words("lines")
    write_which_field: str = _words("line")
    write_which_value: str = _words("field", "line")
    write_no_so: str = _words()
    write_orders_only: str = _words()
    write_done: str = _words("field", "line")
    # What the chat shows while a turn is worked on.
    step_read: str = _words(max_length=60)
    step_look: str = _words(max_length=60)

    @model_validator(mode="after")
    def _placeholders(self) -> AssistantWords:
        for name, field in type(self).model_fields.items():
            extra = field.json_schema_extra
            assert isinstance(extra, dict)
            named = extra["x-placeholders"]
            assert isinstance(named, list)
            _plain_placeholders(getattr(self, name), frozenset(str(p).strip("{}") for p in named))
        return self

    def say(self, name: str, **values: object) -> str:
        """Sentence ``name`` filled with ``values``; a template names only
        its own placeholders, so each it names is among them."""
        template: str = getattr(self, name)
        return template.format_map(values)


class AssistantCopy(BaseModel):
    """`configs/copy/sales_assistant@<version>.yaml`: the assistant's words."""

    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    copy_id: str = Field(pattern=r"^sales_assistant$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    words: AssistantWords

    @property
    def ref(self) -> str:
        return f"{self.copy_id}@{self.version}"


class AssistantCopyPort(Protocol):
    """The assistant's words for a scope's tenant: theirs, else the platform's."""

    async def assistant_copy(self, scope: SalesScope) -> AssistantCopy: ...
