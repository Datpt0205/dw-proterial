"""A tenant's own Sales rules through the API, against PostgreSQL (tickets 19,
36 and 38).

A proposal opens a `sales.rules` platform approval; the head decides it on
`/approvals` and the worker carries the decision out (`_carry_out` does here
what the worker does). The demo tenant's version (`sales_order_rules@1.5.1`,
in the sample set) went the same way when the suite's database was seeded
(`seed_demo_rules`), as `make demo-reset` does. Each test here that approves
another version puts the seeded one back in force after.
"""

from __future__ import annotations

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
from sales_api_harness import AN, BAO, DIEU, GIANG, HA, Api, user_id
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
    assert DEMO is not None
    document = DEMO.model_dump(mode="json", by_alias=True)
    document["policy_version"] = version
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
    # the head may not approve her own; a decision says why.
    assert (await dieu.decide(approval_id, decision)).status_code == 404
    own = await giang.post("/rules/sales_order_rules/versions", {"document": _document("9.0.2")})
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
