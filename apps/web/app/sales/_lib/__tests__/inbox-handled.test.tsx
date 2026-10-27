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
import { AN } from "./fixtures";

type Message = SalesSchemas["InboxMessageView"];

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
  scopes = ["sales.case.read", "sales.inbox.process"];
  focus = "M11";
});

describe("a routed message marked handled (2026-10-27)", () => {
  it(
    "its PIC marks it handled with a note, and the inbox counts it done",
    async () => {
      inbox = [routed("M11", "an.nguyen@alpha.local")];
      page();
      const note = await screen.findByRole("textbox", {
        name: /Ghi chú khi đánh dấu thư M11/,
      });
      fireEvent.change(note, { target: { value: "  Đã gọi khách  " } });
      fireEvent.click(
        screen.getByRole("button", { name: /Đánh dấu thư M11 đã xử lý/ }),
      );
      await waitFor(() => expect(api.markHandled).toHaveBeenCalledTimes(1));
      expect(api.markHandled.mock.calls[0]!.slice(0, 2)).toEqual([
        "M11",
        "Đã gọi khách",
      ]);
    },
    SLOW,
  );

  it(
    "a handled one says who and when, and offers to reopen it",
    async () => {
      inbox = [
        routed("M11", "an.nguyen@alpha.local", {
          handled_at: "2026-10-27T09:00:00Z",
          handled_by: AN,
          handled_note: "Đã gọi khách",
        }),
      ];
      page();
      expect(
        await screen.findByText(/Sales đã xử lý: An \(bạn\)/),
      ).toBeTruthy();
      expect(screen.getByText("Ghi chú: Đã gọi khách")).toBeTruthy();
      // Counted done, not waiting on Sales.
      expect(screen.getByText(/0 chuyển Sales chờ xử lý/)).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: /Mở lại thư M11/ }));
      await waitFor(() => expect(api.reopenMessage).toHaveBeenCalledTimes(1));
    },
    SLOW,
  );

  it(
    "another PIC's message cannot be marked here, and says why",
    async () => {
      focus = "M12";
      inbox = [routed("M12", "dieu.hoang@alpha.local")];
      page();
      const button = await screen.findByRole("button", {
        name: /Đánh dấu thư M12 đã xử lý/,
      });
      expect((button as HTMLButtonElement).disabled).toBe(true);
      expect(
        screen.getByText(
          "Thư này giao cho người khác: người phụ trách hoặc trưởng nhóm đánh dấu.",
        ),
      ).toBeTruthy();
    },
    SLOW,
  );

  it(
    "the head may mark anyone's",
    async () => {
      focus = "M12";
      scopes = ["sales.case.read", "sales.case.assign"];
      inbox = [routed("M12", "dieu.hoang@alpha.local")];
      page();
      const button = await screen.findByRole("button", {
        name: /Đánh dấu thư M12 đã xử lý/,
      });
      expect((button as HTMLButtonElement).disabled).toBe(false);
    },
    SLOW,
  );
});
