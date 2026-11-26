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
type Reply = SalesSchemas["CaseReplyView"];

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
  recordAgreement: vi.fn(async () => ({ case_id: "c", case_version: 9 })),
  recordDecline: vi.fn(async () => ({ case_id: "c", case_version: 9 })),
  undoImpliedAgreement: vi.fn(async () => ({ case_id: "c", case_version: 10 })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { AgreementPanel } from "../../orders/[caseId]/agreement";

const SENT = {
  sent_at: "2026-11-02T03:00:00Z",
  message_id: null,
  term: null,
  implied_from: null,
};

function reply(proposal: Reply["proposal"], quote: string): Reply {
  return {
    message_id: "R1",
    processed_at: "2026-11-03T03:00:00Z",
    linked_to: "<po@mail.example>",
    outcome: "read",
    intents: [
      {
        intent: proposal === "record_accepted" ? "accepts" : "rejects",
        quotes: [quote],
      },
    ],
    prompt: "sales.reply_intent@2.0.0",
    proposal,
    picked_by: null,
  };
}

function page(shown: Order) {
  return render(
    <UiProvider>
      <AgreementPanel
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

describe("Khách xác nhận đơn (ticket 28)", () => {
  it("draws nothing before the confirmation left", () => {
    const { container } = page(order({ status: "cross_checked" }));
    expect(container.textContent).toBe("");
  });

  it("waits on the customer; silence is refused for a customer with no days", () => {
    page(order({ status: "confirmation_sent", confirmation: SENT }));
    expect(screen.getByText("Đã gửi xác nhận, chờ khách")).toBeTruthy();
    expect(button("Khách đã đồng ý").disabled).toBe(false);
    expect(button("Khách từ chối").disabled).toBe(false);
    expect(button("Khách im lặng quá hạn → ghi đồng ý ngầm").disabled).toBe(
      true,
    );
  });

  it("refuses silence before the customer's days have passed", () => {
    page(
      order({
        status: "confirmation_sent",
        confirmation: {
          ...SENT,
          term: { days: 5, day_count: "business", counted_from: "po_date" },
          implied_from: "2999-01-01T00:00:00Z",
        },
      }),
    );
    expect(button("Khách im lặng quá hạn → ghi đồng ý ngầm").disabled).toBe(
      true,
    );
    expect(screen.getByText(/Chưa hết hạn/)).toBeTruthy();
  });

  it("records silence once the days have passed", async () => {
    page(
      order({
        status: "confirmation_sent",
        confirmation: {
          ...SENT,
          term: {
            days: 3,
            day_count: "calendar",
            counted_from: "confirmation_sent",
          },
          implied_from: "2026-01-01T00:00:00Z",
        },
      }),
    );
    fireEvent.click(button("Khách im lặng quá hạn → ghi đồng ý ngầm"));
    fireEvent.click(
      await screen.findByRole("button", { name: "Ghi đồng ý ngầm" }),
    );
    await waitFor(() =>
      expect(api.recordAgreement).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ how: "implied" }),
        expect.any(String),
      ),
    );
  });

  it("marks an accepting reply's proposal with its quote and records it from that mail", async () => {
    page(
      order({
        status: "confirmation_sent",
        confirmation: SENT,
        replies: [reply("record_accepted", "We accept the confirmation.")],
      }),
    );
    expect(screen.getByText("Đề xuất từ luồng thư")).toBeTruthy();
    expect(
      screen.getAllByText(/We accept the confirmation\./).length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Xem trong thư").length).toBeGreaterThan(0);
    // Proposed only: nothing is recorded until the person presses.
    expect(api.recordAgreement).not.toHaveBeenCalled();
    fireEvent.click(button("Khách đã đồng ý"));
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "Khách đã đồng ý" }).length,
      ).toBe(2),
    );
    const [, ok] = screen.getAllByRole("button", { name: "Khách đã đồng ý" });
    fireEvent.click(ok!);
    await waitFor(() =>
      expect(api.recordAgreement).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({ how: "accepted", message_id: "R1" }),
        expect.any(String),
      ),
    );
  });

  it("disables every answer without the prepare scope or while a change runs", () => {
    SCOPES = ["sales.case.read"];
    page(order({ status: "confirmation_sent", confirmation: SENT }));
    expect(button("Khách đã đồng ý").disabled).toBe(true);
    expect(button("Khách từ chối").disabled).toBe(true);
    cleanup();
    SCOPES = ["sales.case.read", "sales.order.prepare"];
    page(
      order({
        status: "confirmation_sent",
        confirmation: SENT,
        update_loop: { step: "ask_pc" } as never,
      }),
    );
    expect(button("Khách đã đồng ý").disabled).toBe(true);
    expect(
      screen.getAllByText(/Khách đang xin thay đổi đơn/).length,
    ).toBeGreaterThan(0);
  });

  it("says how the customer agreed once recorded, with no button left", () => {
    page(
      order({
        status: "confirmed",
        confirmation: SENT,
        agreement: {
          how: "implied",
          by: AN,
          at: "2026-11-06T03:00:00Z",
          message_id: null,
          quotes: [],
        },
      }),
    );
    expect(screen.getByText("Khách im lặng quá hạn: đồng ý ngầm")).toBeTruthy();
    expect(screen.queryByText("Khách từ chối")).toBeNull();
  });

  it("takes an agreement by silence back with one confirmed press (ticket 82)", async () => {
    page(
      order({
        status: "confirmed",
        confirmation: SENT,
        agreement: {
          how: "implied",
          by: AN,
          at: "2026-11-06T03:00:00Z",
          message_id: null,
          quotes: [],
        },
      }),
    );
    fireEvent.click(button("Hoàn tác"));
    expect(api.undoImpliedAgreement).not.toHaveBeenCalled();
    fireEvent.click(
      await screen.findByRole("button", { name: "Hoàn tác đồng ý ngầm" }),
    );
    await waitFor(() =>
      expect(api.undoImpliedAgreement).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Number),
        expect.any(String),
      ),
    );
  });

  it("never offers to undo a customer's own words", () => {
    page(
      order({
        status: "confirmed",
        confirmation: SENT,
        agreement: {
          how: "accepted",
          by: AN,
          at: "2026-11-06T03:00:00Z",
          message_id: null,
          quotes: [],
        },
      }),
    );
    expect(screen.queryByText("Hoàn tác")).toBeNull();
  });
});
