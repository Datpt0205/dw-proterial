import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";

type Message = SalesSchemas["InboxMessageView"];
type Card = NonNullable<SalesSchemas["MessageDispositionView"]["triage"]>;

let scopes = ["sales.case.read", "sales.inbox.process"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    email: "an.nguyen@alpha.local",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

const decideTriageCard = vi.fn();
const skills = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ decideTriageCard, skills }),
}));

import { TriageCardPanel } from "../../inbox/triage-card";

const CARD: Card = {
  kind: "reply_to_case",
  kind_label: null,
  routed_as: "reply_to_case",
  step: "reply_to_case",
  case: { case_kind: "order", case_id: "c-1", number: "VLX-PO-2608-0102" },
  skill: "sales_skill_mail_kinds@1.0.0",
  decided: null,
};

function message(card: Card, owner = "an.nguyen@alpha.local"): Message {
  return {
    message_id: "M31",
    sender: "an.trinh@velatrix.example",
    sender_name: "Velatrix",
    subject: "Phiếu nhập kho",
    received_at: "2026-11-16T03:00:00Z",
    body_text: "Bên em nhận đủ hàng",
    attachments: [],
    sender_verified: true,
    disposition: {
      kind: "routed_to_sales",
      reason: "other",
      owner,
      processed_at: "2026-11-16T03:05:00Z",
      thread_cases: [],
      outgoing: false,
      order_cases: [],
      triage: card,
    },
    handoff_draft: null,
    processing: null,
  };
}

afterEach(() => {
  cleanup();
  decideTriageCard.mockReset();
  skills.mockReset();
  scopes = ["sales.case.read", "sales.inbox.process"];
});

function renderIt(m: Message, onChanged = vi.fn()) {
  render(
    <UiProvider>
      <TriageCardPanel message={m} onChanged={onChanged} />
    </UiProvider>,
  );
  return onChanged;
}

describe("Thẻ gợi ý: a mail routed 'Khác' (ticket 33)", () => {
  it("says it is DW1's suggestion, links the case, and takes the step", async () => {
    decideTriageCard.mockResolvedValue({ kind: "attached_to_case" });
    const onChanged = renderIt(message(CARD));

    expect(screen.getByText("DW1 gợi ý")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "PO VLX-PO-2608-0102" }),
    ).toHaveProperty("href", expect.stringContaining("/sales/orders/c-1"));
    fireEvent.click(
      screen.getByRole("button", { name: "Làm theo gợi ý cho thư M31" }),
    );

    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
    // The request names a step and "attach", never a case id.
    expect(decideTriageCard).toHaveBeenCalledWith(
      "M31",
      { step: "reply_to_case", attach: true },
      expect.any(String),
    );
  });

  it("dismisses without a step", async () => {
    decideTriageCard.mockResolvedValue({ kind: "routed_to_sales" });
    const onChanged = renderIt(message(CARD));
    fireEvent.click(screen.getByRole("button", { name: "Bỏ qua gợi ý" }));
    await vi.waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(decideTriageCard).toHaveBeenCalledWith(
      "M31",
      { step: null, attach: false },
      expect.any(String),
    );
  });

  it("disables every decision, with the reason, on someone else's mail", () => {
    renderIt(message(CARD, "dieu.hoang@alpha.local"));
    const take = screen.getByRole("button", {
      name: "Làm theo gợi ý cho thư M31",
    });
    expect(take).toHaveProperty("disabled", true);
    fireEvent.click(take);
    expect(decideTriageCard).not.toHaveBeenCalled();
    expect(
      screen.getByText(
        "Thư này giao cho người khác: người phụ trách hoặc trưởng nhóm quyết.",
      ),
    ).toBeTruthy();
  });

  it("shows a decided card's decision and no buttons", () => {
    renderIt(
      message({
        ...CARD,
        decided: {
          decision: "changed",
          step: "complaint",
          case_id: null,
          by: AN,
          at: "2026-11-16T04:00:00Z",
        },
      }),
    );
    expect(screen.getByText(/Đã chọn bước khác: Khiếu nại/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Bỏ qua gợi ý" })).toBeNull();
  });

  it("offers teaching the kind only to whoever proposes rules (ticket 34)", () => {
    renderIt(message(CARD));
    expect(
      screen.queryByRole("button", { name: "Dạy DW1 loại thư này" }),
    ).toBeNull();
    cleanup();
    scopes = [...scopes, "sales.rules.propose"];
    renderIt(message(CARD));
    expect(
      screen.getByRole("button", { name: "Dạy DW1 loại thư này" }),
    ).toBeTruthy();
  });
});
