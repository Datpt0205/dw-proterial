"""Ticket 65's reaction table, a test per row (acceptance 1), and the
mutation-facing defaults: nothing reads as unchanged on an error."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from dw_bravo.watch import (
    MAX_AGE,
    Component,
    Fingerprint,
    diff,
    early_warnings,
    react,
    status,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 11, 21, 3, tzinfo=UTC)
SO = "EDIT_BizDocSO"
ALL = {
    "so.line.set_confirmed_date@1",
    "so.line.set_quantity@1",
    "so.line.cancel@1",
    "so.line.split@1",
    "so.create@1",
}
BASE = Fingerprint(
    "production",
    NOW,
    (
        Component("layout", SO, "l1", modified_by="admin1"),
        Component("command", SO, "c1"),
        Component("template", SO, "t1"),
        Component("columns", "B30BizDocDetailSO", "col1"),
        Component("columns", "B30BizDocDetailRQ", "rq1"),
        Component("trigger", "DML_B30BizDocDetailSO_ChangeLog", "tr1", table="B30BizDocDetailSO"),
        Component("trigger", "DML_B30BizDocRQ_X", "tr2", table="B30BizDocRQ"),
        Component("routine", "ufn_Prevent_Edit", "r1"),
        Component("routine", "usp_B30BizDocDetailSO_GetSQData_HCV", "r2", screens=frozenset({SO})),
        Component("routine", "usp_OnlyRq", "r3", screens=frozenset({"EDIT_BizDocRQ"})),
        Component("context_parser", "ufn_sys_GetUserIdFromContext_Info", "p1"),
        Component("client_version", "B8.4.3.0.1", "v1"),
    ),
)


def changed(name: str, **over: object) -> Fingerprint:
    components = tuple(
        replace(c, **{"digest": c.digest + "'", **over}) if c.name == name else c  # type: ignore[arg-type]
        for c in BASE.components
    )
    return replace(BASE, components=components)


def test_nothing_changed_is_no_change() -> None:
    assert diff(BASE, BASE) == []
    reaction = react([], {})
    assert reaction.paused == {} and reaction.notices == []


def test_a_layout_edit_that_parses_and_replays_goes_on_with_a_notice() -> None:
    # `changed(SO)` touches every component named after the screen (layout,
    # command, template); the layout alone is this row.
    layout_only = [c for c in diff(BASE, changed(SO, modified_by="admin2")) if c.kind == "layout"]
    reaction = react(layout_only, {SO: "agrees"})

    assert reaction.paused == {}
    [notice] = reaction.notices
    assert notice.level == "info" and "follows Bravo's new layout" in notice.text
    assert set(notice.kinds) == ALL and "admin2" in notice.text


def test_an_explained_replay_also_goes_on() -> None:
    layout_only = [c for c in diff(BASE, changed(SO)) if c.kind == "layout"]

    assert react(layout_only, {SO: "explained"}).paused == {}


@pytest.mark.parametrize("replay", ["differs", "not_run"])
def test_a_layout_whose_replay_has_not_agreed_pauses_that_screen(replay: str) -> None:
    layout_only = [c for c in diff(BASE, changed(SO)) if c.kind == "layout"]

    reaction = react(layout_only, {SO: replay} if replay != "not_run" else {})  # type: ignore[dict-item]

    assert set(reaction.paused) == ALL


def test_a_layout_with_a_rule_the_runner_cannot_run_pauses_only_that_screen() -> None:
    other = Component("layout", "EDIT_BizDocRQ", "q1")
    base = replace(BASE, components=(*BASE.components, other))
    current = replace(
        base,
        components=tuple(
            replace(c, digest="new", unknown=("Eval_NewThing",))
            if c.key == ("layout", SO.lower())
            else c
            for c in base.components
        ),
    )

    reaction = react(diff(base, current), {SO: "agrees"})

    assert set(reaction.paused) == ALL  # every kind is the SO screen's today
    assert "Eval_NewThing" in reaction.notices[0].text
    assert all("EDIT_BizDocRQ" not in n.text for n in reaction.notices)


def test_a_column_change_pauses_only_the_kinds_that_use_the_table() -> None:
    reaction = react(diff(BASE, changed("B30BizDocDetailSO")), {})
    assert set(reaction.paused) == ALL

    untouched = react(diff(BASE, changed("B30BizDocDetailRQ")), {})
    assert untouched.paused == {}


def test_a_trigger_change_pauses_only_the_kinds_that_write_its_table() -> None:
    assert set(react(diff(BASE, changed("DML_B30BizDocDetailSO_ChangeLog")), {}).paused) == ALL
    assert react(diff(BASE, changed("DML_B30BizDocRQ_X")), {}).paused == {}


def test_a_trigger_disabled_is_a_change() -> None:
    # The gateway puts the enabled flag in the digest; a flip is a new digest.
    assert diff(BASE, changed("DML_B30BizDocDetailSO_ChangeLog")) != []


def test_a_routine_pauses_the_screens_that_call_it_or_every_write() -> None:
    assert set(react(diff(BASE, changed("usp_B30BizDocDetailSO_GetSQData_HCV")), {}).paused) == ALL
    assert react(diff(BASE, changed("usp_OnlyRq")), {}).paused == {}
    assert set(react(diff(BASE, changed("ufn_Prevent_Edit")), {}).paused) == ALL


def test_the_context_parser_changed_pauses_every_write() -> None:
    reaction = react(diff(BASE, changed("ufn_sys_GetUserIdFromContext_Info")), {})

    assert set(reaction.paused) == ALL


def test_an_import_template_pauses_only_creation_on_that_screen() -> None:
    template = [c for c in diff(BASE, changed(SO)) if c.kind == "template"]

    paused = react(template, {}).paused

    # A split is a save of a stored SO that adds lines in its grid (ticket
    # 73): it uses no import template, so only creation pauses.
    assert set(paused) == {"so.create@1"}


def test_a_new_client_version_notices_and_pauses_until_the_replay() -> None:
    current = replace(
        BASE,
        components=tuple(
            replace(c, name="B8.4.4.0.0", digest="v2") if c.kind == "client_version" else c
            for c in BASE.components
        ),
    )

    reaction = react(diff(BASE, current), {SO: "agrees"})

    assert set(reaction.paused) == ALL
    assert any("B8.4.4.0.0" in n.text for n in reaction.notices)


def test_a_removed_component_is_a_change() -> None:
    gone = replace(
        BASE, components=tuple(c for c in BASE.components if c.name != "ufn_Prevent_Edit")
    )

    assert set(react(diff(BASE, gone), {}).paused) == ALL


def test_uat_ahead_of_production_is_an_early_warning_and_pauses_nothing() -> None:
    uat = replace(changed("B30BizDocDetailSO"), environment="uat")

    warnings = early_warnings(uat, BASE)

    assert [w.level for w in warnings] == ["early_warning"]
    assert "UAT" in warnings[0].text and "B30BizDocDetailSO" in warnings[0].text


def test_bravo_unreachable_reads_could_not_check_never_unchanged() -> None:
    recent = status(NOW - timedelta(minutes=10), NOW)
    assert recent.paused == {}
    assert recent.notices[0].level == "could_not_check"

    stale = status(NOW - MAX_AGE - timedelta(minutes=1), NOW)
    assert set(stale.paused) == ALL

    never = status(None, NOW)
    assert set(never.paused) == ALL
