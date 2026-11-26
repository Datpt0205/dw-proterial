import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, order } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];

let SCOPES = ["sales.case.read", "sales.order.prepare"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => SCOPES.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

const api = {
  pcRequest: vi.fn(async () => ({
    case_version: 1,
    lines: [1],
    subject: "[Hỏi PC] Ngày giao cho PO BRN-PO-1",
    body: "Chào anh/chị PC,\n- Dòng 1: 6.100 m",
    template_ref: "sales_handoffs@1.1.0#pc_request",
    reminder_at: "2026-11-16T02:00:00Z",
  })),
  recordPcAsked: vi.fn(async () => ({ case_id: "c", case_version: 2 })),
  recordPcAnswer: vi.fn(async () => ({ case_id: "c", case_version: 2 })),
  pcReplyMail: vi.fn(async () => ({
    message_id: "PC01",
    sender: "pc@proterial.example",
    subject: "Re: ngày giao BRN-PO-1",
    received_at: "2026-11-15T03:00:00Z",
    text: "Dòng 1 giao được ngày 30/11/2026.",
  })),
  acceptPcReply: vi.fn(async () => ({ case_id: "c", case_version: 3 })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { PcRequestPanel } from "../../orders/[caseId]/pc-request";

function page(shown: Order) {
  return render(
    <UiProvider>
      <PcRequestPanel
        order={shown}
        viewer={{
          principalId: AN,
          hasScope: (s: string) => SCOPES.includes(s),
        }}
        onChanged={vi.fn()}
      />
    </UiProvider>,
  );
}

function button(name: string): HTMLButtonElement {
  return screen
    .getByText(name, { selector: "button span" })
    .closest("button") as HTMLButtonElement;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  SCOPES = ["sales.case.read", "sales.order.prepare"];
});

describe("Hỏi PC (ticket 07)", () => {
  it("shows the request DW1 drafted, the wait and when DW1 reminds", async () => {
    page(
      order({
        status: "in_review",
        pc_request: { lines: [1], by: AN, at: "2026-11-15T02:00:00Z" },
      }),
    );
    expect(await screen.findByText(/Ngày giao cho PO BRN-PO-1/)).toBeTruthy();
    expect(screen.getByText("Chờ PC trả ngày")).toBeTruthy();
    expect(screen.getByText(/DW1 nhắc lúc/)).toBeTruthy();
    // Ticket 77: the same request goes from DW1 as a draft to PC's mailbox.
    expect(
      screen.getByText(/Thư hỏi PC ngày giao \(nháp\)”.*DW1 tự ghi đã hỏi PC/s),
    ).toBeTruthy();
    fireEvent.click(button("Ghi đã hỏi PC"));
    await waitFor(() =>
      expect(api.recordPcAsked).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Number),
        expect.any(String),
      ),
    );
  });

  it("says why PC is not asked once the order is in Bravo", async () => {
    const line = order().lines[0]!;
    page(
      order({
        status: "uploaded_to_bravo",
        lines: [
          {
            ...line,
            pc_answer: {
              deliveries: [
                {
                  quantity: "6100",
                  first_date: "2026-11-20",
                  date: "2026-12-05",
                },
              ],
              by: AN,
              at: "2026-11-15T02:00:00Z",
            },
          },
        ],
      }),
    );
    expect(button("Ghi đã hỏi PC").disabled).toBe(true);
    expect(screen.queryByText(/DW1 tự ghi đã hỏi PC/)).toBeNull();
    expect(
      screen.getByText(/Chỉ hỏi và ghi ngày PC khi đơn đang xem xét/),
    ).toBeTruthy();
    // The first date PC gave stays beside the current one.
    expect(screen.getByText(/20\/11\/2026 → 05\/12\/2026/)).toBeTruthy();
  });

  it("opens one line's answer, a delivery per row of PC's split", async () => {
    page(order({ status: "in_review" }));
    fireEvent.click(button("Ghi ngày PC"));
    fireEvent.click(await screen.findByText("Thêm một đợt"));
    expect(await screen.findByText("Số lượng đợt 2")).toBeTruthy();
    expect(screen.getByText(/Tổng các đợt/)).toBeTruthy();
  });
});

describe("PC's mail read by DW1 (ticket 77)", () => {
  const proposed = () =>
    order({
      status: "in_review",
      pc_request: { lines: [1], by: AN, at: "2026-11-15T02:00:00Z" },
      pc_reply: {
        dates: [
          {
            line_no: 1,
            delivery: 1,
            date: "2026-11-30",
            quote: "30/11/2026",
            message_id: "PC01",
            received_at: "2026-11-15T03:00:00Z",
          },
        ],
        read_at: "2026-11-15T03:05:00Z",
        prompt_ref: "sales.pc_dates@1.0.0",
      },
    });

  it("shows the date as the machine's, and Đúng waits until the mail is opened", async () => {
    page(proposed());
    // The glossary's value state, drawn as every machine-read value is.
    expect(await screen.findByText("Máy đọc")).toBeTruthy();
    expect(
      screen.getByText(/30\/11\/2026 · trong thư: “30\/11\/2026”/),
    ).toBeTruthy();
    const dung = () =>
      screen.getByLabelText("Đúng ngày PC cho dòng 1") as HTMLButtonElement;
    expect(dung().disabled).toBe(true);
    expect(screen.getByText("Mở thư PC trước khi bấm Đúng.")).toBeTruthy();
    expect(api.acceptPcReply).not.toHaveBeenCalled();

    fireEvent.click(screen.getByLabelText("Xem thư PC cho dòng 1"));
    expect(
      await screen.findByText("Dòng 1 giao được ngày 30/11/2026."),
    ).toBeTruthy();
    expect(api.pcReplyMail).toHaveBeenCalledWith(expect.any(String), "PC01");
    await waitFor(() => expect(dung().disabled).toBe(false));
    fireEvent.click(dung());
    await waitFor(() =>
      expect(api.acceptPcReply).toHaveBeenCalledWith(
        expect.any(String),
        1,
        expect.any(Number),
        expect.any(String),
      ),
    );
  });

  it("keeps PC's mail closed, with the reason, to a viewer who cannot prepare", async () => {
    SCOPES = ["sales.case.read"];
    page(proposed());
    const open = (await screen.findByLabelText(
      "Xem thư PC cho dòng 1",
    )) as HTMLButtonElement;
    expect(open.disabled).toBe(true);
    fireEvent.click(open);
    expect(api.pcReplyMail).not.toHaveBeenCalled();
    expect(
      screen.getAllByText(/cần vai Sales phụ trách/).length,
    ).toBeGreaterThan(0);
  });

  it("opens Sửa as the answer form filled with DW1's reading", async () => {
    page(proposed());
    fireEvent.click(await screen.findByLabelText("Sửa ngày PC cho dòng 1"));
    expect(await screen.findByText("Ngày PC trả lời cho dòng 1")).toBeTruthy();
    expect(screen.getByDisplayValue("30/11/2026")).toBeTruthy();
  });

  it("shows no reading where DW1 read none", async () => {
    page(order({ status: "in_review" }));
    await screen.findByText("Hỏi PC ngày giao");
    expect(screen.queryByText("Máy đọc")).toBeNull();
  });
});
