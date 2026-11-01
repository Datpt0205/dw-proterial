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
from decimal import Decimal
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dw_purchasing.domain.checks import CrossCheck, PurchaseFindingCode
from dw_purchasing.domain.orders import BravoPoLayout
from dw_purchasing.domain.requests import (
    Currency,
    Price,
    PurchaseRequest,
    RequiredField,
)

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


# The scopes an approval may be stamped with: the ones the purchasing
# migrations declare (`PurchasingScopes`, held to this by test). Which band
# of amounts each decides is the tenant's rule; which person holds each is
# the platform's catalogue of roles and permission sets.
ApproveScope = Literal[
    "purchasing.approve.tier1", "purchasing.approve.tier2", "purchasing.approve.tier3"
]


class ApprovalTier(BaseModel):
    """Requests up to ``up_to`` (inclusive; None for no limit) are decided by
    a holder of ``scope``; ``label`` names who that is, as people say it."""

    model_config = _FROZEN

    up_to: Price | None
    scope: ApproveScope
    label: str = Field(min_length=1, max_length=80)


class ApprovalRules(BaseModel):
    """Who approves a request, by its amount (DW02 function 2)."""

    model_config = _FROZEN

    # The currency the limits are in; a request in another goes to the last tier.
    currency: Currency
    # Ascending limits; the last has none.
    tiers: tuple[ApprovalTier, ...] = Field(min_length=1, max_length=5)
    # How far above the reference an estimate may be before it is a finding.
    price_tolerance_percent: Decimal = Field(ge=0, le=100)
    # Findings that send a request to the last tier whatever its amount.
    escalate: frozenset[PurchaseFindingCode]
    # How far above the approved tier's limit a choice of suppliers may come
    # before it goes back for approval at the tier its total names (rules
    # 1.5.0; 0: any amount above the limit goes back).
    reapproval_tolerance_percent: Decimal = Field(default=Decimal(0), ge=0, le=100)

    @model_validator(mode="after")
    def _ascending_and_open_ended(self) -> Self:
        limits = [tier.up_to for tier in self.tiers]
        if limits[-1] is not None or any(limit is None for limit in limits[:-1]):
            raise ValueError("every tier but the last has a limit, and the last has none")
        bounded = [limit for limit in limits if limit is not None]
        if bounded != sorted(set(bounded)):
            raise ValueError("tier limits are strictly ascending")
        return self

    def tier_for(self, check: CrossCheck) -> ApprovalTier:
        """The tier that decides ``check``: the last one when the amount is
        unknown, in another currency, or a finding escalates it; else the
        first whose limit the amount does not pass."""
        if check.amount is None or check.currency != self.currency or check.codes & self.escalate:
            return self.tiers[-1]
        return next(tier for tier in self.tiers if tier.up_to is None or check.amount <= tier.up_to)


class RfqRules(BaseModel):
    """Whom DW2 drafts a request for quotation to (DW02 function 3)."""

    model_config = _FROZEN

    # At most this many suppliers asked per line, from those the master data
    # lists for its item.
    max_suppliers_per_line: int = Field(ge=1, le=10)
    # The reply date an RFQ asks for, in days from the day it is drafted.
    reply_days: int = Field(ge=1, le=60)


class RetentionRules(BaseModel):
    """How long DW2 keeps a tenant's rows (since 1.6.0): the tenant's own
    number, changed like any rule and decided by a second person, so the
    accountant's answer lands as a setting, not a release. Bounded both
    ways: a term too short to be deliberate, or longer than any law asks,
    is not a version."""

    model_config = _FROZEN

    # A purchase case, by when it was received; its mail outcomes go with it.
    case_years: int = Field(ge=1, le=30)
    # What DW2 did with one mail, by when it was settled.
    mail_outcome_days: int = Field(ge=30, le=3650)


class PurchasingRules(BaseModel):
    """One version of the tenant's rules (module docstring). Written as the
    platform's rule versions hold every document (`ck_rule_versions_document`):
    its ``policy_id`` the key, its ``policy_version`` the version; a file
    names the version ``version``."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    policy_id: Literal["purchasing_rules"] = POLICY_ID
    version: Annotated[str, Field(alias="policy_version", pattern=r"^\d+\.\d+\.\d+$")]
    pr_form: PrFormRules
    # The company's mail domains: only a sender from one of them, verified by
    # the mail system, may be a requester.
    internal_domains: frozenset[str] = Field(min_length=1)
    # Who approves what. Absent in 1.0.0, which received requests only: a
    # request is not sent for approval under rules that set no limits.
    approval: ApprovalRules | None = None
    # Whom to ask. Absent before 1.2.0: no RFQ is drafted under such rules.
    rfq: RfqRules | None = None
    # The Bravo import file's shape (DW02 function 4). Absent before 1.3.0:
    # no order is drafted under such rules.
    bravo_po: BravoPoLayout | None = None
    # How long rows are kept. Absent before 1.6.0: nothing is deleted for age.
    retention: RetentionRules | None = None

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
