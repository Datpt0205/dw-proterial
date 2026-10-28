"""Export control (WIV-03-032), the six steps Proterial's survey lists.

1. Screen the product against PRV's own list: each item's export
   classification, from master data (`Item.export_classification`).
2. Check the customer and their country on the group's denial list.
3. Answer the red-flag questions.
4. Ask the customer for a NOC (the NOEC mail) and receive it.
5. Have the export screening form (ESF) approved, level by level.
6. Renew the ESF each fiscal year for every customer still buying.

DW1 decides none of it. A person records each result with its evidence; DW1
keeps the latest result per customer and step (`ScreeningRecord`), the audit
trail keeps every one before it, and the customer's compliance the order
checks read is the master data's as these results move it
(`effective_compliance`). The questions, the ESF's approval levels and the
other choices are the tenant's policy (`SalesExportControl`), shipped as a
sample until Proterial sends WIV-03-032 (asked in the customer questionnaire).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from typing import Annotated, Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from dw_sales.domain.catalog import Compliance, CustomerCode, Language
from dw_sales.domain.messages import Sha256Hex

_FROZEN = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)


class ScreeningStep(StrEnum):
    """The steps a person records a result of. The product screen (step 1)
    is read from master data, and the yearly renewal (step 6) is an ESF
    recorded for the new year: neither is a step of its own here."""

    DENIAL_LIST = "denial_list"
    RED_FLAG = "red_flag"
    NOC = "noc"
    ESF = "esf"


# What each step's result may be. One owner: the migration's CHECK repeats it
# and `test_export_control_store` holds the two equal.
OUTCOMES: Final[dict[ScreeningStep, frozenset[str]]] = {
    ScreeningStep.DENIAL_LIST: frozenset({"clear", "match"}),
    ScreeningStep.RED_FLAG: frozenset({"clear", "escalated"}),
    ScreeningStep.NOC: frozenset({"requested", "received"}),
    ScreeningStep.ESF: frozenset({"approved"}),
}
# A result that is a document the customer or the approvers signed is kept
# with its file; a result without one is a claim nobody could check.
EVIDENCE_REQUIRED: Final = frozenset(
    {(ScreeningStep.NOC, "received"), (ScreeningStep.ESF, "approved")}
)
NOTE_MAX: Final = 500

QuestionId = Annotated[str, Field(pattern=r"^rf\d{2}$")]
EvidenceType = Literal["application/pdf", "image/jpeg", "image/png"]


class Evidence(BaseModel):
    """A file a result rests on: the NOC, the signed ESF, a screenshot."""

    model_config = _FROZEN

    file_id: uuid.UUID
    sha256: Sha256Hex
    content_type: EvidenceType
    size_bytes: int = Field(gt=0)


class ScreeningRecord(BaseModel):
    """The latest result of one step for one customer, and who recorded it."""

    model_config = _FROZEN

    customer_code: CustomerCode
    step: ScreeningStep
    outcome: str
    checked_on: date
    # The fiscal year an ESF covers; None for every other step.
    fiscal_year: int | None = Field(default=None, ge=2000, le=2100)
    # The red-flag answers by question id: True is "yes".
    answers: dict[QuestionId, bool] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=NOTE_MAX)
    evidence: Evidence | None = None
    recorded_by: uuid.UUID
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.outcome not in OUTCOMES[self.step]:
            raise ValueError(f"{self.step} has no outcome {self.outcome!r}")
        if (self.fiscal_year is not None) != (self.step is ScreeningStep.ESF):
            raise ValueError("a fiscal year is an ESF's, and an ESF has one")
        if self.step is ScreeningStep.RED_FLAG:
            if not self.answers:
                raise ValueError("a red-flag result answers its questions")
            if (self.outcome == "escalated") != any(self.answers.values()):
                raise ValueError("a red flag is escalated exactly when a question is answered yes")
        elif self.answers:
            raise ValueError("only the red-flag step has answers")
        if (self.step, self.outcome) in EVIDENCE_REQUIRED and self.evidence is None:
            raise ValueError(f"{self.step} {self.outcome} is recorded with its document")
        return self


def effective_compliance(base: Compliance, records: Iterable[ScreeningRecord]) -> Compliance:
    """The customer's compliance as master data states it, moved by what was
    recorded since: a NOC received confirms it, an approved ESF covers its
    year (the later year of the two), a clear denial-list check dates the
    screening (the later date), a match or an escalated red flag holds every
    order of the customer for the export-control PIC. Never loosened by a
    record: a match stays until a later check of that step is clear."""
    latest = {record.step: record for record in records}
    noc = latest.get(ScreeningStep.NOC)
    esf = latest.get(ScreeningStep.ESF)
    denial = latest.get(ScreeningStep.DENIAL_LIST)
    red_flag = latest.get(ScreeningStep.RED_FLAG)
    years = [y for y in (base.esf_fiscal_year, esf.fiscal_year if esf else None) if y is not None]
    checked = [d for d in (base.denial_list_checked_on,) if d is not None]
    if denial is not None and denial.outcome == "clear":
        checked.append(denial.checked_on)
    return Compliance(
        noc_confirmed=base.noc_confirmed or (noc is not None and noc.outcome == "received"),
        esf_fiscal_year=max(years) if years else None,
        denial_list_checked_on=max(checked) if checked else None,
        denial_list_match=base.denial_list_match
        or (denial is not None and denial.outcome == "match"),
        red_flag_escalated=red_flag is not None and red_flag.outcome == "escalated",
    )


# ------------------------------------------------------------- the policy --


class RedFlagQuestion(BaseModel):
    model_config = _FROZEN

    id: QuestionId
    text: str = Field(min_length=5, max_length=300)


class NoecEmail(BaseModel):
    """The NOEC mail asking a customer for their NOC, per language the
    customer master records. ``{customer_name}`` is filled in."""

    model_config = _FROZEN

    subject: dict[Language, Annotated[str, Field(min_length=3, max_length=200)]]
    body: dict[Language, Annotated[str, Field(min_length=10, max_length=4000)]]

    @model_validator(mode="after")
    def _every_language(self) -> Self:
        for name, texts in (("subject", self.subject), ("body", self.body)):
            if set(texts) != {"vi", "en", "ja"}:
                raise ValueError(f"noec_email.{name} is written in vi, en and ja")
        return self


class SalesExportControl(BaseModel):
    """The tenant's export-control choices: the red-flag questions and who
    approves an ESF, in order. A sample until Proterial's own arrive."""

    model_config = _FROZEN

    schema_version: str = Field(pattern=r"^1\.0$")
    policy_id: Literal["sales_export_control"]
    policy_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    sample: bool = Field(
        description=(
            "Bản mẫu: câu hỏi và cấp duyệt chưa phải của Proterial. Tắt khi đã thay bằng bộ thật."
        )
    )
    red_flags: tuple[RedFlagQuestion, ...] = Field(
        min_length=1, max_length=40, description="Bộ câu hỏi Red flag Indicator."
    )
    esf_approvers: tuple[Annotated[str, Field(min_length=2, max_length=80)], ...] = Field(
        min_length=1, max_length=8, description="Các cấp duyệt ESF, theo thứ tự ký."
    )
    noec_email: NoecEmail = Field(description="Thư NOEC đề nghị khách xác nhận NOC.")

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        ids = [q.id for q in self.red_flags]
        if len(set(ids)) != len(ids):
            raise ValueError("red_flags repeat an id")
        return self

    @property
    def version(self) -> str:
        return f"{self.policy_id}@{self.policy_version}"

    @property
    def ref(self) -> str:
        return self.version
