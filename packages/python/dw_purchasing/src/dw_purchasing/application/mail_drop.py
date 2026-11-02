"""DW2 reads real mail from a folder of `.eml` files: the `purchasing_mail_drop`
lane, Purchasing's own queue (ADR 0014 decision 2), written after Sales'
(`dw_sales.application.mail_drop`, ticket 43) without importing it.

A flow exports every mail reaching the purchasing mailbox as an `.eml` file
into a folder the host syncs (`dw_platform.application.drop_folder`). **The
folder is a drop box, not the mailbox**: each tick, this lane reads the files
it has not handled before and stores each message, with its attachments, in
DW2's stored mailbox (`MailStorePort`, `purchasing.mailbox_*`). Everything
else reads the stored mailbox through `InboxPort`, like the mock.

**One tick:**

1. The names already handled are read once per process (`handled_sources`):
   a restart does not read the folder's whole history again.
2. Each `.eml` file not seen yet, oldest name first. A file modified less
   than `SETTLE` ago, or still empty, may be arriving: it waits.
3. A file modified before the mailbox's term (`MailTermPort`, the tenant's
   `retention.mailbox_days`) is not read: its mail would be deleted by the
   next retention pass, and once its name is forgotten with it, reading it
   would bring the mail back. It is not marked either.
4. A file over the size limit, or one the reader refuses (`MailRefused`), is
   recorded as handled with its reason, and whoever receives purchase
   requests (`purchasing.request.intake`) is told which file did not arrive,
   once per file (`MailDropNoticePort.refused`). Told before it is marked: a
   notice that fails leaves the file to the next tick, never marked and
   untold.
5. Every other mail is stored with one audit event, in one transaction
   (`MailStorePort.store`). A copy of a file has the same id (its hash), and
   one mail exported twice carries the same Message-ID from the same
   sender: either is stored once, audited once.

**It audits as itself**: `lane_audit_event` from `system_actor(MAIL_DROP_LANE)`
(ADR 0011), action `purchasing.mail.stored`, naming the file it came from.
**No word of a mail is logged**: a log line names a file and a reason code
wrote, never a subject, a sender or a body.

A reader that does not answer (`InfrastructureError`) ends the tick: no file
is marked, and the next tick tries again. A folder that cannot be listed ends
the tick too, and the same people are told, at most once a day while it lasts.
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
from dw_platform.application.rule_versions import ContextScope
from dw_platform.domain.audit import AuditEvent, lane_audit_event, system_actor
from dw_platform.domain.messages import InboundMessage
from dw_purchasing.application.access import PurchasingScopes
from dw_purchasing.application.ports import NoticesPort
from dw_purchasing.application.rules import PurchasingRuleBook, PurchasingRuleKey
from dw_purchasing.domain.rules import PurchasingRules

logger = logging.getLogger("dw_purchasing.mail_drop")

MAIL_DROP_LANE: Final = "purchasing_mail_drop"
MAIL_STORED: Final = "purchasing.mail.stored"
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
    """Reads one `.eml` file in the reader sandbox. Raises
    `InfrastructureError` when the reader cannot answer at all."""

    async def read_mail(self, data: bytes) -> MailFile | MailRefused: ...


class MailStorePort(Protocol):
    """DW2's stored mailbox, as the lane writes it."""

    async def handled_sources(self, scope: ContextScope) -> frozenset[str]:
        """The file names already handled: stored, duplicate or refused."""
        ...

    async def refuse(self, scope: ContextScope, *, source: str, reason: str) -> None:
        """Record that ``source`` was not read, and why; nothing else of it."""
        ...

    async def store(
        self, scope: ContextScope, mail: MailFile, *, source: str, event: AuditEvent
    ) -> bool:
        """The message, its attachments and ``event`` in one transaction.
        False, and only the file recorded, when the message is already
        stored: by its id, or by its Message-ID from the same sender."""
        ...


class MailTermPort(Protocol):
    async def kept_days(self, scope: ContextScope) -> int | None:
        """How many days stored mail is kept; None where no term is set."""
        ...


@dataclass(frozen=True)
class RulesMailTerm:
    """`MailTermPort` over the tenant's rules in force, the term the
    retention lane deletes by (`RetentionRules.mailbox_term_days`)."""

    book: PurchasingRuleBook

    async def kept_days(self, scope: ContextScope) -> int | None:
        rules = (await self.book.current(scope, PurchasingRuleKey.RULES)).policy
        assert isinstance(rules, PurchasingRules)
        return None if rules.retention is None else rules.retention.mailbox_term_days


class MailDropNoticePort(Protocol):
    """Tells whoever receives purchase requests what the lane could not do."""

    async def refused(self, scope: ContextScope, *, source: str, reason: str) -> None: ...

    async def unreachable(self, scope: ContextScope, *, day: date) -> None: ...


@dataclass(frozen=True)
class MailDropNotices:
    """`MailDropNoticePort` as in-app notices to every member of the workspace
    holding `purchasing.request.intake`, through DW2's `NoticesPort`.
    Idempotent by key: a file is told once, an unreachable folder once a day."""

    notices: NoticesPort

    async def refused(self, scope: ContextScope, *, source: str, reason: str) -> None:
        await self._tell(
            scope,
            key=f"purchasing.mail_drop.refused:{scope.workspace_id.value}:{source}",
            title="Có thư DW2 không đọc được",
            body=(
                f"Tệp {source} trong thư mục thư không được lưu vào DW2, nên thư này "
                f"không có trong Hộp thư Mua hàng. Mở thư gốc trong Outlook và xử lý tay. "
                f"Lý do (cho IT): {reason}."
            ),
        )

    async def unreachable(self, scope: ContextScope, *, day: date) -> None:
        await self._tell(
            scope,
            key=f"purchasing.mail_drop.unreachable:{scope.workspace_id.value}:{day.isoformat()}",
            title="DW2 không đọc được thư mục thư",
            body=(
                "Thư mới gửi phòng Mua hàng chưa vào DW2 cho tới khi thư mục được nối "
                "lại. Báo IT kiểm tra thư mục đồng bộ trên máy chủ của DW2."
            ),
        )

    async def _tell(self, scope: ContextScope, *, key: str, title: str, body: str) -> None:
        await self.notices.tell(
            _lane_context(scope),
            scopes=frozenset({PurchasingScopes.REQUEST_INTAKE.value}),
            source_key=key,
            title=title,
            body=body,
            link="/purchasing/mail",
        )


def _lane_context(scope: ContextScope) -> AccessContext:
    """The lane delivering in ``scope``: its own actor, no scope at all."""
    return AccessContext(
        tenant_id=scope.tenant_id.value,
        workspace_id=scope.workspace_id.value,
        principal_id=system_actor(MAIL_DROP_LANE).value,
        roles=frozenset(),
        scopes=frozenset(),
        plan_id="background",
    )


@dataclass(frozen=True)
class DropTick:
    """What one tick did, by file name."""

    stored: tuple[str, ...] = ()
    already_stored: tuple[str, ...] = ()
    refused: tuple[tuple[str, str], ...] = ()
    waiting: int = 0
    expired: int = 0


_Outcome = Literal["stored", "already_stored"]


@dataclass
class MailDrop:
    """One drop folder, read into one workspace's stored mailbox."""

    folder: DropFolderPort
    reader: MailFileReaderPort
    store: MailStorePort
    term: MailTermPort
    notices: MailDropNoticePort
    clock: UtcClock
    ids: IdGenerator
    max_bytes: int = MAX_MAIL_BYTES
    # The names handled, or refused by this process; None until the first tick.
    _seen: set[str] | None = field(default=None, init=False, repr=False)

    async def tick(self, scope: ContextScope) -> DropTick:
        if self._seen is None:
            self._seen = set(await self.store.handled_sources(scope))
        seen = self._seen
        now = self.clock.now()
        days = await self.term.kept_days(scope)
        oldest = None if days is None else now - timedelta(days=days)
        done: dict[_Outcome, list[str]] = {"stored": [], "already_stored": []}
        refused: list[tuple[str, str]] = []
        waiting = expired = 0
        try:
            listed = await self.folder.files()
        except OSError:
            await self.notices.unreachable(scope, day=now.date())
            raise
        for dropped in sorted(listed, key=lambda f: f.name):
            if dropped.name in seen or not dropped.name.lower().endswith(_SUFFIX):
                continue
            if oldest is not None and dropped.modified_at < oldest:
                expired += 1
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
                logger.warning(
                    "purchasing_mail_drop: %s not stored: %s", dropped.name, taken.reason
                )
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
            expired=expired,
        )

    async def _take(
        self, scope: ContextScope, dropped: DroppedFile
    ) -> _Outcome | Literal["waiting"] | MailRefused:
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
            resource_type="purchasing.message",
            resource_id=read.message.message_id,
            occurred_at=self.clock.now(),
            details={"source": dropped.name, "attachments": len(read.message.attachments)},
        )
        if await self.store.store(scope, read, source=dropped.name, event=event):
            return "stored"
        return "already_stored"


def _over(limit: int) -> MailRefused:
    return MailRefused(f"the file is over {limit // (1024 * 1024)} MB")
