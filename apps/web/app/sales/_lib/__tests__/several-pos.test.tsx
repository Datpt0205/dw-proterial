import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN } from "./fixtures";

type Message = SalesSchemas["InboxMessageView"];

const scopes = ["sales.case.read", "sales.inbox.process"];
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
let focus = "M11";
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(`message=${focus}`),
  usePathname: () => "/sales/inbox",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

function routed(id: string, owner: string, extra = {}): Message {
  return {
    message_id: id,
    sender: "buyer@vlx.example",
    sender_name: "VLX Purchasing",
    subject: `Đổi ngày giao ${id}`,
    received_at: "2026-10-01T03:00:00Z",
    body_text: "Xin đổi ngày giao",
    attachments: [],
    sender_verified: true,
    disposition: {
      kind: "routed_to_sales",
      reason: "delivery_change",
      owner,
      processed_at: "2026-10-01T03:05:00Z",
      thread_cases: [],
      order_cases: [],
      ...extra,
    },
    handoff_draft: null,
    processing: null,
  };
}

let inbox: Message[] = [];
const api = {
  inbox: vi.fn(async () => inbox),
  overview: vi.fn(async () => ({
    worker: { paused: false, changed_by: null, changed_at: null, reason: null },
  })),
  markHandled: vi.fn(async (id: string, note: string | null) => ({
    message_id: id,
    handled_at: "2026-10-27T09:00:00Z",
    handled_by: AN,
    handled_note: note,
  })),
  reopenMessage: vi.fn(async (id: string) => ({
    message_id: id,
    handled_at: null,
    handled_by: null,
    handled_note: null,
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import InboxPage from "../../inbox/page";
import { SalesFrameProvider } from "../../_components/sales-frame";

function page() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <InboxPage />
      </SalesFrameProvider>
    </UiProvider>,
  );
}

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function onCases(id: string, extra = {}): Message {
  const message = routed(id, "an.nguyen@alpha.local");
  return {
    ...message,
    disposition: {
      ...message.disposition,
      kind: "case_created",
      reason: null,
      owner: null,
      case_kind: "order",
      case_id: "00000000-0000-0000-0000-0000000000c1",
      ...extra,
    },
  };
}

describe("a mail with several POs (ticket 19)", () => {
  it(
    "is one row listing each of its cases by PO number",
    async () => {
      focus = "P3";
      inbox = [
        onCases("P3", {
          order_cases: [
            {
              case_kind: "order",
              case_id: "00000000-0000-0000-0000-0000000000c1",
              number: "VLX-PO-1",
            },
            {
              case_kind: "order",
              case_id: "00000000-0000-0000-0000-0000000000c2",
              number: "VLX-PO-2",
            },
            {
              case_kind: "order",
              case_id: "00000000-0000-0000-0000-0000000000c3",
              number: "VLX-PO-3",
            },
          ],
        }),
      ];
      page();
      const links = await screen.findAllByRole("link", {
        name: /^PO VLX-PO-\d$/,
      });
      expect(links.map((l) => l.getAttribute("href"))).toEqual([
        "/sales/orders/00000000-0000-0000-0000-0000000000c1",
        "/sales/orders/00000000-0000-0000-0000-0000000000c2",
        "/sales/orders/00000000-0000-0000-0000-0000000000c3",
      ]);
      expect(screen.queryByRole("link", { name: "Mở đơn hàng" })).toBeNull();
    },
    SLOW,
  );

  it(
    "a mail on one case keeps its one link",
    async () => {
      focus = "M01";
      inbox = [onCases("M01")];
      page();
      expect(
        await screen.findByRole("link", { name: "Mở đơn hàng" }),
      ).toBeTruthy();
    },
    SLOW,
  );
});
