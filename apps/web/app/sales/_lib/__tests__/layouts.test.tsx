import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, GIANG } from "./fixtures";

type Source = SalesSchemas["LayoutSourceView"];
type Layout = SalesSchemas["LayoutView"];
type Mapping = SalesSchemas["LayoutMapping"];

let principal = AN;
let scopes = ["sales.case.read", "sales.price.read", "sales.order.prepare"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: principal,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));
// The decision goes to the platform approval the proposal opened.
const decideApproval = vi.fn(async () => ({ status: "approved" }));
const approvalClient = vi.fn((type: string) => ({ type, decideApproval }));
vi.mock("../../../../lib/approvals/registry", () => ({
  approvalClient: (type: string) => approvalClient(type),
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () =>
    new URLSearchParams({ message: "M43", attachment: "M43-A1" }),
  usePathname: () => "/sales/layouts/new",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

const MAPPING: Mapping = {
  kind: "pdf",
  po_no: "Order Number",
  revision: null,
  po_date: "Order Date",
  currency: "Currency",
  line_no: "Item",
  customer_item_code: "Part Number",
  description: "Part Description",
  quantity: "Order Qty",
  uom: "Unit",
  unit_price: "Price",
  amount: "Extended",
  requested_date: "Need By",
  page_label: null,
  total_label: "Order Total",
  thousands_separator: ",",
  decimal_separator: ".",
  date_format: "%Y-%m-%d",
  pdf_columns: null,
};

const SOURCE: Source = {
  message_id: "M43",
  attachment_id: "M43-A1",
  customer_code: "NRV",
  kind: "pdf",
  cells: Object.entries(MAPPING)
    .filter(
      ([k, v]) =>
        typeof v === "string" &&
        !k.endsWith("separator") &&
        k !== "date_format" &&
        k !== "kind",
    )
    .map(([, text], i) => ({
      ref: `p1:${i + 1}:1`,
      sheet: "page 1",
      row: i + 1,
      column: 1,
      text: text as string,
      labelled: false,
    })),
  prefill: {
    prompt: "sales.po_layout_proposal@1.0.0",
    model_profile: "onprem",
    route: "structured_extraction",
    rules: "sales_order_rules@1.4.1",
    outcome: "proposed",
    attachment_id: "M43-A1",
    mapping: MAPPING,
    problems: [],
  },
  approved: null,
};

const LAYOUT: Layout = {
  layout_id: "0aa10aa0-c939-7000-8539-31fd3e621660",
  customer_code: "NRV",
  kind: "pdf",
  version: 1,
  status: "proposed",
  mapping: MAPPING,
  sample: {
    message_id: "M43",
    attachment_id: "M43-A1",
    attachment_sha256: "0".repeat(64),
  },
  proposed_by: AN,
  proposed_at: "2026-10-03T02:00:00Z",
  approval_id: "0aa10aa0-c939-7000-8539-31fd3e621661",
  decided_by: null,
  decided_at: null,
  prefill: SOURCE.prefill,
};

const api = {
  layoutSource: vi.fn(async () => SOURCE),
  previewLayout: vi.fn(async () => ({
    ok: true,
    problems: [],
    po_no: "NRV-PO-26-0502",
    po_date: "2026-10-01",
    currency: "USD",
    revision: 0,
    total: "4877.10",
    lines: [],
  })),
  proposeLayout: vi.fn(async () => LAYOUT),
  layouts: vi.fn(async () => [LAYOUT]),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import OnboardingPage from "../../layouts/new/page";
import LayoutsPage from "../../layouts/page";

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  principal = AN;
  scopes = ["sales.case.read", "sales.price.read", "sales.order.prepare"];
});

describe("onboarding a customer's PO form (ticket 30)", () => {
  it(
    "opens with the model's labels marked as a machine's, and sends only a mapping it read",
    async () => {
      render(
        <UiProvider>
          <OnboardingPage />
        </UiProvider>,
      );

      expect(
        await screen.findByText(
          "Mô hình đã gợi ý cách gán: các trường mở sẵn nhãn mô hình chọn.",
        ),
      ).toBeTruthy();
      expect(screen.getAllByText("Mô hình gợi ý").length).toBeGreaterThan(5);
      const send = screen.getByRole("button", { name: "Gửi duyệt" });
      expect(send.hasAttribute("disabled")).toBe(true);

      fireEvent.click(screen.getByRole("button", { name: "Xem thử" }));
      await waitFor(() => expect(api.previewLayout).toHaveBeenCalledTimes(1));
      const [sent] = api.previewLayout.mock.calls[0] as unknown as [
        { message_id: string; mapping: Mapping },
      ];
      expect(sent.message_id).toBe("M43");
      expect(sent.mapping.unit_price).toBe("Price");
      await waitFor(() =>
        expect(
          screen
            .getByRole("button", { name: "Gửi duyệt" })
            .hasAttribute("disabled"),
        ).toBe(false),
      );
      fireEvent.click(screen.getByRole("button", { name: "Gửi duyệt" }));
      await waitFor(() => expect(api.proposeLayout).toHaveBeenCalledTimes(1));
    },
    SLOW,
  );
});

describe("deciding a mapped form (ticket 30)", () => {
  it(
    "the person who mapped it may not decide it; the head decides on its approval, with a comment",
    async () => {
      scopes = [...scopes, "sales.layout.approve"];
      render(
        <UiProvider>
          <LayoutsPage />
        </UiProvider>,
      );
      const row = (await screen.findByText("NRV")).closest("tr")!;
      expect(
        within(row)
          .getByRole("button", { name: "Duyệt" })
          .hasAttribute("disabled"),
      ).toBe(true);
      cleanup();

      principal = GIANG;
      render(
        <UiProvider>
          <LayoutsPage />
        </UiProvider>,
      );
      const giang = (await screen.findByText("NRV")).closest("tr")!;
      fireEvent.click(within(giang).getByRole("button", { name: "Duyệt" }));
      fireEvent.change(await screen.findByLabelText("Nhận xét"), {
        target: { value: "Mẫu đọc đúng PO" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Duyệt mẫu" }));

      await waitFor(() => expect(decideApproval).toHaveBeenCalledTimes(1));
      expect(approvalClient).toHaveBeenCalledWith("sales.layout");
      const [approvalId, decision] = decideApproval.mock
        .calls[0] as unknown as [string, Record<string, unknown>];
      expect(approvalId).toBe(LAYOUT.approval_id);
      expect(decision).toEqual({
        approve: true,
        comment: "Mẫu đọc đúng PO",
        subject_version: 1,
      });
    },
    SLOW,
  );
});
