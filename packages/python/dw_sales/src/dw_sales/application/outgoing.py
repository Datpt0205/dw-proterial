"""A message Sales sent: which stored message is one (ticket 25, dw_sales ADR
0009 decision 3).

Each person's flow exports Sent Items into the same drop folder as their
Inbox, so the stored mailbox holds Sales' own mail beside the customers'.
**A message is outgoing when its sender is a member's own sign-in address**,
as the workspace's directory holds it (`sales_addresses`, the
platform's user record, verified at sign-in): never the folder the flow wrote
it into, never a header or a field anyone could send. Two exceptions, both
facts the server holds:

- **an upload is never outgoing**: "Tải PO lên" stores the uploader as its
  sender (ticket 18), and it is the customer's PO, by that person's word;
- **a sender the receiving mail system says is forged is not trusted** as
  the member: a mail whose SPF, DKIM or DMARC result is ``fail`` (or SPF's
  ``softfail``) arrived from outside wearing a member's address. It is
  processed as incoming, so a person sees it, rather than hidden as context.
  A copy saved from Sent Items carries no such result at all (``none``).

An outgoing message is stored and threaded like any (`threads.thread_key`),
and listed in the inbox marked "Sales gửi". It is never processed into a
case, never routed, never read for values and has no disposition of its own:
it is context, what Sales asked and when. Where the tenant turns the thread
intents step on, DW1 reads what it does (ticket 26) and keeps the reading
beside it (`SentRead`); a case on its thread may then propose a step for a
person to take. The mailbox lane takes it up only then (`InboxLane`).
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import Final

from dw_platform.application.access_context import AccessContext
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.order_ports import UPLOAD_PREFIX
from dw_sales.application.ports import MemberDirectoryPort

# The authentication results that say the sender address was not the
# sender's to use.
_FORGED: Final = frozenset({"fail", "softfail"})


def is_outgoing(message: InboundMessage, sales: Collection[str]) -> bool:
    """Whether ``message`` is one Sales sent (module docstring). ``sales``:
    the members' sign-in addresses, lower-cased."""
    if message.message_id.startswith(UPLOAD_PREFIX):
        return False
    if message.sender.address.lower() not in sales:
        return False
    results = message.authentication
    return _FORGED.isdisjoint({results.spf, results.dkim, results.dmarc})


async def sales_addresses(directory: MemberDirectoryPort, context: AccessContext) -> frozenset[str]:
    """The sign-in addresses of the workspace's people, lower-cased, as the
    platform's user record holds them. A service account signs in nowhere,
    so it has none here."""
    return frozenset(
        member.email.lower()
        for member in await directory.list_members(context)
        if member.email is not None and not member.service
    )


async def outgoing_in(
    directory: MemberDirectoryPort, context: AccessContext
) -> Callable[[InboundMessage], bool]:
    """`is_outgoing` with the addresses of ``context``'s workspace bound:
    read once, for every message a caller looks at."""
    sales = await sales_addresses(directory, context)
    return lambda message: is_outgoing(message, sales)
