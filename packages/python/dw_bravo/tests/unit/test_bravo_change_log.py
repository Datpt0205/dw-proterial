# ruff: noqa: E501 - the log values below are kept as Bravo's trigger writes them
"""Bravo's own change log read as saves (ticket 69).

Every save of a document is logged by Bravo's trigger (`DML_<table>_ChangeLog`)
into `<db>_Log.dbo.<table>$0`: the command and its word, I/U/D, the user, the
time, the session, and `__$Value`: for an insert the new row, for a delete
the old row, for an update the updated columns' new values then their old
values (`FOR XML AUTO`, elements `new` and `old`). The rows below have that
shape and no Bravo data.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from dw_bravo.change_log import LogRow, group_saves, parse_value

pytestmark = pytest.mark.unit

AT = datetime(2026, 9, 18, 8, 0)


def _row(
    kind: str,
    value: str,
    *,
    session: str = "S1",
    doc: str = "D1",
    word: str = "Edit",
    line: int = 11,
) -> LogRow:
    return LogRow(
        table="B30BizDocDetailSO$0",
        command="EDIT_BizDocSO",
        word=word,
        kind=kind,  # type: ignore[arg-type]
        user=2413,
        at=AT,
        session=session,
        doc_id=doc,
        row_id=line,
        value=value,
    )


def test_an_update_gives_the_new_and_the_old_values_of_the_columns_it_changed() -> None:
    new, old = parse_value(
        '<new EstimatedTimeDelivery="2026-10-01T00:00:00" Remark="a &amp; b"/>'
        '<old EstimatedTimeDelivery="2026-09-20T00:00:00" Remark="a"/>'
    )
    assert new == {"EstimatedTimeDelivery": "2026-10-01T00:00:00", "Remark": "a & b"}
    assert old == {"EstimatedTimeDelivery": "2026-09-20T00:00:00", "Remark": "a"}


def test_an_insert_holds_the_new_row_and_a_delete_the_old_one() -> None:
    assert parse_value('<new Quantity9="610" Unit="m"/>') == ({"Quantity9": "610", "Unit": "m"}, {})
    assert parse_value('<old Quantity9="610"/>') == ({}, {"Quantity9": "610"})
    assert parse_value("<new /><old />") == ({}, {})
    assert parse_value("") == ({}, {})


def test_a_value_that_is_not_the_triggers_xml_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_value("<!DOCTYPE x><new/>")
    with pytest.raises(ValueError):
        parse_value('<other A="1"/>')


@pytest.mark.parametrize(
    ("rows", "kind"),
    [
        (
            [
                (
                    "U",
                    '<new EstimatedTimeDelivery="2026-10-01T00:00:00" CDDate="2026-09-28T00:00:00"/>'
                    '<old EstimatedTimeDelivery="2026-09-20T00:00:00" CDDate="2026-09-17T00:00:00"/>',
                )
            ],
            "date",
        ),
        (
            [("U", '<new Quantity9="500" Amount9="20"/><old Quantity9="610" Amount9="25"/>')],
            "quantity",
        ),
        (
            [
                (
                    "U",
                    '<new OriginalUnitCost="0.04" OriginalAmount9="24.4"/><old OriginalUnitCost="0.05" OriginalAmount9="30.5"/>',
                )
            ],
            "price",
        ),
        ([("U", '<new IsCancel="1"/><old IsCancel="0"/>')], "cancel"),
        (
            [
                ("I", '<new Quantity9="100"/>'),
                ("U", '<new Quantity9="510"/><old Quantity9="610"/>'),
            ],
            "split",
        ),
        ([("D", '<old Quantity9="100"/>')], "delete"),
        ([("U", "<new /><old />")], "touch"),
        ([("U", '<new CustomerPRS="X"/><old CustomerPRS="Y"/>')], "other"),
    ],
)
def test_a_save_is_classed_by_what_it_changed(rows: list[tuple[str, str]], kind: str) -> None:
    (save,) = group_saves([_row(k, v, line=11 + i) for i, (k, v) in enumerate(rows)])
    assert save.kind == kind


def test_a_create_is_classed_by_its_word_and_its_lines_kept() -> None:
    rows = [_row("I", '<new Quantity9="1"/>', word="Import", line=i) for i in (1, 2)]
    (save,) = group_saves(rows)
    assert (save.kind, save.word, len(save.lines)) == ("create", "Import", 2)


def test_saves_are_one_per_session_and_document_in_time_order() -> None:
    rows = [
        _row("U", '<new Quantity9="5"/><old Quantity9="6"/>', session="S2", doc="D1"),
        _row(
            "U",
            '<new CDDate="2026-09-28T00:00:00"/><old CDDate="2026-09-27T00:00:00"/>',
            session="S1",
            doc="D1",
        ),
        _row("U", '<new Quantity9="5"/><old Quantity9="6"/>', session="S1", doc="D2"),
    ]
    rows[0] = LogRow(**{**rows[0].__dict__, "at": datetime(2026, 9, 18, 9, 0)})
    saves = group_saves(rows)
    assert [(s.session, s.doc_id) for s in saves] == [("S1", "D1"), ("S1", "D2"), ("S2", "D1")]
    assert [s.kind for s in saves] == ["date", "quantity", "quantity"]


def test_the_audit_columns_never_class_a_save() -> None:
    (save,) = group_saves(
        [_row("U", '<new ModifiedBy="2" ModifiedAt="x"/><old ModifiedBy="1" ModifiedAt="y"/>')]
    )
    assert save.kind == "touch"
