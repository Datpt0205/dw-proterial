import type { PurchaseRfqMail } from "@dw/api-client";
import type { StatusTone } from "@dw/ui";

/** A sent RFQ's status in words (`RfqMail.status`). */
export const MAIL_STATUS: Record<
  PurchaseRfqMail["status"],
  { label: string; tone: StatusTone }
> = {
  queued: { label: "Đang chuyển sang hộp thư", tone: "pri" },
  written: { label: "Chờ luồng gửi", tone: "pri" },
  sent: { label: "Đã gửi", tone: "ok" },
  failed: { label: "Không gửi được", tone: "err" },
  stalled: { label: "Chưa có xác nhận gửi", tone: "warn" },
};

/** Why a mail did not go, in words (`RfqMail.error`). */
export const MAIL_ERROR: Record<
  NonNullable<PurchaseRfqMail["error"]>,
  string
> = {
  not_connected: "bạn chưa có thư mục gửi thư (nhờ quản trị cài luồng)",
  flow_failed: "luồng gửi thư báo lỗi, thử gửi lại",
  no_receipt: "kiểm tra thư mục Đã gửi trong Outlook trước khi gửi lại",
};

/** Why "Gửi từ hộp thư của tôi" cannot be pressed, in words; null when it can. */
export function sendBlocked({
  may,
  pending,
  mail,
}: {
  may: boolean;
  pending: boolean;
  mail: PurchaseRfqMail | undefined;
}): string | null {
  if (!may) return "Chỉ người mua phụ trách hỏi giá gửi được thư ở bước này.";
  if (pending) return "Thư chưa có nội dung: viết thư trước rồi gửi.";
  if (mail?.status === "sent") return "Thư đã gửi từ hộp thư của bạn.";
  if (mail && (mail.status === "queued" || mail.status === "written"))
    return "Thư đang được gửi.";
  return null;
}
