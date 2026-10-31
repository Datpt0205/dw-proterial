"""The tenant's Purchasing rules, as one versioned document.

What Proterial's process decides (which fields a PR form requires, whose mail
may be a request, and, as later slices arrive, the approval limits, who
approves and Bravo's fields) is a value in this document, never a constant in
code (ADR 0013 decision 5). The platform layer ships in
``configs/policies/purchasing_rules@<version>.yaml``; a tenant's own version
replaces it whole (`dw_purchasing.application.rules`). A case stamps the
version it was received under.

Every field here has a reader; a section a slice does not read yet is not
written yet (failure-modes #1).
"""

from __future__ import annotations

import re
from typing import Annotated, Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_purchasing.domain.requests import Currency, PurchaseRequest, RequiredField

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

POLICY_ID: Final = "purchasing_rules"
_DOMAIN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


class PrFormRules(BaseModel):
    """What a request must carry to be received (DW02 function 1)."""

    model_config = _FROZEN

    required: frozenset[RequiredField]
    max_lines: int = Field(ge=1, le=100)
    currencies: frozenset[Currency] = Field(min_length=1)
    # The currency of a request that names none: the company's, a rule, never
    # a model's guess.
    default_currency: Currency

    @model_validator(mode="after")
    def _default_is_allowed(self) -> Self:
        if self.default_currency not in self.currencies:
            raise ValueError("the default currency is not one the form allows")
        return self


class PurchasingRules(BaseModel):
    """One version of the tenant's rules (module docstring)."""

    model_config = _FROZEN

    version: Annotated[str, Field(pattern=r"^\d+\.\d+\.\d+(?:-[a-z0-9.]+)?$")]
    pr_form: PrFormRules
    # The company's mail domains: only a sender from one of them, verified by
    # the mail system, may be a requester.
    internal_domains: frozenset[str] = Field(min_length=1)

    @field_validator("internal_domains")
    @classmethod
    def _domains(cls, value: frozenset[str]) -> frozenset[str]:
        if any(_DOMAIN.fullmatch(d) is None or len(d) > 253 for d in value):
            raise ValueError("an internal domain is not a lowercase domain name")
        return value

    @property
    def ref(self) -> str:
        """What a case stamps: ``purchasing_rules@<version>``."""
        return f"{POLICY_ID}@{self.version}"

    def refusals(self, request: PurchaseRequest) -> tuple[str, ...]:
        """Why this request cannot be received under these rules, as codes
        (``missing:<field>``, ``too_many_lines``, ``currency_not_allowed``);
        empty when it can."""
        found = [f"missing:{field}" for field in request.missing(self.pr_form.required)]
        if len(request.lines) > self.pr_form.max_lines:
            found.append("too_many_lines")
        if request.currency not in self.pr_form.currencies:
            found.append("currency_not_allowed")
        return tuple(found)
