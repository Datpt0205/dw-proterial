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

// A PO the customer wrote in the mail body (AI item 4): no file, and every
// value anchored in the mail's text, which is the one source to open.
const TEXT =
  "Đơn đặt hàng VLX-PO-2610-0201\n\nPO số VLX-PO-2610-0201, ngày 01/10/2026:\n1. VX-W24-BK: 6.100 m, đơn giá 0.0420";
const SHA = "b".repeat(64);
const PO_NO = {
  start: TEXT.indexOf("VLX-PO"),
  end: TEXT.indexOf("VLX-PO") + 16,
};
const LINE = TEXT.indexOf("1. VX");

function inMail(start: number, end: number) {
  return {
    attachment_id: null,
    attachment_sha256: SHA,
    cell_ref: null,
    page: null,
    boxes: [],
    quote: TEXT.slice(start, end),
    chars: { start, end },
  };
}

function fromMail(): Order {
  const base = order();
  return order({
    attachment_id: null,
    attachment_sha256: SHA,
    parser_version: "sales.po_body_extraction@1.0.0",
    header_anchors: { po_no: inMail(PO_NO.start, PO_NO.end) },
    total_anchor: null,
    coverage: { ...base.coverage, regions: ["message_text"] },
    lines: base.lines.map((line) => ({
      ...line,
      anchors: { line_no: inMail(LINE, TEXT.length) },
      value_states: { line_no: "uncertain" },
    })),
  } as Partial<Order>);
}

const SCOPES = ["sales.case.read", "sales.price.read", "sales.order.prepare"];
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
vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId: order().case_id }),
}));

const shown: Order = fromMail();
const api = {
  order: vi.fn(async () => shown),
  myWork: vi.fn(async () => []),
  history: vi.fn(async () => []),
  caseActivity: vi.fn(async () => ({ entries: [] })),
  customers: vi.fn(async () => ({ items: [] })),
  artifacts: vi.fn(async () => ({
    case_version: shown.case_version,
    available: [],
    artifacts: [],
  })),
  orderMessageText: vi.fn(async () => ({
    case_id: shown.case_id,
    case_version: shown.case_version,
    text: TEXT,
    sha256: SHA,
    served_at: "2026-10-02T03:00:00Z",
  })),
  orderSource: vi.fn(),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import OrderPage from "../../orders/[caseId]/page";
import { SalesFrameProvider } from "../../_components/sales-frame";

function page() {
  return render(
    <UiProvider>
      <SalesFrameProvider>
        <OrderPage />
      </SalesFrameProvider>
    </UiProvider>,
  );
}

const SLOW = 20_000;

afterEach(cleanup);

describe("an order whose PO was written in the mail (AI item 4)", () => {
  it(
    "asks for the mail's text, opens it with the value's words marked, and stops asking",
    async () => {
      page();
      const notice = await screen.findByText(
        /Chưa mở nguồn: nội dung thư/,
        undefined,
        {
          timeout: 5000,
        },
      );
      expect(notice).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: /Mở thư của khách/ }));
      const marked = await screen.findByText("VLX-PO-2610-0201", {
        selector: "mark",
      });
      expect(marked).toBeTruthy();
      expect(api.orderMessageText).toHaveBeenCalledWith(shown.case_id);
      expect(api.orderSource).not.toHaveBeenCalled();
      await waitFor(() =>
        expect(screen.queryByText(/Chưa mở nguồn: nội dung thư/)).toBeNull(),
      );
    },
    SLOW,
  );
});
