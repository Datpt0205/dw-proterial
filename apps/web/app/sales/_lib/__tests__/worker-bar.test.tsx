import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

/**
 * The DW1 bar says what DW1 is doing, never a bare "đang chạy" (Đạt,
 * 2026-10-21): the mail it is reading, how far through the mailbox it is,
 * and that it waits for new mail once nothing is left.
 */
const GIANG = "00000000-0000-4000-8000-0000000000c1";
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: GIANG,
    displayName: "Giang",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) =>
      ["sales.overview.read", "sales.case.read"].includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

const message = (
  id: string,
  subject: string,
  status: string | null,
  processed_at: string | null,
) => ({
  message_id: id,
  subject,
  sender: "x@example.com",
  received_at: "2026-10-20T01:00:00Z",
  attachments: [],
  sender_verified: true,
  disposition: {
    kind: processed_at ? "case_created" : "not_yet_processed",
    processed_at,
  },
  processing: status ? { status, attempts: 1, error: null } : null,
});

let inbox: unknown[] = [];
const api = {
  overview: vi.fn(async () => ({
    worker: { paused: false, changed_by: null, changed_at: null, reason: null },
  })),
  inbox: vi.fn(async () => inbox),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { SalesFrameProvider } from "../../_components/sales-frame";

function bar() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <div />
      </SalesFrameProvider>
    </UiProvider>,
  );
}

afterEach(() => cleanup());

describe("the DW1 bar", () => {
  it("names the mail DW1 is reading and how far it is", async () => {
    inbox = [
      message("M17", "Xin hàng mẫu cáp 2 lõi", "running", null),
      message("M18", "Đơn đặt hàng 2", "queued", null),
      message("M01", "Đơn đặt hàng 1", "done", "2026-10-20T02:00:00Z"),
    ];
    bar();
    expect(
      await screen.findByText("DW1 đang đọc “Xin hàng mẫu cáp 2 lõi”"),
    ).toBeTruthy();
    expect(
      screen.getByText(/đã xử lý 1\/3 thư · 1 thư đang chờ · thư gần nhất lúc/),
    ).toBeTruthy();
    expect(screen.queryByText(/DW1 đang chạy/)).toBeNull();
  }, 20_000);

  it("says it waits for new mail once the mailbox is done", async () => {
    inbox = [message("M01", "Đơn đặt hàng 1", "done", "2026-10-20T02:00:00Z")];
    bar();
    expect(
      await screen.findByText("DW1 đã xử lý hết thư, đang chờ thư mới"),
    ).toBeTruthy();
    expect(screen.getByText(/đã xử lý 1\/1 thư/)).toBeTruthy();
  }, 20_000);
});
