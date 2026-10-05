"""An order through the API, as the personas walk it (spec "Done when"), and
each refusal on the way: separation of duties at the route, the source gate,
stale versions, the self-check, revisions, mappings and export control.

Every test starts from an empty `sales` schema in the demo tenant; the
mocks are bound to it.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, DIEU, GIANG, KHOA, Api, user_id
from sales_flow import dates, decide, open_sources, order, order_of, prepared, process, uploaded
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


async def _audit(migrator: AsyncEngine, case_id: str) -> list[dict[str, object]]:
    async with migrator.connect() as conn:
        rows = await conn.execute(
            sa.text(
                "SELECT action, actor_id, details FROM platform.audit_events"
                " WHERE resource_id = :id ORDER BY occurred_at, id"
            ),
            {"id": case_id},
        )
        return [dict(row._mapping) for row in rows]


async def test_an_and_dieu_walk_m01_from_the_mailbox_to_confirmed(
    api: Api, migrator: AsyncEngine
) -> None:
    an, dieu = api.as_(AN), api.as_(DIEU)
    case = await order_of(an, "M01")
    # DW1 read and checked it, and handed it to An's self-check.
    assert (case["status"], case["assigned_to"]) == ("in_review", str(user_id(AN)))
    assert case["findings"] == [] and case["rules_version"] == "sales_order_rules@1.0.0"
    assert case["release_manifest_ref"].startswith("sha256:")

    up = await uploaded(an, case)
    assert (up["status"], up["prepared_by"], up["bravo_recorded_by"]) == (
        "uploaded_to_bravo",
        str(user_id(AN)),
        str(user_id(AN)),
    )
    await open_sources(dieu, up)
    crossed = await decide(dieu, up, "cross-check", {"decision": "accept"})
    assert crossed["cross_checked_by"] == str(user_id(DIEU))
    confirmed = await decide(an, crossed, "confirm", {"delivery_dates": dates(crossed)})
    assert confirmed["status"] == "confirmed"
    assert {line["confirmed_delivery_date"] for line in confirmed["lines"]} == {"2026-11-27"}

    rows = await _audit(migrator, case["case_id"])
    assert [r["action"] for r in rows] == [
        "sales.order.checked",
        "sales.order.review_started",
        "sales.order.prepared",
        "sales.order.bravo_recorded",
        "sales.order.cross_checked",
        "sales.order.confirmed",
    ]
    # DW1's own steps are the worker's, on An's request; the rest are people's.
    assert rows[0]["details"]["actor_kind"] == "worker"  # type: ignore[index]
    assert rows[0]["actor_id"] == user_id(AN)
    assert rows[4]["actor_id"] == user_id(DIEU)
    # Ids, codes, transitions and versions: nothing else travels.
    allowed = {
        "case_kind",
        "case_version",
        "from_status",
        "to_status",
        "actor_kind",
        "worker_id",
        "worker_version",
        "finding_key",
        "field",
        "reason_code",
    }
    for row in rows:
        assert set(row["details"]) <= allowed  # type: ignore[arg-type]
    # The case's own log says the same: DW1's events name the worker and the
    # person whose request started them.
    async with migrator.connect() as conn:
        events = (
            await conn.execute(
                sa.text(
                    "SELECT action, actor_kind, actor_id, worker_id, initiated_by"
                    " FROM sales.case_events WHERE case_id = :id ORDER BY occurred_at, case_version"
                ),
                {"id": case["case_id"]},
            )
        ).all()
    assert [(e.action, e.actor_kind) for e in events[:2]] == [
        ("order.checked", "worker"),
        ("order.review_started", "worker"),
    ]
    assert {(e.worker_id, e.initiated_by) for e in events[:2]} == {("sales-dw1", user_id(AN))}
    assert events[2].actor_kind == "user" and events[2].actor_id == str(user_id(AN))


async def test_the_preparer_cannot_cross_check_their_own_order(api: Api) -> None:
    an = api.as_(AN)
    up = await uploaded(an, await order_of(an, "M01"))
    await open_sources(an, up)

    refused = await an.post(
        f"/orders/{up['case_id']}/cross-check",
        {"case_version": up["case_version"], "decision": "accept"},
    )

    # The case refuses it itself, naming the rule, before the store's CHECK.
    assert refused.status_code == 409
    assert "tách nhiệm" in refused.json()["message"]
    assert refused.json()["details"]["rule"] == "maker_checker"


async def test_whoever_recorded_the_bravo_entry_cannot_cross_check(api: Api) -> None:
    an, khoa = api.as_(AN), api.as_(KHOA)
    up = await uploaded(an, await order_of(an, "M01"), recorder=khoa)
    await open_sources(khoa, up)

    refused = await khoa.post(
        f"/orders/{up['case_id']}/cross-check",
        {"case_version": up["case_version"], "decision": "accept"},
    )

    assert refused.status_code == 409 and "tách nhiệm" in refused.json()["message"]


async def test_a_round_one_preparer_stays_a_maker_after_a_return(api: Api) -> None:
    an, dieu, giang = api.as_(AN), api.as_(DIEU), api.as_(GIANG)
    up = await uploaded(an, await order_of(an, "M01"))
    await open_sources(dieu, up)
    returned = await decide(dieu, up, "cross-check", {"decision": "return", "reason": "sai SO"})
    again = await uploaded(giang, returned)
    assert str(user_id(AN)) in again["makers"]
    await open_sources(an, again)

    refused = await an.post(
        f"/orders/{again['case_id']}/cross-check",
        {"case_version": again["case_version"], "decision": "accept"},
    )

    assert refused.status_code == 409 and "tách nhiệm" in refused.json()["message"]


async def test_prepare_and_cross_check_need_the_callers_own_served_source(api: Api) -> None:
    an, dieu = api.as_(AN), api.as_(DIEU)
    case = await order_of(an, "M01")
    # Diệu looks at the source now, while the case is still in review.
    await open_sources(dieu, case)

    unopened = await an.post(
        f"/orders/{case['case_id']}/prepare", {"case_version": case["case_version"]}
    )
    assert unopened.status_code == 409
    assert "chưa mở nguồn" in unopened.json()["message"]

    up = await uploaded(an, case)
    # An's record is his, and Diệu's is for a version the case has left.
    refused = await dieu.post(
        f"/orders/{up['case_id']}/cross-check",
        {"case_version": up["case_version"], "decision": "accept"},
    )
    assert refused.status_code == 409 and "chưa mở nguồn" in refused.json()["message"]

    await open_sources(dieu, up)
    accepted = await dieu.post(
        f"/orders/{up['case_id']}/cross-check",
        {"case_version": up["case_version"], "decision": "accept"},
    )
    assert accepted.status_code == 200, accepted.text


async def test_a_decision_on_a_stale_version_is_refused(api: Api) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M01")
    await open_sources(an, case)

    stale = await an.post(
        f"/orders/{case['case_id']}/prepare", {"case_version": case["case_version"] - 1}
    )

    assert stale.status_code == 409
    assert stale.json()["details"]["case_version"] == str(case["case_version"])
    assert (await order(an, case["case_id"]))["status"] == "in_review"


async def test_confirm_before_the_cross_check_is_refused(api: Api) -> None:
    an = api.as_(AN)
    up = await uploaded(an, await order_of(an, "M01"))

    early = await an.post(
        f"/orders/{up['case_id']}/confirm",
        {"case_version": up["case_version"], "delivery_dates": dates(up)},
    )

    assert early.status_code == 409


async def test_prepare_with_an_open_blocking_finding_names_it(api: Api) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M04")
    await open_sources(an, case)

    refused = await an.post(
        f"/orders/{case['case_id']}/prepare", {"case_version": case["case_version"]}
    )

    assert refused.status_code == 409
    assert "price_mismatch:2" in refused.json()["details"]["open_findings"]


async def test_m04_goes_back_to_the_customer_and_m07_supersedes_it_in_the_case(api: Api) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M04")
    for key in ("price_mismatch:2", "code_unmapped:3"):
        case = await decide(
            an, case, f"findings/{key}/disposition", {"disposition": "ask_customer"}
        )
    asked = await decide(an, case, "correction-request")
    assert asked["status"] == "correction_requested"

    joined = await process(an, "M07")
    revised = await order(an, case["case_id"])

    assert (joined["kind"], joined["case_id"]) == ("attached_to_case", case["case_id"])
    assert revised["revision"] == 1 and [s["message_id"] for s in revised["superseded"]] == ["M04"]
    assert revised["status"] == "in_review"
    # A decision taken on the superseded revision is refused: its version is
    # gone, and so is the finding it names.
    on_old = await an.post(
        f"/orders/{case['case_id']}/findings/price_mismatch:2/disposition",
        {"case_version": asked["case_version"], "disposition": "accepted", "reason": "ok"},
    )
    assert on_old.status_code == 409
    missing = await an.post(
        f"/orders/{case['case_id']}/findings/price_mismatch:2/disposition",
        {"case_version": revised["case_version"], "disposition": "accepted", "reason": "ok"},
    )
    assert missing.status_code == 409


async def test_a_mapping_to_a_code_outside_the_candidates_is_refused(api: Api) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M05")
    line = next(line for line in case["lines"] if line["line_no"] == 1)
    assert line["mapping"]["status"] == "ambiguous"

    outside = await an.post(
        f"/orders/{case['case_id']}/lines/1/mapping",
        {"case_version": case["case_version"], "prv_code": "CB-2005"},
    )
    assert outside.status_code == 409

    chosen = await decide(an, case, "lines/1/mapping", {"prv_code": "CB-2001"})
    confirmed = next(line for line in chosen["lines"] if line["line_no"] == 1)
    assert confirmed["mapping"]["status"] == "candidate_confirmed"
    assert confirmed["mapping"]["confirmed_by"] == str(user_id(AN))


async def test_missing_noc_esf_is_acknowledged_by_the_export_control_pic_only(api: Api) -> None:
    an, dieu = api.as_(AN), api.as_(DIEU)
    case = await order_of(an, "M03")
    body = {"case_version": case["case_version"], "disposition": "accepted", "reason": "Đã xem"}

    without = await dieu.post(
        f"/orders/{case['case_id']}/findings/missing_noc_esf:-/disposition", body
    )
    assert without.status_code == 403

    acknowledged = await an.post(
        f"/orders/{case['case_id']}/findings/missing_noc_esf:-/disposition", body
    )
    assert acknowledged.status_code == 200, acknowledged.text


async def test_a_refused_decision_writes_neither_the_case_nor_an_audit_row(
    api: Api, migrator: AsyncEngine
) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M04")
    before = await _audit(migrator, case["case_id"])

    await open_sources(an, case)
    refused = await an.post(
        f"/orders/{case['case_id']}/prepare", {"case_version": case["case_version"]}
    )

    assert refused.status_code == 409
    assert await _audit(migrator, case["case_id"]) == before
    assert (await order(an, case["case_id"]))["case_version"] == case["case_version"]


async def test_a_retried_decision_acts_once(api: Api) -> None:
    an = api.as_(AN)
    case = await order_of(an, "M01")
    await open_sources(an, case)
    body = {"case_version": case["case_version"]}

    first = await an.post(f"/orders/{case['case_id']}/prepare", body, key="retry-1")
    again = await an.post(f"/orders/{case['case_id']}/prepare", body, key="retry-1")

    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert (await order(an, case["case_id"]))["case_version"] == case["case_version"] + 1


async def test_once_prepared_every_value_reads_as_checked_by_a_person(api: Api) -> None:
    an = api.as_(AN)
    ready = await prepared(an, await order_of(an, "M01"))

    states = {s for line in ready["lines"] for s in line["value_states"].values()}

    assert states == {"confirmed"}
