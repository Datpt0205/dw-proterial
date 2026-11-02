"""DW1 reads real mail from a folder of `.eml` files: the `sales_mail_drop` lane
(ticket 43).

Proterial gives DW1 no access to Microsoft 365. A DW1 account owns one
OneDrive folder per Sales PIC; each PIC runs a copy of one Power Automate
flow that exports every mail reaching their Inbox as an `.eml` file into
their folder, and a PC in the plant syncs the folders and shares them with
DW1's host. **The folder is a drop box, not the mailbox**: each tick, this lane
reads the files it has not handled before and stores each message, with its
attachments, in the stored mailbox (`MailStorePort`, PostgreSQL). Everything
else reads the stored mailbox, through `InboxPort`, like the mock.

**One tick:**

1. The names already handled are read once per process (`handled_sources`):
   a restart does not read the folders' whole history again.
2. Each `.eml` file not seen yet, in the folder or one level below it (a
   folder per PIC), oldest name first (the flow names a file by when it wrote
   it). A file modified less than `SETTLE` ago, or still empty, may be
   arriving (OneDrive writes it in place): it waits for a later tick.
3. A file over the size limit, or one the reader refuses (`MailRefused`), is
   recorded as handled with its reason (`MailStorePort.refuse`), so no
   restart reads it again, and the people who process the mailbox are told
   which file did not arrive (`MailDropNoticePort.refused`, Đạt 2026-10-29:
   "không thể làm hỏng luồng rồi im lặng luôn được"). Its content is never
   logged.
4. Every other mail is stored, whoever sent it, with one audit event, in one
   transaction (`MailStorePort.store`): internal mail included (Đạt,
   2026-11-02: DW1's model sorts every mail; `ignored_sender_domains` left
   the order rules in 1.9.0). The same mail in a second file is stored once,
   audited once: a copy of the file has the same id (its hash), and one mail
   exported from two PICs' mailboxes (To and Cc) carries the same Message-ID
   from the same sender.

**It audits as itself**: `lane_audit_event` from `system_actor(MAIL_DROP_LANE)`,
action `sales.mail.stored`, naming the file it came from.

A reader that does not answer (`ReaderUnavailableError`) ends the tick: no
file is marked, and the next tick tries again. A folder that cannot be
listed (the share gone, OneDrive unsynced) also ends the tick, and the same
people are told, at most once a day while it lasts: no new mail reaches DW1
until it is back, and a log line nobody reads is not telling anyone.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Final, Literal, Protocol

from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.application.drop_folder import DropFolderPort, DroppedFile
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor
from dw_platform.domain.messages import InboundMessage
from dw_sales.application.access import SalesScopes
from dw_sales.application.ports import NotificationSenderPort, SalesScope, ScopeHoldersPort

logger = logging.getLogger("dw_sales.mail_drop")

MAIL_DROP_LANE: Final = "sales_mail_drop"
MAIL_STORED: Final = "sales.mail.stored"
# A file modified this recently may still be being written.
SETTLE: Final = timedelta(seconds=30)
# The largest file read: its base64 must fit the reader sandbox's request.
MAX_MAIL_BYTES: Final = 20 * 1024 * 1024
_SUFFIX: Final = ".eml"


@dataclass(frozen=True)
class MailFile:
    """A mail as the reader read it: the message, and each attachment's bytes
    by attachment id, every one held to its description."""

    message: InboundMessage
    contents: Mapping[str, bytes]


@dataclass(frozen=True)
class MailRefused:
    """A file the reader would not read, and why, in words code wrote."""

    reason: str


class MailFileReaderPort(Protocol):
    """Reads one `.eml` file. Raises when the reader cannot answer at all."""

    async def read_mail(self, data: bytes) -> MailFile | MailRefused: ...


class MailStorePort(Protocol):
    """The stored mailbox, as the lane writes it."""

    async def handled_sources(self, scope: SalesScope) -> frozenset[str]:
        """The file names already handled: stored, duplicate or refused."""
        ...

    async def refuse(self, scope: SalesScope, *, source: str, reason: str) -> None:
        """Record that ``source`` was not read, and why; nothing else of it."""
        ...

    async def store(
        self, scope: SalesScope, mail: MailFile, *, source: str, event: AuditEvent
    ) -> bool:
        """The message, its attachments and ``event`` in one transaction.
        False, and nothing written, when the message is already stored: by
        its id, or by its Message-ID from the same sender address."""
        ...


@dataclass(frozen=True)
class DropTick:
    """What one tick did, by file name."""

    stored: tuple[str, ...] = ()
    already_stored: tuple[str, ...] = ()
    refused: tuple[tuple[str, str], ...] = ()
    waiting: int = 0


class MailDropNoticePort(Protocol):
    """Tells the people who process the mailbox what the lane could not do."""

    async def refused(self, scope: SalesScope, *, source: str, reason: str) -> None: ...

    async def unreachable(self, scope: SalesScope, *, day: date) -> None: ...


@dataclass(frozen=True)
class MailDropNotices:
    """`MailDropNoticePort` as in-app notices to every member of the workspace
    who may process its mailbox, read by the function that decides who may.
    Idempotent by key: a file is told once, an unreachable folder once a day."""

    holders: ScopeHoldersPort
    notifications: NotificationSenderPort

    async def refused(self, scope: SalesScope, *, source: str, reason: str) -> None:
        await self._tell(
            scope,
            key=f"sales.mail_drop.refused:{scope.workspace_id.value}:{source}",
            title="Có thư DW1 không đọc được",
            body=(
                f"Tệp {source} trong thư mục thư không được lưu vào DW1, nên thư này "
                f"không có trong Hộp thư. Mở thư gốc trong Outlook và xử lý tay. "
                f"Lý do (cho IT): {reason}."
            ),
        )

    async def unreachable(self, scope: SalesScope, *, day: date) -> None:
        await self._tell(
            scope,
            key=f"sales.mail_drop.unreachable:{scope.workspace_id.value}:{day.isoformat()}",
            title="DW1 không đọc được thư mục thư",
            body=(
                "Thư mới của khách chưa vào DW1 cho tới khi thư mục được nối lại. "
                "Báo IT kiểm tra thư mục đồng bộ trên máy chủ của DW1."
            ),
        )

    async def _tell(self, scope: SalesScope, *, key: str, title: str, body: str) -> None:
        recipients = await self.holders.holding(
            scope.tenant_id.value,
            scope.workspace_id.value,
            frozenset({SalesScopes.INBOX_PROCESS.value}),
        )
        if not recipients:
            # Nobody to tell is itself the failure; the log is all that is left.
            logger.error("sales_mail_drop: no one processes this mailbox to be told %s", key)
            return
        await self.notifications.deliver(
            _lane_context(scope),
            recipients=recipients,
            source_key=key,
            title=title,
            body=body,
            link="/sales/inbox",
        )


def _lane_context(scope: SalesScope) -> AccessContext:
    """The lane delivering in ``scope``: its own actor, no scope at all."""
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(MAIL_DROP_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )


_Outcome = Literal["stored", "already_stored"]
_Taken = _Outcome | Literal["waiting"] | MailRefused


@dataclass
class MailDrop:
    """One drop folder, read into one workspace's stored mailbox."""

    folder: DropFolderPort
    reader: MailFileReaderPort
    store: MailStorePort
    notices: MailDropNoticePort
    clock: UtcClock
    ids: IdGenerator
    max_bytes: int = MAX_MAIL_BYTES
    # The names handled, or refused by this process; None until the first tick.
    _seen: set[str] | None = field(default=None, init=False, repr=False)

    async def tick(self, scope: SalesScope) -> DropTick:
        if self._seen is None:
            self._seen = set(await self.store.handled_sources(scope))
        seen = self._seen
        now = self.clock.now()
        done: dict[_Outcome, list[str]] = {"stored": [], "already_stored": []}
        refused: list[tuple[str, str]] = []
        waiting = 0
        try:
            listed = await self.folder.files()
        except OSError:
            await self.notices.unreachable(scope, day=now.date())
            raise
        for dropped in sorted(listed, key=lambda f: f.name):
            if dropped.name in seen or not dropped.name.lower().endswith(_SUFFIX):
                continue
            taken = (
                "waiting"
                if dropped.size == 0 or now - dropped.modified_at < SETTLE
                else await self._take(scope, dropped)
            )
            if taken == "waiting":
                waiting += 1
                continue
            if isinstance(taken, MailRefused):
                logger.warning("sales_mail_drop: %s not stored: %s", dropped.name, taken.reason)
                # Told before it is marked: a notice that fails leaves the
                # file to the next tick, never marked and untold.
                await self.notices.refused(scope, source=dropped.name, reason=taken.reason)
                await self.store.refuse(scope, source=dropped.name, reason=taken.reason)
                refused.append((dropped.name, taken.reason))
            else:
                done[taken].append(dropped.name)
            seen.add(dropped.name)
        return DropTick(
            stored=tuple(done["stored"]),
            already_stored=tuple(done["already_stored"]),
            refused=tuple(refused),
            waiting=waiting,
        )

    async def _take(self, scope: SalesScope, dropped: DroppedFile) -> _Taken:
        if dropped.size > self.max_bytes:
            return _over(self.max_bytes)
        data = await self.folder.read(dropped, self.max_bytes)
        if not data:
            return "waiting"
        if len(data) > self.max_bytes:
            return _over(self.max_bytes)
        read = await self.reader.read_mail(data)
        if isinstance(read, MailRefused):
            return read
        event = lane_audit_event(
            lane=MAIL_DROP_LANE,
            event_id=self.ids.new_uuid(),
            tenant_id=scope.tenant_id,
            workspace_id=scope.workspace_id,
            action=MAIL_STORED,
            resource_type="sales.message",
            resource_id=read.message.message_id,
            occurred_at=self.clock.now(),
            details={"source": dropped.name, "attachments": len(read.message.attachments)},
        )
        if await self.store.store(scope, read, source=dropped.name, event=event):
            return "stored"
        return "already_stored"


def _over(limit: int) -> MailRefused:
    return MailRefused(f"the file is over {limit // (1024 * 1024)} MB")
