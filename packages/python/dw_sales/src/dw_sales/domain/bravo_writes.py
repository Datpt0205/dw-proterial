"""`sales_bravo_writes`: which Bravo writes DW1 may perform, per tenant.

ADR 0027 decision 7 and ticket 63 (g): every write kind is off until it has
reproduced a PIC's own save column for column on Bravo UAT, and switching one
on is an act of a person with the right. That act is a tenant version of
this policy, proposed and approved by two people like every Sales rule
(`dw_sales.application.rules`), audited where it is decided. The platform's
file (`configs/policies/sales_bravo_writes@<v>.yaml`) switches every kind
off, and so does a kind the document does not name.

Read where the write happens: the Bravo gateway resolves the tenant's
approved version before each write and refuses a kind not switched on in it
(`dw_bravo_gateway.adapters.postgres.SqlSwitches`), whatever the approval
said. The kinds are the gateway contract's (`dw_bravo.contract.WRITE_KINDS`,
the `so.` ones); this module may not import it (contexts reach Bravo through
their adapters), so `test_bravo_writes.py` holds the two lists equal.

Since 1.1.0 it also names the Bravo DW1 reads and writes (ticket 85):
`target`, UAT unless a version names production with the UAT run that
proved the gateway end to end (`target_uat_proof`). The gateway reads it
before each read and write; a proposal is stamped with the target it was
read from, and a write whose stamp is not the target now is refused.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

BravoWriteKind = Literal[
    "so.line.set_confirmed_date@1",
    "so.line.set_quantity@1",
    "so.line.cancel@1",
    "so.line.split@1",
    "so.create@1",
]
UAT_PROOF_LIMIT: Final = 200
# The gateway contract's `dw_bravo.contract.BravoTarget`, held equal by test.
BravoTarget = Literal["uat", "production"]


class BravoWriteSwitch(BaseModel):
    """One kind: on or off, and the UAT run that proved it when on.

    ``uat_proof`` names where the proof is kept (the UAT trace and the
    replay that matched a PIC's own save), so whoever reads the version
    later can find it; a kind cannot be on without one.
    """

    model_config = _FROZEN

    enabled: bool = False
    uat_proof: str | None = Field(default=None, min_length=1, max_length=UAT_PROOF_LIMIT)

    @model_validator(mode="after")
    def _on_only_with_a_proof(self) -> Self:
        if self.enabled and not (self.uat_proof or "").strip():
            raise ValueError("a write kind is switched on only with the UAT run that proved it")
        return self


class BravoWrites(BaseModel):
    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: Literal["sales_bravo_writes"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    kinds: Mapping[BravoWriteKind, BravoWriteSwitch]
    target: BravoTarget = "uat"
    target_uat_proof: str | None = Field(default=None, min_length=1, max_length=UAT_PROOF_LIMIT)

    @model_validator(mode="after")
    def _production_only_with_a_proof(self) -> Self:
        if self.target == "production" and not (self.target_uat_proof or "").strip():
            raise ValueError(
                "Bravo production is named only with the UAT run that proved the gateway"
            )
        return self

    def enabled(self, kind: str) -> bool:
        """Off for a kind the document does not name (fail closed)."""
        switch = self.kinds.get(kind)  # type: ignore[call-overload]
        return switch is not None and switch.enabled

    @property
    def version(self) -> str:
        return f"{self.policy_id}@{self.policy_version}"

    @property
    def ref(self) -> str:
        """``key@x.y.z``, as a tenant's version of it is named (ticket 36)."""
        return self.version
