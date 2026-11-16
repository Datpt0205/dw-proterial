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

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

const api = {
  designRequest: vi.fn(async () => ({
    case_version: 1,
    line_no: 1,
    to: ["design@seller.example"],
    subject: "[Đề nghị tạo mã] PO BRN-PO-1 dòng 1",
    body: "Chào anh/chị Design,\n- CB-2018: MULTI-CORE CABLE",
    template_ref: "sales_handoffs@1.2.0#design_request",
    nearest: [{ code: "CB-2018", description: "MULTI-CORE CABLE" }],
    named: [
      {
        code: "CB-2010",
        description: "MULTI-CORE CABLE 2C",
        message_id: "D1",
        sender: "design@seller.example",
        subject: "RE: [Đề nghị tạo mã]",
        received_at: "2026-11-16T04:00:00Z",
      },
    ],
  })),
  recordDesignAsked: vi.fn(async () => ({ case_id: "c", case_version: 2 })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { DesignRequestPanel } from "../../orders/[caseId]/design-request";

function button(name: string | RegExp): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

function page(shown: Order, onUse = vi.fn()) {
  render(
    <UiProvider>
      <DesignRequestPanel
        order={shown}
        lineNo={1}
        onUse={onUse}
        onChanged={vi.fn()}
      />
    </UiProvider>,
  );
  return onUse;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Đề nghị Design tạo mã (ticket 06)", () => {
  it("opens the drafted request on click and records it sent", async () => {
    page(order({ status: "in_review" }));
    expect(screen.queryByText(/BRN-PO-1 dòng 1/)).toBeNull();
    fireEvent.click(button("Đề nghị Design tạo mã"));
    expect(await screen.findByText(/BRN-PO-1 dòng 1/)).toBeTruthy();
    expect(screen.getByText(/Gửi: design@seller.example/)).toBeTruthy();
    fireEvent.click(button("Ghi đã gửi Design"));
    await waitFor(() =>
      expect(api.recordDesignAsked).toHaveBeenCalledWith(
        expect.any(String),
        1,
        expect.any(Number),
        expect.any(String),
      ),
    );
  });

  it("offers the code Design named to fill the box, never confirming it", async () => {
    const onUse = page(
      order({
        status: "in_review",
        design_requests: [{ line_no: 1, by: AN, at: "2026-11-16T03:00:00Z" }],
      }),
    );
    expect(screen.getByText("Chờ Design")).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: /CB-2010/ }));
    expect(onUse).toHaveBeenCalledWith("CB-2010");
    expect(api.recordDesignAsked).not.toHaveBeenCalled();
  });
});
