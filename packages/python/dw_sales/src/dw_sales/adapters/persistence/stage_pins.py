"""How many open cases each stage version still has (ticket 61, step 2).

Read through `sales.open_cases_by_stage()` (migration `7add0d23936a`), the one
read that crosses tenants here: counts per (stage, version), no tenant, no
case. Start-up refuses to run without a handler for a version that is not
zero (`StageHandlers.refuse_orphans`).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


async def open_cases_by_stage(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict[tuple[str, str], int]:
    async with session_factory() as session:
        rows = await session.execute(
            sa.text("SELECT stage, version, open_cases FROM sales.open_cases_by_stage()")
        )
        return {(row.stage, row.version): int(row.open_cases) for row in rows}
