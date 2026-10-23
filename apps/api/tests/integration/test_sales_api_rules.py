"""A tenant's own Sales rules through the API, against PostgreSQL (tickets 19,
36 and 38).

A proposal opens a `sales.rules` platform approval; the head decides it on
`/approvals` and the worker carries the decision out (`_carry_out` does here
what the worker does). The demo tenant's version (`sales_order_rules@1.5.2`,
in the sample set, every model step on over stand-in measurements) went the
same way when the suite's database was seeded (`seed_demo_rules`), as
`make demo-reset` does with 1.5.3 (every step off). Each test here that
approves another version puts the seeded one back in force after.
"""

from __future__ import annotations

import ast
import email
import email.policy
import json
import uuid
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sales_api_harness import AN, BAO, DIEU, GIANG, HA, TAM, Api, user_id
from sales_flow import (
    cross_checked,
    dates,
    decide,
    order_of,
    replied,
    submitted,
    uploaded,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from dw_kernel.ports import SystemClock, Uuid4Generator
from dw_platform.adapters.persistence.repositories import (
    SqlApprovalRepository,
    SqlAuditRepository,
)
from dw_platform.application.access_context import AccessContext
from dw_sales.adapters.assembly import build_rule_settlement
from dw_sales.adapters.mock.fixtures import DATA_DIR
from dw_sales.adapters.order_rules import load_tenant_order_rules
from dw_sales.adapters.policy_files import load_sales_policies
from dw_sales.application.rules import RULES_DECIDED, RuleKey

pytestmark = pytest.mark.integration

DEMO = load_tenant_order_rules(DATA_DIR / "policies")
assert DEMO is not None
_CONFIGS = Path(__file__).resolve().parents[4] / "configs"
PLATFORM = load_sales_policies(_CONFIGS / "policies", _CONFIGS / "copy")


@pytest.fixture
async def rules_api(api: Api, migrator: AsyncEngine) -> AsyncIterator[Api]:
    yield api
    # The seeded version back in force; the versions a test made, and the
    # approvals they opened, gone.
    async with migrator.begin() as conn:
        await conn.execute(
            sa.text("DELETE FROM sales.rule_versions WHERE version <> :v"),
            {"v": DEMO.policy_version},
        )
        await conn.execute(
            sa.text(
                "DELETE FROM platform.approval_requests WHERE approval_type = 'sales.rules'"
                " AND id NOT IN (SELECT approval_id FROM sales.rule_versions"
                " WHERE approval_id IS NOT NULL)"
            )
        )
        await conn.execute(
            sa.text("UPDATE sales.rule_versions SET status = 'approved' WHERE version = :v"),
            {"v": DEMO.policy_version},
        )


async def _carry_out(api: Api, migrator: AsyncEngine, approval_id: str) -> str:
    """What the worker does with the decision's outbox event: the event is
    there, written by the decision, and its settlement applies it."""
    async with migrator.connect() as conn:
        event = (
            await conn.execute(
                sa.text(
                    "SELECT tenant_id, workspace_id, payload FROM platform.outbox_events"
                    " WHERE event_type = :type AND aggregate_id = :id"
                ),
                {"type": RULES_DECIDED, "id": approval_id},
            )
        ).one()
    settlement = build_rule_settlement(
        configs=_CONFIGS,
        session_factory=api.sessions,
        audit=SqlAuditRepository,
        approvals=SqlApprovalRepository,
        clock=SystemClock(),
        ids=Uuid4Generator(),
    )
    decider = AccessContext(
        tenant_id=event.tenant_id,
        workspace_id=event.workspace_id,
        principal_id=uuid.UUID(event.payload["decided_by"]),
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )
    return (await settlement.settle(uuid.UUID(approval_id), decider)).status


def _document(version: str, **changes: Any) -> dict[str, Any]:
    """The demo version renumbered, its model steps as the platform ships
    them (off): turning one on is refused without a passing measurement for
    the proposing tenant (dw_sales ADR 0005, addendum of 2026-10-23), which
    only the demo tenant has here; a test about that turns one on itself."""
    assert DEMO is not None
    document = DEMO.model_dump(mode="json", by_alias=True)
    document["policy_version"] = version
    document["model_assist"] = PLATFORM.order_rules.model_assist.model_dump(mode="json")
    document.update(changes)
    return document


async def test_the_seeded_version_went_through_the_route_and_is_in_force(
    rules_api: Api, migrator: AsyncEngine
) -> None:
    listed = await rules_api.as_(AN).get("/rules")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["in_force"]["sales_order_rules"] == DEMO.version
    assert body["layers"] == {
        key.value: "tenant" if key is RuleKey.ORDER_RULES else "platform" for key in RuleKey
    }
    (seeded,) = [v for v in body["versions"] if v["version"] == DEMO.policy_version]
    assert (seeded["status"], seeded["proposed_by"], seeded["decided_by"]) == (
        "approved",
        str(user_id(AN)),
        str(user_id(GIANG)),
    )
    assert seeded["approval_id"] is not None
    async with migrator.connect() as conn:
        actions = (
            (
                await conn.execute(
                    sa.text(
                        "SELECT action FROM platform.audit_events WHERE resource_id = :id"
                        " ORDER BY occurred_at"
                    ),
                    {"id": seeded["version_id"]},
                )
            )
            .scalars()
            .all()
        )
    assert list(actions) == ["sales.rules.proposed", "sales.rules.approved"]
    # A case DW1 checks is stamped with it.
    case = await order_of(rules_api.as_(AN), "M01")
    assert case["rules_version"] == DEMO.version


async def test_proposed_by_a_pic_approved_by_the_head_and_stamped_on_the_next_case(
    rules_api: Api, migrator: AsyncEngine
) -> None:
    an, dieu, giang = rules_api.as_(AN), rules_api.as_(DIEU), rules_api.as_(GIANG)
    proposed = await an.post("/rules/sales_order_rules/versions", {"document": _document("9.0.1")})
    assert proposed.status_code == 200, proposed.text
    approval_id = proposed.json()["approval_id"]
    decision = {"approve": True, "comment": "Đồng ý"}

    # Without `sales.rules.approve` the stamped approval is not even visible;
    # the head may not approve her own (on another key: 9.0.1 holds this
    # one's single open proposal); a decision says why.
    assert (await dieu.decide(approval_id, decision)).status_code == 404
    kpi = PLATFORM.kpi.model_dump(mode="json", by_alias=True)
    own = await giang.post("/rules/sales_kpi/versions", {"document": _bumped(kpi, "9.0.2")})
    assert own.status_code == 200, own.text
    refused = await giang.decide(own.json()["approval_id"], decision)
    assert refused.status_code == 409
    assert refused.json()["details"]["rule"] == "maker_checker"
    assert (await giang.decide(approval_id, {"approve": True, "comment": ""})).status_code == 409

    approved = await giang.decide(approval_id, decision)
    assert approved.status_code == 200, approved.text
    # Recorded, not yet carried out: the worker applies it.
    body = (await an.get("/rules")).json()
    assert body["in_force"]["sales_order_rules"] == DEMO.version
    assert await _carry_out(rules_api, migrator, approval_id) == "approved"
    assert await _carry_out(rules_api, migrator, approval_id) == "approved"  # redelivered
    body = (await an.get("/rules")).json()
    assert body["in_force"]["sales_order_rules"] == "sales_order_rules@9.0.1"
    statuses = {v["version"]: v["status"] for v in body["versions"]}
    assert statuses[DEMO.policy_version] == "superseded"
    # The reason the head gave on the approval is the version's, in the list.
    comments = {v["version"]: v["comment"] for v in body["versions"]}
    assert comments["9.0.1"] == "Đồng ý"
    assert (await order_of(an, "M01"))["rules_version"] == "sales_order_rules@9.0.1"

    # The database refuses a decision by the proposer whatever writes it, and
    # a proposal that waits on no approval.
    async with migrator.begin() as conn:
        with pytest.raises(sa.exc.IntegrityError, match="ck_rule_versions_checker_not_maker"):
            await conn.execute(
                sa.text(
                    "UPDATE sales.rule_versions SET status = 'rejected',"
                    " decided_by = proposed_by, decided_at = now() WHERE id = :id"
                ),
                {"id": own.json()["version_id"]},
            )
    async with migrator.begin() as conn:
        with pytest.raises(sa.exc.IntegrityError, match="ck_rule_versions_proposed_has_approval"):
            await conn.execute(
                sa.text("UPDATE sales.rule_versions SET approval_id = NULL WHERE id = :id"),
                {"id": own.json()["version_id"]},
            )
    async with migrator.begin() as conn:
        with pytest.raises(sa.exc.IntegrityError, match="fk_rule_versions_approval_requests"):
            await conn.execute(
                sa.text("UPDATE sales.rule_versions SET approval_id = :other WHERE id = :id"),
                {"other": uuid.uuid4(), "id": own.json()["version_id"]},
            )


async def test_an_override_never_resolves_for_another_tenant(rules_api: Api) -> None:
    bao = rules_api.as_(BAO, tenant="tenant-beta")
    listed = await bao.get("/rules")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["versions"] == []
    assert body["layers"]["sales_order_rules"] == "platform"
    assert body["in_force"]["sales_order_rules"] != DEMO.version
    # Nor can beta decide alpha's version by its approval's id.
    proposed = await rules_api.as_(AN).post(
        "/rules/sales_order_rules/versions", {"document": _document("9.0.3")}
    )
    alpha = proposed.json()["approval_id"]
    assert (await bao.decide(alpha, {"approve": True, "comment": "x"})).status_code == 404


async def test_unknown_keys_and_invalid_documents_are_refused(rules_api: Api) -> None:
    an = rules_api.as_(AN)
    # An unknown key is no path; order rules are no document of another key.
    for key in ("nope", "sales_quote_rules", "sales_emails"):
        response = await an.post(f"/rules/{key}/versions", {"document": _document("9.1.0")})
        assert response.status_code == 422, key
    broken = _document("9.1.1")
    del broken["findings"]
    response = await an.post("/rules/sales_order_rules/versions", {"document": broken})
    assert response.status_code == 422
    assert response.json()["details"]["errors"] == "['findings']"
    # A platform number is not a tenant's.
    platform = (await an.get("/rules")).json()["platform"]
    shipped = next(p["ref"] for p in platform if p["key"] == "sales_order_rules")
    reused = await an.post(
        "/rules/sales_order_rules/versions",
        {"document": _document(shipped.partition("@")[2])},
    )
    assert reused.status_code == 409


async def test_a_viewer_neither_lists_nor_proposes(rules_api: Api) -> None:
    ha = rules_api.as_(HA)
    assert (await ha.get("/rules")).status_code == 403
    proposed = await ha.post("/rules/sales_order_rules/versions", {"document": _document("9.2.0")})
    assert proposed.status_code == 403
    # No Sales route decides a version (ticket 38): the path is gone.
    gone = await rules_api.as_(GIANG).post(
        f"/rules/versions/{uuid.uuid4()}/decision", {"approve": True}
    )
    assert gone.status_code == 404


# ------------------------------------------------ quote rules and copy (36) --


def _quote_rules(version: str, validity_days: int) -> dict[str, Any]:
    document = PLATFORM.quote_rules.model_dump(mode="json", by_alias=True)
    return {**document, "policy_version": version, "validity_days": validity_days}


async def _approved(
    api: Api, migrator: AsyncEngine, key: str, document: dict[str, Any]
) -> dict[str, Any]:
    proposed = await api.as_(AN).post(f"/rules/{key}/versions", {"document": document})
    assert proposed.status_code == 200, proposed.text
    approval_id = proposed.json()["approval_id"]
    decided = await api.as_(GIANG).decide(approval_id, {"approve": True, "comment": "Đồng ý"})
    assert decided.status_code == 200, decided.text
    assert await _carry_out(api, migrator, approval_id) == "approved"
    body: dict[str, Any] = proposed.json()
    return body


async def test_a_quote_case_is_opened_under_the_tenants_quote_rules_and_keeps_them(
    rules_api: Api, migrator: AsyncEngine
) -> None:
    """Ticket 36: alpha's own quote rules stamp the case it opens; a version
    approved after that does not reach the case (its quotation is valid for
    the stamped version's days); tenant beta resolves the platform's."""
    await _approved(rules_api, migrator, "sales_quote_rules", _quote_rules("9.0.1", 30))
    dieu = rules_api.as_(DIEU)
    case = await replied(dieu, "M10", "YCBG-2609-030", "M25")
    await _approved(rules_api, migrator, "sales_quote_rules", _quote_rules("9.0.2", 120))

    pending = await submitted(dieu, case)

    assert case["rules_version"] == "sales_quote_rules@9.0.1"
    submission = pending["submission"]
    issued, valid_to = (date.fromisoformat(submission[k]) for k in ("issued_on", "valid_to"))
    assert (valid_to - issued).days + 1 == 30
    body = (await rules_api.as_(AN).get("/rules")).json()
    assert (body["in_force"]["sales_quote_rules"], body["layers"]["sales_quote_rules"]) == (
        "sales_quote_rules@9.0.2",
        "tenant",
    )
    beta = (await rules_api.as_(BAO, tenant="tenant-beta").get("/rules")).json()
    assert beta["in_force"]["sales_quote_rules"] == PLATFORM.quote_rules.ref
    assert beta["layers"]["sales_quote_rules"] == "platform"
    assert beta["versions"] == []


async def test_a_tenants_email_copy_writes_its_drafts_and_the_file_names_it(
    rules_api: Api, migrator: AsyncEngine
) -> None:
    """Ticket 36: the confirmation draft is written in alpha's own copy, and
    the artifact records that version."""
    document = PLATFORM.emails.model_dump(mode="json", by_alias=True)
    subject = "Xác nhận PO ${po_no} - Công ty Demo"
    document["emails"]["confirmation_draft"]["vi"]["subject"] = subject
    approved = await _approved(
        rules_api, migrator, "sales_emails", {**document, "version": "9.0.1"}
    )
    assert approved["ref"] == "sales_emails@9.0.1"
    an, dieu = rules_api.as_(AN), rules_api.as_(DIEU)
    crossed = await cross_checked(dieu, await uploaded(an, await order_of(an, "M01")))
    confirmed = await decide(an, crossed, "confirm", {"delivery_dates": dates(crossed)})

    rendered = await an.post(
        f"/orders/{confirmed['case_id']}/artifacts",
        {"kind": "confirmation_draft", "case_version": confirmed["case_version"]},
    )

    assert rendered.status_code == 200, rendered.text
    (view,) = rendered.json()["artifacts"]
    assert view["template_ref"] == "sales_emails.confirmation_draft.vi@9.0.1"
    served = await an.get(f"/orders/{confirmed['case_id']}/artifacts/{view['artifact_id']}")
    assert served.status_code == 200
    message = email.message_from_bytes(served.content, policy=email.policy.default)
    assert message["Subject"] == f"Xác nhận PO {confirmed['po_no']} - Công ty Demo"


async def test_a_hand_off_copy_with_a_format_spec_is_refused(rules_api: Api) -> None:
    """Ticket 36: a tenant's hand-off copy is filled with `str.format`, so a
    placeholder that is not a bare known name is refused at proposal."""
    document = PLATFORM.handoff_copy.model_dump(mode="json", by_alias=True)
    for line in ("{line_no:>999999999}", "{line_no.__class__}", "{secret}"):
        response = await rules_api.as_(AN).post(
            "/rules/sales_handoffs/versions",
            {"document": {**document, "version": "9.0.1", "line": line}},
        )
        assert response.status_code == 422, line
        assert "line" in response.json()["details"]["errors"]


async def test_the_table_refuses_a_document_naming_no_key_or_another_keys_version(
    rules_api: Api, migrator: AsyncEngine
) -> None:
    """Ticket 36: `ck_rule_versions_document` reads a policy's `policy_id` and
    a copy's `copy_id`; a document naming neither is refused, not passed as
    NULL. Written around the service, as an application bug would."""
    copy = PLATFORM.emails.model_dump(mode="json", by_alias=True)
    for document in ({}, {**copy, "version": "9.9.8"}, {**copy, "copy_id": "sales_documents"}):
        async with migrator.begin() as conn:
            with pytest.raises(sa.exc.IntegrityError, match="ck_rule_versions_document"):
                await conn.execute(
                    sa.text(
                        "INSERT INTO sales.rule_versions (id, tenant_id, workspace_id, key,"
                        " version, document, status, proposed_by, proposed_at)"
                        " SELECT gen_random_uuid(), tenant_id, workspace_id, 'sales_emails',"
                        " '9.9.9', CAST(:document AS jsonb), 'proposed', proposed_by, now()"
                        " FROM sales.rule_versions LIMIT 1"
                    ),
                    {"document": json.dumps(document)},
                )


# ------------------------------------- tenant IT proposes (2026-10-21) --


def _bumped(document: dict[str, Any], version: str) -> dict[str, Any]:
    """A platform document under a tenant's number: a policy names it
    ``policy_version``, a copy file ``version``."""
    field = "policy_version" if "policy_version" in document else "version"
    return {**document, field: version}


async def test_tenant_it_proposes_a_rule_and_the_head_approves_it(
    rules_api: Api, migrator: AsyncEngine
) -> None:
    """dw_sales ADR 0003 addendum: Tâm (`sales_rules_editor`) proposes the
    Bravo upload template; his own decision is refused (no `approvals.decide`,
    no `sales.rules.approve`), and the head's is carried out."""
    tam, giang = rules_api.as_(TAM), rules_api.as_(GIANG)
    upload = PLATFORM.upload.model_dump(mode="json", by_alias=True)
    proposed = await tam.post(
        "/rules/sales_bravo_upload/versions", {"document": _bumped(upload, "9.0.1")}
    )
    assert proposed.status_code == 200, proposed.text
    assert proposed.json()["proposed_by"] == str(user_id(TAM))
    approval_id = proposed.json()["approval_id"]

    refused = await tam.decide(approval_id, {"approve": True, "comment": "Đồng ý"})
    assert refused.status_code == 403, refused.text
    approved = await giang.decide(approval_id, {"approve": True, "comment": "Đồng ý"})
    assert approved.status_code == 200, approved.text
    assert await _carry_out(rules_api, migrator, approval_id) == "approved"
    body = (await tam.get("/rules")).json()
    assert body["in_force"]["sales_bravo_upload"] == "sales_bravo_upload@9.0.1"


async def test_tenant_it_is_shown_no_price_bearing_rule_and_cannot_propose_one(
    rules_api: Api, migrator: AsyncEngine
) -> None:
    """A key holding prices or price policy asks for `sales.price.read` too,
    which IT never holds: absent from Tâm's list, every version of it
    included, and 403 on its schema, its platform documents and a proposal."""
    # A price the tenant's own pricing version holds, and nobody else's.
    floor = "0.2468"
    pricing = PLATFORM.pricing.model_dump(mode="json", by_alias=True)
    await _approved(
        rules_api,
        migrator,
        "sales_pricing",
        {**_bumped(pricing, "9.0.1"), "floor_margin": floor},
    )
    await _approved(rules_api, migrator, "sales_quote_rules", _quote_rules("9.0.1", 45))
    tam = rules_api.as_(TAM)

    listed = await tam.get("/rules")

    assert listed.status_code == 200, listed.text
    # The order rules too: the tenant's seeded version holds the price
    # tolerance and the LME rule (dw_sales ADR 0003).
    price_keys = ("sales_pricing", "sales_quote_rules", "sales_order_rules")
    for hidden in (*price_keys, floor, "copper_adders"):
        assert hidden not in listed.text, hidden
    # The search can fail: An, who reads prices, is shown all three.
    shown = (await rules_api.as_(AN).get("/rules")).text
    assert all(text in shown for text in (*price_keys, floor))
    for key, document in (
        ("sales_pricing", _bumped(pricing, "9.0.2")),
        ("sales_quote_rules", _quote_rules("9.0.2", 60)),
        ("sales_order_rules", _document("9.0.2")),
    ):
        assert (await tam.get(f"/rules/{key}/schema")).status_code == 403
        assert (await tam.get(f"/rules/{key}/platform")).status_code == 403
        refused = await tam.post(f"/rules/{key}/versions", {"document": document})
        assert refused.status_code == 403, key
    async with migrator.connect() as conn:
        versions = await conn.scalar(
            sa.text("SELECT count(*) FROM sales.rule_versions WHERE proposed_by = :u"),
            {"u": user_id(TAM)},
        )
    assert versions == 0


# ------------------------- one proposal waiting per key (2026-10-22) --


async def _open_rule_approvals(migrator: AsyncEngine) -> int:
    async with migrator.connect() as conn:
        count = await conn.scalar(
            sa.text(
                "SELECT count(*) FROM platform.approval_requests"
                " WHERE approval_type = 'sales.rules' AND status = 'pending'"
            )
        )
    return int(count or 0)


async def test_a_second_proposal_on_a_key_waits_until_the_first_is_decided(
    rules_api: Api, migrator: AsyncEngine
) -> None:
    """`uq_rule_versions_one_proposed`: a version is the whole document, so a
    second proposal started from the same version would silently undo the
    first when both are approved. While one waits, another on the same key is
    refused (409) naming the waiting version, who proposed it and when, and
    writes nothing; rejecting or approving the first frees the key."""
    an, dieu, giang = rules_api.as_(AN), rules_api.as_(DIEU), rules_api.as_(GIANG)
    first = await an.post("/rules/sales_order_rules/versions", {"document": _document("9.3.0")})
    assert first.status_code == 200, first.text
    waiting = await _open_rule_approvals(migrator)

    refused = await dieu.post("/rules/sales_order_rules/versions", {"document": _document("9.3.1")})

    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["details"]["rule"] == "one_open_proposal"
    assert body["details"]["version_id"] == first.json()["version_id"]
    assert body["details"]["proposed_by"] == str(user_id(AN))
    assert "9.3.0" in body["message"] and "Nguyễn Văn An" in body["message"]
    assert "(giờ Việt Nam)" in body["message"]
    # Nothing written: no second version, and the approval the refused
    # proposal opened in its transaction rolled back with it.
    assert await _open_rule_approvals(migrator) == waiting
    listed = (await an.get("/rules")).json()["versions"]
    assert [v["version"] for v in listed if v["status"] == "proposed"] == ["9.3.0"]
    # Another key is not held by it.
    kpi = PLATFORM.kpi.model_dump(mode="json", by_alias=True)
    other = await dieu.post("/rules/sales_kpi/versions", {"document": _bumped(kpi, "9.3.0")})
    assert other.status_code == 200, other.text

    # Rejected: the key is free.
    rejected = await giang.decide(
        first.json()["approval_id"], {"approve": False, "comment": "Chưa"}
    )
    assert rejected.status_code == 200, rejected.text
    assert await _carry_out(rules_api, migrator, first.json()["approval_id"]) == "rejected"
    second = await dieu.post("/rules/sales_order_rules/versions", {"document": _document("9.3.1")})
    assert second.status_code == 200, second.text
    # Approved: free again.
    approval_id = second.json()["approval_id"]
    assert (
        await giang.decide(approval_id, {"approve": True, "comment": "Đồng ý"})
    ).status_code == 200
    assert await _carry_out(rules_api, migrator, approval_id) == "approved"
    third = await an.post("/rules/sales_order_rules/versions", {"document": _document("9.3.2")})
    assert third.status_code == 200, third.text

    # The database refuses a second waiting row whatever writes it: the
    # rejected first one put back to waiting beside the third.
    async with migrator.begin() as conn:
        with pytest.raises(sa.exc.IntegrityError, match="uq_rule_versions_one_proposed"):
            await conn.execute(
                sa.text(
                    "UPDATE sales.rule_versions SET status = 'proposed', decided_by = NULL,"
                    " decided_at = NULL WHERE id = :id"
                ),
                {"id": first.json()["version_id"]},
            )


async def test_another_tenants_waiting_proposal_holds_nothing_here(rules_api: Api) -> None:
    """Narrowed by tenant: beta's open proposal on a key is beta's alone."""
    bao = rules_api.as_(BAO, tenant="tenant-beta")
    beta = await bao.post("/rules/sales_order_rules/versions", {"document": _document("9.4.0")})
    assert beta.status_code == 200, beta.text

    alpha = await rules_api.as_(AN).post(
        "/rules/sales_order_rules/versions", {"document": _document("9.4.0")}
    )

    assert alpha.status_code == 200, alpha.text
    # The search can fail: beta's key is held, by beta's own waiting one.
    again = await bao.post("/rules/sales_order_rules/versions", {"document": _document("9.4.1")})
    assert again.status_code == 409
    assert again.json()["details"]["version_id"] == beta.json()["version_id"]


# ------------------------------------------- the process page (2026-10-22) --


async def test_the_process_page_serves_no_price_bearing_key_to_tenant_it(rules_api: Api) -> None:
    """Absent, not empty: Tâm (no `sales.price.read`) is served every step
    and no field of a key holding prices; An is served them; a viewer is
    refused."""
    served = await rules_api.as_(TAM).get("/rules/process")

    assert served.status_code == 200, served.text
    body = served.json()
    assert [lane["kind"] for lane in body["lanes"]] == ["order", "quote"]
    assert len(body["steps"]) == 23
    for hidden in (
        "sales_order_rules",
        "sales_quote_rules",
        "sales_pricing",
        "price.relative_tolerance",
        "floor_margin",
    ):
        assert hidden not in served.text, hidden
    shown = await rules_api.as_(AN).get("/rules/process")
    assert all(key in shown.text for key in ("sales_order_rules", "sales_pricing", "floor_margin"))
    assert (await rules_api.as_(HA).get("/rules/process")).status_code == 403


# ----------------------------- a model step earns its switch (2026-10-23) --


async def test_a_tenant_with_no_measurement_cannot_turn_a_model_step_on(rules_api: Api) -> None:
    """Beta runs the platform's rules (every step off) and no live eval was
    recorded for it: a version turning a step on is refused, naming the step,
    its bar and "chưa đo"; the same version with the step off is not."""
    bao = rules_api.as_(BAO, tenant="tenant-beta")
    document = _document("9.6.0")
    document["model_assist"]["message_intent"] = True

    refused = await bao.post("/rules/sales_order_rules/versions", {"document": document})

    assert refused.status_code == 409, refused.text
    body = refused.json()
    assert body["details"]["rule"] == "model_bar_unmet"
    # The error envelope serves each detail as a string (`exception_handlers`).
    steps = ast.literal_eval(body["details"]["steps"])
    assert [step["step"] for step in steps] == ["message_intent"]
    assert "chưa đo" in body["message"] and "90%" in body["message"]
    allowed = await bao.post("/rules/sales_order_rules/versions", {"document": _document("9.6.0")})
    assert allowed.status_code == 200, allowed.text


async def test_the_process_page_serves_each_steps_model_uses_actors_and_edge_actions(
    rules_api: Api,
) -> None:
    """The demo tenant's version turns every model step on, and the suite
    recorded a measurement at its bar for each: each is served in effect.
    The actors are the database's own roles and permission sets."""
    body = (await rules_api.as_(AN).get("/rules/process")).json()
    steps = {step["step_id"]: step for step in body["steps"]}
    models = [model for step in body["steps"] for model in step["models"]]
    assert len(models) == 6
    for model in models:
        assert model["enabled"] and model["effective"], model
        assert model["latest"]["passed"] and model["latest"]["model"] == model["model"]
    assert steps["O1"]["uses"] == {"lists": ["customers"], "layouts": True}
    cross = {actor["key"] for actor in steps["O9"]["actors"]}
    assert cross and all(
        actor["scopes"] == ["sales.order.cross_check"] for actor in steps["O9"]["actors"]
    )
    edge = next(
        e
        for lane in body["lanes"]
        for e in lane["edges"]
        if (e["from"], e["to"]) == ("pending_approval", "approved")
    )
    assert (edge["action"], edge["actor"]) == ("approve", "approver")
    assert "approval" in edge["guards"]
    # Tenant IT reads no order rules, so no model switch is served to it.
    hidden = (await rules_api.as_(TAM).get("/rules/process")).json()
    assert all(step["models"] == [] for step in hidden["steps"])
