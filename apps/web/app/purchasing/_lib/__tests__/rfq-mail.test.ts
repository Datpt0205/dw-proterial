// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { PurchaseRfqMail } from "@dw/api-client";
import { sendBlocked } from "../rfq-mail";

function mail(status: PurchaseRfqMail["status"]): PurchaseRfqMail {
  return {
    mail_id: "m",
    supplier_code: "NCC-A",
    mailbox: "buyer@alpha.local",
    status,
    error: status === "failed" ? "flow_failed" : null,
    queued_by: "u",
    queued_at: "2026-11-03T00:00:00Z",
    settled_at: null,
  };
}

describe("Gửi từ hộp thư của tôi", () => {
  it("says why it cannot be pressed", () => {
    expect(
      sendBlocked({ may: false, pending: false, mail: undefined }),
    ).toMatch(/người mua/);
    expect(sendBlocked({ may: true, pending: true, mail: undefined })).toMatch(
      /chưa có nội dung/,
    );
    expect(
      sendBlocked({ may: true, pending: false, mail: mail("written") }),
    ).toMatch(/đang được gửi/);
    expect(
      sendBlocked({ may: true, pending: false, mail: mail("sent") }),
    ).toMatch(/đã gửi/);
  });

  it("may be pressed again once a mail failed or stalled", () => {
    expect(
      sendBlocked({ may: true, pending: false, mail: mail("failed") }),
    ).toBeNull();
    expect(
      sendBlocked({ may: true, pending: false, mail: mail("stalled") }),
    ).toBeNull();
    expect(
      sendBlocked({ may: true, pending: false, mail: undefined }),
    ).toBeNull();
  });
});
