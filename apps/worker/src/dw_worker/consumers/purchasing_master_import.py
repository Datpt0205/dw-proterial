"""DW2's master-data workbooks, read as they are uploaded.

Each tick hands the one workspace this host serves DW2 for to
`dw_purchasing.application.master_data.MasterImportLane`, which decides
everything: the scan, the reading, what the rows mean, what is forgotten.
This module only paces it. Counts only: no file name or cell is logged here.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from dw_platform.application.rule_versions import ContextScope

logger = logging.getLogger("dw_worker.purchasing_master_import")

# A person waits on the page for their file to be read.
INTERVAL_SECONDS = 15.0


class ImportLane(Protocol):
    async def tick(self, scope: ContextScope, *, limit: int = 5) -> int: ...


def build_purchasing_master_import_consumer(
    lane: ImportLane, scope: ContextScope
) -> Callable[[], Awaitable[None]]:
    async def consume() -> None:
        read = await lane.tick(scope)
        if read:
            logger.info("purchasing_master_import: read %d workbook(s)", read)

    return consume
