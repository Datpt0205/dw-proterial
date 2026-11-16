"""The document forms a tenant's ``document-forms`` skill names, and what code
holds each to (ticket 42 family 3, dw_sales ADR 0014).

The fixed-label reader (`adapters.rfq_excel`) reads one layout, the mock
customers' English labels, and its ``RFQ No.`` marker is what makes a file a
request for quotation. Every new customer's form misses it. Which header or
label of a customer's form means which field is words, in the customer's
language: the tenant's, in its version of this skill, a text a person
proposes and the head approves. What a form DOES stays code's: each names
one route from a closed set (`FORM_ROUTES`: the quotation flow, whose
request code verifies value by value at its cells), and the customer it
belongs to, so one customer's form never reads another's file.

**How a skill names its forms.** In its instructions, one block per form, at
the start of a line, written as every skill a fixed step reads writes its
kinds (`skill_blocks`)::

    - kind: velatrix_rfq
      customer: VLX
      route: quote_request
      means: Velatrix's request sheet. "Số phiếu" beside the top is the
        request number, "Tiền tệ" the currency; in the table, "Mã hàng" is
        their part number and "Số lượng (m)" the quantity in metres ...

``kind`` is the form's name (lowercase words joined by ``_``), ``customer``
the customer's code in master data or ``any`` for a form any customer may
send, ``route`` the flow it opens, one of `FORM_ROUTES`, ``means`` the words
the model reads it by. `document_forms_of` reads the blocks and refuses
anything else in them: an unknown route, a customer that is no code, a form
named twice. It is asked when a version is proposed (refusing the proposal)
and whenever the skill is served (a version that no longer reads is not
used: the file is read as with the step off). Text outside the blocks is
guidance every reading is given (`guidance`).
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.catalog import CustomerCode
from dw_sales.domain.skill_blocks import blocks_of

__all__ = [
    "ANY_CUSTOMER",
    "DOCUMENT_FORMS",
    "FORM_ROUTES",
    "MAX_FORMS",
    "NO_FORM",
    "DocumentForm",
    "DocumentForms",
    "FormRoute",
    "document_forms_of",
    "guidance",
]

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

# The skill whose forms read a customer's document no fixed reader reads.
DOCUMENT_FORMS: Final = "document-forms"
# The flows a form may open: the quotation flow, whose request code finds
# value by value at its cells. A purchase order is read by its approved
# layout (ticket 18), never by words.
FormRoute = Literal["quote_request"]
FORM_ROUTES: Final[frozenset[str]] = frozenset(get_args(FormRoute))
# A form any customer may send (the platform's own forms say so).
ANY_CUSTOMER: Final = "any"
# What the model answers when the document is none of the forms it is shown.
NO_FORM: Final = "none"
# A company reads a few dozen customers' forms at most; the ones a customer
# may send are in the schema of every call that reads that customer's file.
MAX_FORMS: Final = 60

FormName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$", max_length=40)]
# The lines a form's block may hold (`skill_blocks`).
_FIELDS: Final = frozenset({"customer", "route", "means"})
_START: Final = "- kind:"


class DocumentForm(BaseModel):
    """One form as the skill names it."""

    model_config = _FROZEN

    name: FormName
    # The customer it is read for; None: any customer (``any``).
    customer: CustomerCode | None
    route: FormRoute
    means: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def _named(self) -> Self:
        if self.name == NO_FORM:
            raise ValueError(f'"{NO_FORM}" is the answer that names no form, not a form')
        return self

    def block(self) -> str:
        """The form as the skill writes it, for a reading's prompt."""
        customer = ANY_CUSTOMER if self.customer is None else self.customer
        return (
            f"{_START} {self.name}\n  customer: {customer}\n  route: {self.route}\n"
            f"  means: {self.means}"
        )


class DocumentForms(BaseModel):
    """Every form a version of the skill names, in its order."""

    model_config = _FROZEN

    forms: tuple[DocumentForm, ...] = Field(min_length=1, max_length=MAX_FORMS)

    @model_validator(mode="after")
    def _each_once(self) -> Self:
        names = [form.name for form in self.forms]
        if len(set(names)) != len(names):
            raise ValueError("the skill names a form twice")
        return self

    def of(self, customer_code: str) -> tuple[DocumentForm, ...]:
        """The forms a file of ``customer_code``'s may be read as: its own and
        those any customer may send. Never another customer's."""
        return tuple(f for f in self.forms if f.customer in (None, customer_code))


def document_forms_of(instructions: str) -> DocumentForms:
    """The forms ``instructions`` name (module docstring). Raises ValueError,
    saying what is wrong in words, for a block that does not read or a set
    that does not hold."""
    blocks = blocks_of(instructions, "kind", _FIELDS)
    if not blocks:
        raise ValueError(f'the skill names no form: each starts with a line "{_START} <name>"')
    forms = []
    for block in blocks:
        name = block["kind"]
        for key in ("customer", "route", "means"):
            if key not in block:
                raise ValueError(f"the form {name} names no {key}")
        if block["route"] not in FORM_ROUTES:
            raise ValueError(
                f"the form {name} names the route {block['route']}, which is not one of "
                + ", ".join(sorted(FORM_ROUTES))
            )
        customer = block["customer"]
        forms.append(
            {
                "name": name,
                "customer": None if customer == ANY_CUSTOMER else customer,
                "route": block["route"],
                "means": block["means"],
            }
        )
    return DocumentForms.model_validate({"forms": forms})


def guidance(instructions: str) -> str:
    """The skill's words outside its form blocks: what every reading is told,
    whichever customer's file it reads. A block is its head line and the
    indented lines after it, as `skill_blocks` reads one."""
    kept: list[str] = []
    inside = False
    for raw in instructions.replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.startswith(_START):
            inside = True
            continue
        if inside and line.strip() and line[0].isspace():
            continue
        inside = False
        kept.append(line)
    return "\n".join(kept).strip()
