"""The surveyed process steps, and where DW1 meets each one.

`WIV_STEPS` is the one owner of the mapping the spec's "Process map" table
describes: for each step of WIV-03-012 (order entry, ``O1``-``O11``) and
WIV-03-023 (quotation, ``Q1``-``Q12``), the case states and artifacts it
produces and whether this slice covers it. The overview (ticket 05) and its
page (08) read it; the per-step export of time spent is keyed by these ids.

State names are CONTEXT.md's. An order step's states are checked against
`OrderStatus` by a test; a quote step's belong to `QuoteCase`, whose
transitions ticket 03 owns.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Names that hold a digit and are no figure: the Digital Workers' own. A
# model's prose may write them with no source holding them
# (`dw_agent_runtime.model.figure_check.unsupported`'s ``names``).
DW_NAMES: Final = frozenset({"DW1", "DW2"})


class Procedure(StrEnum):
    ORDER_ENTRY = "WIV-03-012"
    QUOTATION = "WIV-03-023"


class Coverage(StrEnum):
    """How far this slice takes the step."""

    YES = "yes"
    # DW1 proposes; a person decides outside the portal (O4's date).
    SUGGESTION = "suggestion"
    # Built on mock data until the company grants access (Q4, Q11, Q12).
    MOCK = "mock"
    # Another worker's (DW2) or outside this slice.
    OUT = "out"


class StepId(StrEnum):
    """The surveyed steps' ids as a closed set: what a value kept per step (the
    KPI's manual baseline) is keyed by, so a version written before a step was
    surveyed reads that step as the platform has it (`rules.read_over`). Held
    to `WIV_STEPS`, which owns the steps themselves, by a test."""

    O1 = "O1"
    O2 = "O2"
    O3 = "O3"
    O4 = "O4"
    O5 = "O5"
    O6 = "O6"
    O7 = "O7"
    O8 = "O8"
    O9 = "O9"
    O10 = "O10"
    O11 = "O11"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    Q5 = "Q5"
    Q6 = "Q6"
    Q7 = "Q7"
    Q8 = "Q8"
    Q9 = "Q9"
    Q10 = "Q10"
    Q11 = "Q11"
    Q12 = "Q12"


class ProcessStep(BaseModel):
    model_config = _FROZEN

    step_id: str = Field(pattern=r"^[OQ]\d{1,2}$")
    procedure: Procedure
    number: int = Field(ge=1)
    coverage: Coverage
    states: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()


_PREFIX: Final = {Procedure.ORDER_ENTRY: "O", Procedure.QUOTATION: "Q"}


def _step(
    procedure: Procedure,
    number: int,
    coverage: Coverage,
    states: tuple[str, ...],
    artifacts: tuple[str, ...] = (),
) -> ProcessStep:
    return ProcessStep(
        step_id=f"{_PREFIX[procedure]}{number}",
        procedure=procedure,
        number=number,
        coverage=coverage,
        states=states,
        artifacts=artifacts,
    )


def _o(number: int, coverage: Coverage, *rest: tuple[str, ...]) -> ProcessStep:
    return _step(Procedure.ORDER_ENTRY, number, coverage, *rest)


def _q(number: int, coverage: Coverage, *rest: tuple[str, ...]) -> ProcessStep:
    return _step(Procedure.QUOTATION, number, coverage, *rest)


_YES, _SUGGESTION, _MOCK, _OUT = Coverage.YES, Coverage.SUGGESTION, Coverage.MOCK, Coverage.OUT

WIV_STEPS: Final[tuple[ProcessStep, ...]] = (
    _o(1, _YES, ("received",), ("message_disposition",)),
    _o(2, _YES, ("checked",), ("convert_list_proposal",)),
    _o(3, _YES, ("uploaded_to_bravo",), ("bravo_upload_file",)),
    _o(4, _SUGGESTION, (), ("suggested_delivery_date", "confirmed_delivery_date")),
    _o(5, _OUT, ()),
    _o(6, _YES, ("in_review",), ("findings",)),
    _o(7, _YES, ("prepared", "uploaded_to_bravo"), ("coverage_statement",)),
    _o(8, _YES, ("correction_requested",), ("correction_draft",)),
    _o(9, _YES, ("cross_checked",), ("cross_check_sheet",)),
    _o(10, _YES, ("confirmation_sent", "confirmed"), ("confirmation_draft",)),
    _o(11, _OUT, ()),
    _q(1, _YES, ("received",)),
    _q(2, _YES, ("ycbg_drafted", "ycbg_recorded"), ("ycbg_draft",)),
    _q(3, _YES, ("sent_to_design",), ("design_request_draft",)),
    _q(4, _MOCK, ("design_replied",), ("ycbg_waiting_list",)),
    _q(5, _YES, ("declined",), ("decline_draft",)),
    _q(6, _YES, ("spec_discussion",), ("spec_discussion_draft",)),
    _q(7, _YES, ("priced",), ("price_evidence",)),
    _q(8, _YES, (), ("quotation_document",)),
    _q(9, _YES, ("pending_approval", "approved", "returned"), ("approval_pack",)),
    _q(10, _YES, ("sent",), ("send_draft",)),
    _q(11, _MOCK, ("master_list_recorded",), ("master_list_row",)),
    _q(12, _MOCK, (), ("screening_report",)),
)


def step(step_id: str) -> ProcessStep:
    """The step with this id; a KeyError for one the survey does not have."""
    for candidate in WIV_STEPS:
        if candidate.step_id == step_id:
            return candidate
    raise KeyError(step_id)


# ------------------------------------------- the BA's merged flows (11-13) --


class BaStep(BaseModel):
    """One step of the BA's two merged flows of 2026-11-13, "QUY TRÌNH ĐƠN
    HÀNG (PO)" (0-KH … 6.3) and "QUY TRÌNH BÁO GIÁ (RFQ)" (1 … 2.1.6): the
    code the BA wrote on it, and what it does in a few words. The BA's
    decision gates (◇) carry no code and are not listed."""

    model_config = _FROZEN

    code: str = Field(pattern=r"^[0-9][0-9A-Z.\-]{0,9}$")
    label: str = Field(min_length=1, max_length=80)


def _ba(code: str, label: str) -> BaStep:
    return BaStep(code=code, label=label)


# Where DW1 is while each of the BA's steps runs, the one owner of the
# code -> words mapping (ticket 35): per procedure, a place is a case status
# (`OrderStatus`, `QuoteStatus`) or a step of a flow beside the statuses,
# ``<flow>.<step>`` (`process_settings.SUBFLOWS`). The process page draws
# each code on its place; `test_process_settings.py` holds every place to the
# served view. A step DW1 does not do yet (5.1, 6.1B, 6-HUY, 2.2.x, …) has no
# place and is left out; so is a status the BA's flow has no step for.
BA_STEPS: Final[Mapping[Procedure, Mapping[str, tuple[BaStep, ...]]]] = MappingProxyType(
    {
        Procedure.ORDER_ENTRY: MappingProxyType(
            {
                "thread.before_po": (_ba("0-KH", "Khách trao đổi trong luồng thư, rồi gửi PO"),),
                "received": (
                    _ba("0-SP", "Sales tải PO từ cổng của khách lên DW1"),
                    _ba("1", "Gom PO, phân loại, giao đúng PIC"),
                ),
                "checked": (
                    _ba("2", "Đọc PO, trích xuất từng dòng"),
                    _ba("2.1A", "Kiểm giá theo LME"),
                    _ba("2.2A", "Đổi mã khách sang mã PRV"),
                    _ba("3.1", "So PO với báo giá"),
                ),
                "in_review": (_ba("3", "PIC tự kiểm, quyết định từng sai lệch"),),
                "correction_requested": (_ba("4", "Đề nghị khách sửa PO, nhắc khách"),),
                "prepared": (_ba("5", "Xác nhận PO hợp lệ, lịch giao theo PC"),),
                "uploaded_to_bravo": (_ba("5-BR", "Nhập đơn vào Bravo, ghi số SO"),),
                "cross_checked": (_ba("5-KC", "Kiểm chéo đơn hàng"),),
                "confirmation_sent": (
                    _ba("5.2", "Gửi kèm Excel đã xử lý"),
                    _ba("5.3", "Gửi thư xác nhận cho khách"),
                    _ba("6.3", "Gửi lại khách PO và lịch giao mới"),
                ),
                "change_review": (_ba("6.2B", "Làm lại PO, kiểm lại bước 2 đến 3"),),
                "closed": (_ba("1-X", "Đóng hồ sơ PO không hợp lệ"),),
                "pc_request.waiting_pc": (_ba("2.4B", "Hỏi PC lịch giao và cách tách dòng"),),
                "change_request.confirm_lines": (
                    _ba("6.1A", "Khách xin điều chỉnh qua thư"),
                    _ba("6-DW1", "Nhận ra yêu cầu, gắn với PO gốc, so thay đổi"),
                ),
                "update.ask_pc": (_ba("6-DW2", "Soạn yêu cầu gửi PC"),),
                "update.waiting_pc": (_ba("6-PC", "PC xem và trả lời"),),
                "update.answer_customer": (
                    _ba("6-DW3", "PC đề xuất khác: soạn thư phương án cho khách"),
                    _ba("6-DW4", "PC làm được: soạn thư xác nhận điều chỉnh"),
                ),
                "update.bravo_update": (_ba("6.2-SP", "Duyệt cập nhật đơn trên Bravo"),),
            }
        ),
        Procedure.QUOTATION: MappingProxyType(
            {
                "received": (_ba("1-DW", "Gom RFQ, đọc, phân loại, giao PIC"),),
                "ycbg_recorded": (_ba("1.1.1", "Nhập RFQ lên Bravo"),),
                "sent_to_design": (_ba("1.1.2", "Gửi RFQ cho Design, nhắc khi chậm"),),
                "spec_discussion": (_ba("1.1.3", "Hỏi lại khách về spec"),),
                "design_replied": (_ba("1.1.4", "Ghi BP code và Base price"),),
                "declined": (_ba("1.1.5", "Sales quyết định đóng"),),
                "priced": (_ba("2.1.1", "Tính giá theo LME và policy, chốt giá"),),
                "pending_approval": (_ba("2.1.4", "In báo giá, trình ký"),),
                "approved": (_ba("2.1.5", "Bản đã ký"),),
                "sent": (_ba("2.1.6", "Gửi thư báo giá"),),
                "master_list_recorded": (_ba("2.1.3", "Ghi báo giá vào master list"),),
            }
        ),
    }
)
