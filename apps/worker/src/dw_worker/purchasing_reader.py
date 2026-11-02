"""DW2's `MailFileReaderPort` over the reader sandbox's client that exists.

ADR 0013 decision 2 makes the reader's mail operation the platform's; until
that split, the client is Sales' (`dw_sales.adapters.reader_client`), and
DW2 may not import Sales. So the composition root, which may import both,
adapts one to the other here: the same bytes read by the same sandbox, the
answer turned into DW2's own types. Removed when the split lands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from dw_purchasing.application.mail_drop import MailFile, MailRefused
from dw_sales.application import mail_drop as sales


class _SalesMailReader(Protocol):
    async def read_mail(self, data: bytes) -> sales.MailFile | sales.MailRefused: ...


@dataclass(frozen=True)
class PurchasingMailReader:
    """Implements DW2's `MailFileReaderPort`. A reader that does not answer
    raises as it did (`InfrastructureError`)."""

    reader: _SalesMailReader

    async def read_mail(self, data: bytes) -> MailFile | MailRefused:
        read = await self.reader.read_mail(data)
        if isinstance(read, sales.MailRefused):
            return MailRefused(read.reason)
        return MailFile(message=read.message, contents=read.contents)
