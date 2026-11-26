"""Ticket 75: a write's command right, read from Bravo's own function
(`ufn_B00Permission_Getdata`), decided for the keys script 10 measures."""

from __future__ import annotations

import pytest

from dw_bravo_gateway.adapters.sqlserver import COMMAND_KEYS, CommandKeys, decide_command_right

pytestmark = pytest.mark.unit

KEYS = CommandKeys(
    explorer="BizDocSO",
    editor="EDIT_BizDocSO",
    sub_commands={"update": ("Edit", "Save"), "insert": ("New", "Save")},
)


def row(kind: str, command: str, sub: str = "", **flags: int) -> dict[str, object]:
    return {"Kind": kind, "CommandKey": command, "SubCommandKey": sub, **flags}


def test_no_row_is_no_denial() -> None:
    assert decide_command_right([], KEYS, "update") == "allowed"


@pytest.mark.parametrize(
    ("rows", "operation"),
    [
        ([row("1", "BizDocSO", NoOpen=1)], "update"),
        ([row("2", "BizDocSO", "Edit", NoOpen=1)], "update"),
        ([row("2", "BizDocSO", "Save", NoDisplay=1)], "update"),
        ([row("2", "BizDocSO", "New", NoOpen=1)], "insert"),
        ([row("3", "EDIT_BizDocSO", NoEdit=1)], "update"),
        ([row("3", "EDIT_BizDocSO", NoAddNew=1)], "insert"),
    ],
)
def test_a_flag_on_the_screens_commands_denies(
    rows: list[dict[str, object]], operation: str
) -> None:
    assert decide_command_right(rows, KEYS, operation) == "denied"  # type: ignore[arg-type]


def test_another_commands_or_operations_flag_does_not_deny() -> None:
    rows = [
        row("2", "BizDocSO", "Delete", NoOpen=1),
        row("3", "EDIT_BizDocSO", NoAddNew=1),
        row("1", "BizDocPO", NoOpen=1),
    ]
    assert decide_command_right(rows, KEYS, "update") == "allowed"


def test_an_operation_with_no_measured_sub_command_is_unknown() -> None:
    keys = CommandKeys(explorer="BizDocSO", editor="EDIT_BizDocSO", sub_commands={})
    assert decide_command_right([], keys, "update") == "unknown"


def test_no_screen_is_measured_yet_so_every_live_write_is_refused() -> None:
    # Script 10 fills this; until then `command_right` answers "unknown".
    assert dict(COMMAND_KEYS) == {}
