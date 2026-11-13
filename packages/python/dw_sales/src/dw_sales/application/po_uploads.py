""" "Tải PO lên": a PO file Sales downloaded, stored as one message (ticket 18).

A customer that sends no PO by mail puts it on its own portal, and DW never
logs into a customer's portal (Đạt, 11-13): a person downloads the file and
uploads it here, choosing the customer it is for. Forwarding it to themselves
would not do: a mail from an internal address names no customer.

**One upload is one stored message**, in the stored mailbox every screen and
lane reads (`UploadStorePort`), so it takes the road every mail takes: the
malware scan and the name check at the mailbox's door, the reader sandbox, the
processing job and its disposition. Its sender is the uploader's own sign-in
address, resolved here from the verified context (never a field of the
request), its subject names the files, and it has no body.

**The customer is a person's choice, stamped by the server.** The code the
caller picked must be a customer of this tenant's master data, or the upload
is refused. The store writes it, with who chose it, beside the message
(`PoUpload`, read back by `UploadLookupPort`), never inside anything the
message carries: a mail can never claim to be an upload. Intake then takes
that customer instead of looking up the sender (`OrderIntake.customer_of`).
The audit event names the person as its actor, with the customer they chose.

**The same files uploaded twice are stored once.** The message's id is the
hash of its files' hashes, so a second upload of the same file finds the first
(`already_stored`) and queues nothing new; the mailbox dedupes mail by its
file's hash the same way.

**Bounded by the caps mail is bounded by**: each file by the tenant's order
rules (`IntakeCaps.max_attachment_bytes`), the whole by the largest mail the
drop lane reads (`MAX_MAIL_BYTES`), and at most `MAX_UPLOAD_FILES` files.

Uploading needs what processing the mailbox needs (`sales.inbox.process`):
the upload is queued for processing at once, as the caller, exactly as if
they had pressed "DW xử lý" on a mail (refused while DW1 is paused).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

from pydantic import BaseModel, ConfigDict, ValidationError

from dw_kernel.errors import ConflictError, DomainError, NotFoundError
from dw_kernel.ids import TenantId, UserId, WorkspaceId
from dw_kernel.ports import IdGenerator, UtcClock
from dw_platform.application.access_context import AccessContext
from dw_platform.domain.audit import AuditEvent
from dw_platform.domain.messages import Attachment, EmailAddress, InboundMessage
from dw_sales.application.access import Gate, SalesScopes, sales_scope
from dw_sales.application.case_store import SalesUnitOfWorkFactory
from dw_sales.application.inbox_service import own_address
from dw_sales.application.mail_drop import MAX_MAIL_BYTES, MailFile
from dw_sales.application.order_ports import OrderRulesPort, PoUpload, UploadLookupPort
from dw_sales.application.ports import MemberDirectoryPort, SalesCatalogPort, SalesScope
from dw_sales.application.processing import ProcessingService
from dw_sales.application.views import ProcessingJobView
from dw_sales.application.worker_service import require_running

# What an uploaded message's id starts with; the rest is its files' hash. A
# stored row is an upload exactly when its id does (`ck_mailbox_messages_upload`).
UPLOAD_PREFIX: Final = "upload-"
# How many files one upload holds: a portal's export and its print, a few POs.
MAX_UPLOAD_FILES: Final = 10
PO_UPLOADED: Final = "sales.po.uploaded"
# The sender's declared type is no fact DW1 reads (formats sniff the bytes).
_MEDIA_TYPE: Final = "application/octet-stream"
_SUBJECT: Final = "Tải PO lên: "


@dataclass(frozen=True, slots=True)
class UploadedFile:
    """One file as the caller sent it: its name and its bytes."""

    name: str
    data: bytes


class UploadStorePort(UploadLookupPort, Protocol):
    """The stored mailbox, as an upload writes it and reads its stamp back."""

    async def store_upload(
        self, scope: SalesScope, mail: MailFile, upload: PoUpload, *, event: AuditEvent
    ) -> bool:
        """The message, its files, who uploaded it for which customer, and
        ``event``, in one transaction. False, and nothing written, when a
        message of that id is already stored."""
        ...


class PoUploadView(BaseModel):
    """What one upload did: the message it is, whether it was stored now or
    already, and its processing job when one was queued."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    customer_code: str
    already_stored: bool
    job: ProcessingJobView | None


@dataclass(frozen=True)
class PoUploads:
    """ "Tải PO lên" (module docstring)."""

    uow: SalesUnitOfWorkFactory
    gate: Gate
    clock: UtcClock
    ids: IdGenerator
    catalog: SalesCatalogPort
    rules: OrderRulesPort
    directory: MemberDirectoryPort
    store: UploadStorePort
    queue: ProcessingService

    async def upload(
        self, context: AccessContext, customer_code: str, files: Sequence[UploadedFile]
    ) -> PoUploadView:
        await self.gate.require(context, SalesScopes.INBOX_PROCESS, resource_type="sales_message")
        scope = sales_scope(context)
        customer = (await self.catalog.customer_by_code(scope, customer_code)).data
        if customer is None:
            # Another tenant's customer reads as none, as any unknown code.
            raise NotFoundError(
                "khách hàng không có trong dữ liệu chủ", details={"customer_code": customer_code}
            )
        caps = (await self.rules.rules(scope)).intake
        _within_caps(files, caps.max_attachment_bytes)
        sender = await own_address(self.directory, context)
        if sender is None:
            raise ConflictError(
                "tài khoản của bạn chưa có địa chỉ thư: DW1 ghi người tải lên bằng địa chỉ đó",
                details={"rule": "no_mailbox"},
            )
        async with self.uow(scope) as work:
            await require_running(work)
        mail = upload_message(files, sender, self.clock.now())
        upload = PoUpload(customer_code=customer.code, uploaded_by=context.principal_id)
        event = AuditEvent(
            id=self.ids.new_uuid(),
            tenant_id=TenantId(context.tenant_id),
            workspace_id=WorkspaceId(context.workspace_id),
            actor_id=UserId(context.principal_id),
            action=PO_UPLOADED,
            resource_type="sales_message",
            resource_id=mail.message.message_id,
            occurred_at=self.clock.now(),
            # Ids, a code and a count: never a file's name or bytes.
            details={"customer_code": customer.code, "files": len(files)},
        )
        message_id = mail.message.message_id
        if not await self.store.store_upload(scope, mail, upload, event=event):
            # The customer stamped when it was first stored stands.
            first = await self.store.upload_of(scope, message_id)
            return PoUploadView(
                message_id=message_id,
                customer_code=first.customer_code if first is not None else customer.code,
                already_stored=True,
                job=None,
            )
        job = await self.queue.enqueue(context, message_id)
        return PoUploadView(
            message_id=message_id,
            customer_code=customer.code,
            already_stored=False,
            job=job,
        )


def _within_caps(files: Sequence[UploadedFile], max_file_bytes: int) -> None:
    if not files:
        raise DomainError("chọn ít nhất một tệp", details={"rule": "no_file"})
    if len(files) > MAX_UPLOAD_FILES:
        raise DomainError(
            f"tải lên tối đa {MAX_UPLOAD_FILES} tệp một lần", details={"rule": "too_many_files"}
        )
    if any(len(f.data) > max_file_bytes for f in files):
        raise DomainError(
            f"mỗi tệp tối đa {max_file_bytes // 1_000_000} MB", details={"rule": "file_too_large"}
        )
    if sum(len(f.data) for f in files) > MAX_MAIL_BYTES:
        raise DomainError(
            f"cả lần tải tối đa {MAX_MAIL_BYTES // (1024 * 1024)} MB",
            details={"rule": "upload_too_large"},
        )


def upload_id(files: Sequence[UploadedFile]) -> str:
    """The message id of an upload of ``files``: the hash of their hashes, in
    any order, so the same files uploaded again are the same message."""
    digests = sorted(hashlib.sha256(f.data).hexdigest() for f in files)
    return UPLOAD_PREFIX + hashlib.sha256("\n".join(digests).encode("ascii")).hexdigest()


def upload_message(files: Sequence[UploadedFile], sender: str, at: datetime) -> MailFile:
    """The upload as the stored mailbox holds a mail: a message naming its
    files, and each file's bytes by attachment id. A name a mail's could not
    be (a path, a control character) is refused, naming no byte of it."""
    attachments: list[Attachment] = []
    contents: dict[str, bytes] = {}
    for index, file in enumerate(files, start=1):
        attachment_id = f"A{index}"
        try:
            attachment = Attachment(
                attachment_id=attachment_id,
                name=file.name,
                media_type=_MEDIA_TYPE,
                size=len(file.data),
                sha256=hashlib.sha256(file.data).hexdigest(),
            )
        except ValidationError:
            raise DomainError(
                f"tên tệp thứ {index} không dùng được", details={"rule": "file_name"}
            ) from None
        attachments.append(attachment)
        contents[attachment_id] = file.data
    names = ", ".join(a.name for a in attachments)
    message = InboundMessage.model_validate(
        {
            "message_id": upload_id(files),
            "sender": EmailAddress(address=sender),
            "subject": (_SUBJECT + names)[:998],
            "received_at": at,
            "body_text": "",
            "attachments": attachments,
        }
    )
    return MailFile(message=message, contents=contents)
