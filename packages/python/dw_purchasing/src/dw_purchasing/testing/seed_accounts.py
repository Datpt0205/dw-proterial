"""DW2's service account in a workspace, for the demo seed and the tests:
what the platform's provisioning creates with every new tenant
(`DW2_SERVICE_ACCOUNT`), written for a tenant that existed before it.

Re-running resets the membership to exactly the role `purchasing_dw2`, so a
role or a permission set given to the account by hand is taken off again.
Local and test only: the platform creates the account in a deployment.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from dw_platform.adapters.persistence import tables
from dw_purchasing.application.automation_lane import (
    DW2_ROLE,
    DW2_SERVICE_ACCOUNT,
    dw2_subject,
)


async def seed_dw2_account(
    conn: AsyncConnection, scopes: Sequence[tuple[uuid.UUID, uuid.UUID]]
) -> dict[uuid.UUID, uuid.UUID]:
    """DW2's account in each (tenant, workspace), as the migrator writes it;
    its user id per tenant."""
    found: dict[uuid.UUID, uuid.UUID] = {}
    for tenant_id, workspace_id in scopes:
        subject = dw2_subject(tenant_id)
        user = pg_insert(tables.users).values(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"dw2-user:{subject}"),
            subject=subject,
            display_name=DW2_SERVICE_ACCOUNT.display_name,
        )
        await conn.execute(
            user.on_conflict_do_update(
                index_elements=["subject"],
                set_={"display_name": user.excluded.display_name, "email": None},
            )
        )
        user_id = (
            await conn.execute(
                sa.select(tables.users.c.id).where(tables.users.c.subject == subject)
            )
        ).scalar_one()
        membership = pg_insert(tables.memberships).values(
            id=uuid.uuid5(uuid.NAMESPACE_URL, f"dw2-membership:{workspace_id}:{subject}"),
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role_keys=[DW2_ROLE],
            permission_set_keys=[],
        )
        await conn.execute(
            membership.on_conflict_do_update(
                constraint="uq_memberships_scope_user",
                set_={"role_keys": [DW2_ROLE], "permission_set_keys": []},
            )
        )
        found[tenant_id] = user_id
    return found
