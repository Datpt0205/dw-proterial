"""`sales_pricing`: the price inputs Sales weighs that are policy, not master data.

`configs/policies/sales_pricing@<version>.yaml`, versioned like every rule
DW1 applies. It holds the copper adder per LME band, the floor margin and the
freight table. Nothing here sets a price: the copper component and the floor
are evidence and a finding (`price_below_policy_floor`, ticket 03); the price
is Sales' decision.

No approval matrix: which price or discount needs which approver is owed by
the customer (requirements doc §4 item 5). Until it arrives, any holder of
`sales.quote.approve` other than the pricer approves, and ticket 12 adds the
matrix here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.catalog import LmeBand, LmeMonth

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

Incoterm = Literal["EXW", "FCA", "FOB", "CIF", "DAP", "DDP"]


class CopperAdder(BaseModel):
    """What is added to LME copper while LME is inside ``band``, in USD per tonne."""

    model_config = _FROZEN

    band: LmeBand
    adder_usd_per_tonne: Decimal = Field(ge=0)


class FreightRate(BaseModel):
    """Freight for one incoterm to one destination, per kilometre of cable."""

    model_config = _FROZEN

    incoterm: Incoterm
    # A zone name, not an address: ``domestic_north``, ``japan``.
    destination: str = Field(pattern=r"^[a-z][a-z0-9_]{1,31}$")
    usd_per_km: Decimal = Field(ge=0)


class SalesPricing(BaseModel):
    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: Literal["sales_pricing"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    # Contiguous and in order, so an LME price inside the table has exactly one.
    copper_adders: tuple[CopperAdder, ...] = Field(min_length=1)
    # The lowest price is the copper component times (1 + this).
    floor_margin: Decimal = Field(ge=0, lt=1)
    freight: tuple[FreightRate, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _one_answer_per_question(self) -> Self:
        for lower, upper in zip(self.copper_adders, self.copper_adders[1:], strict=False):
            if lower.band.high_usd_per_tonne != upper.band.low_usd_per_tonne:
                raise ValueError("copper_adders are not contiguous and in order")
        lanes = [(rate.incoterm, rate.destination) for rate in self.freight]
        if len(lanes) != len(set(lanes)):
            raise ValueError("freight repeats an incoterm and destination")
        return self

    @property
    def version(self) -> str:
        """What a quotation finding is stamped with: ``sales_pricing@1.0.0``."""
        return f"{self.policy_id}@{self.policy_version}"

    def copper_adder(self, lme: LmeMonth) -> CopperAdder | None:
        """The adder for the month's LME, or None outside the table.

        None is not zero: a copper price the policy does not cover is one
        nobody has priced, and the copper component is then unknown.
        """
        return next((a for a in self.copper_adders if a.band.contains(lme.usd_per_tonne)), None)

    def freight_rate(self, incoterm: Incoterm, destination: str) -> FreightRate | None:
        """The rate for the lane, or None when the policy has none for it."""
        return next(
            (r for r in self.freight if (r.incoterm, r.destination) == (incoterm, destination)),
            None,
        )
