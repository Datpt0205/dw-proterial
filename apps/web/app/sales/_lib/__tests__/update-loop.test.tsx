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
type Loop = NonNullable<Order["update_loop"]>;

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
  updatePcRequest: vi.fn(async () => ({
    case_version: 7,
    lines: [1],
    subject: "[Hỏi PC] Ngày giao cho PO BRN-PO-1",
    body: "Chào anh/chị PC,\n- Dòng 1: 6.100 m, khách cần ngày 20/11/2026",
    template_ref: "sales_handoffs@1.1.0#pc_request",
    reminder_at: null,
  })),
  recordUpdatePcAsked: vi.fn(async () => ({ case_id: "c", case_version: 8 })),
  recordUpdatePcAnswer: vi.fn(async () => ({ case_id: "c", case_version: 8 })),
  recordUpdateAnswerSent: vi.fn(async () => ({
    case_id: "c",
    case_version: 8,
  })),
  recordUpdateCustomerAnswer: vi.fn(async () => ({
    case_id: "c",
    case_version: 8,
  })),
  approveBravoUpdate: vi.fn(async () => ({ case_id: "c", case_version: 8 })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { UpdateLoopPanel } from "../../orders/[caseId]/update-loop";

const REQUEST = "11111111-2222-3333-4444-555555555555";

function loop(overrides: Partial<Loop> = {}): Loop {
  return {
    request_id: REQUEST,
    step: "ask_pc",
    since: "2026-11-15T02:00:00Z",
    awaits: "ask_pc",
    verdict: null,
    approval: null,
    lines: [
      {
        line_no: 1,
        held_quantity: "6100",
        held_requested_date: "2026-12-04",
        asked_quantity: null,
        asked_requested_date: "2026-11-20",
        pc_deliveries: null,
        pc_answered_by: null,
      },
    ],
    ...overrides,
  };
}

function page(shown: Order, files: SalesSchemas["ArtifactView"][] = []) {
  return render(
    <UiProvider>
      <UpdateLoopPanel
        order={shown}
        viewer={{
          principalId: AN,
          hasScope: (s: string) => SCOPES.includes(s),
        }}
        artifacts={
          {
            data: {
              case_version: shown.case_version,
              available: [],
              artifacts: files,
            },
            loading: false,
            error: null,
            reload: vi.fn(),
          } as never
        }
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

describe("Vòng cập nhật (ticket 29)", () => {
  it("draws nothing on an order with no change in Bravo", () => {
    const { container } = page(order({ status: "confirmation_sent" }));
    expect(container.textContent).toBe("");
  });

  it("shows the step it waits on and records PC asked", async () => {
    page(order({ status: "confirmation_sent", update_loop: loop() }));
    expect(screen.getByText("Chờ hỏi PC")).toBeTruthy();
    // Held beside asked; the draft opens on click.
    expect(screen.getByText(/04\/12\/2026/)).toBeTruthy();
    await waitFor(() => expect(api.updatePcRequest).toHaveBeenCalled());
    fireEvent.click(button("Ghi đã hỏi PC"));
    await waitFor(() =>
      expect(api.recordUpdatePcAsked).toHaveBeenCalledWith(
        expect.any(String),
        expect.any(Number),
        expect.any(String),
      ),
    );
  });

  it("disables asking PC while a line of the request is undecided", () => {
    page(
      order({
        status: "confirmation_sent",
        update_loop: loop(),
        change_requests: [
          {
            request_id: REQUEST,
            lines: [{ state: "confirmed" }, { state: "open" }],
          } as never,
        ],
      }),
    );
    expect(button("Ghi đã hỏi PC").disabled).toBe(true);
    expect(screen.getByText(/Còn dòng thay đổi chưa xác nhận/)).toBeTruthy();
  });

  it("offers the customer's three answers once the answer was sent", () => {
    page(
      order({
        status: "confirmation_sent",
        update_loop: loop({
          step: "waiting_customer",
          awaits: "waiting_customer",
          verdict: "proposes",
        }),
      }),
    );
    expect(screen.getByText("Chờ khách quyết định")).toBeTruthy();
    expect(screen.getByText("PC đề xuất khác đề nghị của khách")).toBeTruthy();
    for (const name of ["Khách đồng ý", "Khách giữ PO cũ", "Hỏi PC lại"])
      expect(button(name).disabled).toBe(false);
    // PC's answer is recorded only while waiting on PC.
    expect(button("Ghi ngày PC").disabled).toBe(true);
  });

  it("approves only the Bravo update file drawn at this version", async () => {
    const shown = order({
      status: "change_review",
      update_loop: loop({ step: "bravo_update", awaits: "approve_update" }),
    });
    const { unmount } = page(shown);
    expect(button("Duyệt tệp cập nhật Bravo").disabled).toBe(true);
    expect(screen.getByText(/ở mục Tài liệu trước/)).toBeTruthy();
    unmount();

    page(shown, [
      {
        artifact_id: "a-1",
        kind: "bravo_update",
        case_version: shown.case_version,
        template_ref: "sales_bravo_upload@2.1.0",
        sha256: "ab".repeat(32),
        content_type: "application/xlsx",
        size_bytes: 10,
        file_name: "bravo_update.xlsx",
        created_by: AN,
        created_at: "2026-11-15T02:00:00Z",
        downloadable: true,
      },
    ]);
    fireEvent.click(button("Duyệt tệp cập nhật Bravo"));
    await waitFor(() =>
      expect(api.approveBravoUpdate).toHaveBeenCalledWith(
        expect.any(String),
        { case_version: shown.case_version, artifact_id: "a-1" },
        expect.any(String),
      ),
    );
  });

  it("says why a reader cannot move the loop", () => {
    SCOPES = ["sales.case.read"];
    page(order({ status: "confirmation_sent", update_loop: loop() }));
    expect(button("Ghi đã hỏi PC").disabled).toBe(true);
  });
});
