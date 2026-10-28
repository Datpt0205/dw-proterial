import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, finding, orderInBravo, pendingQuote } from "./fixtures";

/**
 * The audit's UI gaps (2026-10-21), on the case pages: a prepared value
 * nobody opened is "Chưa mở nguồn", never "Đã kiểm" (1); the cross-checker is
 * told which values nobody opened (5); the quote says what it covered (4);
 * and what blocks the case sits above its history (3, ui-quality §2).
 */
type Order = SalesSchemas["OrderCaseView"];
type Quote = SalesSchemas["QuoteCaseView"];

const SCOPES = [
  "sales.case.read",
  "sales.price.read",
  "sales.order.prepare",
  "sales.order.cross_check",
  "sales.quote.prepare",
];
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
let caseId = "";
vi.mock("next/navigation", () => ({
  useParams: () => ({ caseId }),
}));

let order: Order = orderInBravo();
let quote: Quote = pendingQuote();
const api = {
  order: vi.fn(async () => order),
  quote: vi.fn(async () => quote),
  myWork: vi.fn(async () => []),
  history: vi.fn(async () => []),
  caseActivity: vi.fn(async () => ({ entries: [] })),
  customers: vi.fn(async () => ({ items: [] })),
  lme: vi.fn(async () => ({ items: [] })),
  orderSource: vi.fn(() => new Promise(() => {})),
  quoteSource: vi.fn(() => new Promise(() => {})),
  artifacts: vi.fn(async () => ({
    case_version: 3,
    available: [],
    artifacts: [],
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import OrderPage from "../../orders/[caseId]/page";
import QuotePage from "../../quotes/[caseId]/page";
import { SalesFrameProvider } from "../../_components/sales-frame";
import { ValueStateTag } from "../../_components/tags";
import { quoteCoverageStatement } from "../statements";
import { VALUE_STATE } from "../labels";

function show(page: "order" | "quote") {
  caseId = page === "order" ? order.case_id : quote.case_id;
  return render(
    <UiProvider>
      <SalesFrameProvider>
        {page === "order" ? <OrderPage /> : <QuotePage />}
      </SalesFrameProvider>
    </UiProvider>,
  );
}

/** Whether `first` comes before `second` in the document. */
function before(first: HTMLElement, second: HTMLElement): boolean {
  return Boolean(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  );
}

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  order = orderInBravo();
  quote = pendingQuote();
});

describe('"Chưa mở nguồn" (gap 1)', () => {
  it("has its own words and look, apart from 'Đã kiểm' and 'Máy đọc'", () => {
    render(
      <UiProvider>
        {Object.keys(VALUE_STATE).map((state) => (
          <span key={state} data-state={state}>
            <ValueStateTag state={state} />
          </span>
        ))}
      </UiProvider>,
    );
    const chip = (state: string) =>
      document.querySelector(`[data-state="${state}"]`)!
        .firstElementChild as HTMLElement;
    expect(chip("not_opened").textContent).toBe("Chưa mở nguồn");
    // An icon besides the words (never colour alone) ...
    expect(chip("not_opened").querySelector("[aria-hidden]")).toBeTruthy();
    // ... and a look no other state shares.
    const look = (state: string) =>
      `${chip(state).getAttribute("style")}|${chip(state).querySelector("[aria-hidden]")?.className}`;
    const others = Object.keys(VALUE_STATE)
      .filter((s) => s !== "not_opened")
      .map(look);
    expect(others).not.toContain(look("not_opened"));
  });

  it(
    "is what a line row shows for a prepared value nobody opened",
    async () => {
      order = {
        ...orderInBravo(),
        lines: orderInBravo().lines.map((l) => ({
          ...l,
          value_states: {
            line_no: "confirmed",
            description: "not_opened",
            unit_price: "confirmed",
          },
        })),
      };
      show("order");
      const lines = (await screen.findByText("Các dòng DW1 đọc")).closest(
        ".ant-card",
      ) as HTMLElement;
      expect(
        within(lines).getAllByText("Chưa mở nguồn").length,
      ).toBeGreaterThan(0);
    },
    SLOW,
  );
});

describe("the cross-checker is told which values nobody opened (gap 5)", () => {
  it(
    "lists them by line, each opening its source",
    async () => {
      order = {
        ...orderInBravo(),
        unopened_values: [
          { field: "po_no", line_no: null },
          { field: "description", line_no: 1 },
          { field: "unit_price", line_no: 1 },
        ],
      };
      show("order");
      const list = (
        await screen.findByText(
          "3 giá trị chưa ai mở nguồn trước khi nhập Bravo",
        )
      ).closest(".ant-alert") as HTMLElement;
      expect(within(list).getByText("Đầu PO:")).toBeTruthy();
      expect(within(list).getByText("Dòng 1:")).toBeTruthy();
      fireEvent.click(
        within(list).getByRole("button", { name: "Mở nguồn Đơn giá dòng 1" }),
      );
      const drawer = await screen.findByRole("dialog");
      expect(drawer.textContent).toContain("Bản gốc");
      expect(api.orderSource).toHaveBeenCalledTimes(1);
    },
    SLOW,
  );

  it(
    "draws nothing before Bravo, while the preparer is still checking",
    async () => {
      order = {
        ...orderInBravo(),
        status: "in_review",
        bravo_recorded_at: null,
        unopened_values: [{ field: "unit_price", line_no: 1 }],
      };
      show("order");
      await screen.findByText("Các dòng DW1 đọc");
      expect(screen.queryByText(/chưa ai mở nguồn/)).toBeNull();
    },
    SLOW,
  );

  it(
    "draws nothing when the server sends no list (not a cross-checker)",
    async () => {
      order = { ...orderInBravo(), unopened_values: null };
      show("order");
      await screen.findByText("Các dòng DW1 đọc");
      expect(screen.queryByText(/chưa ai mở nguồn/)).toBeNull();
    },
    SLOW,
  );
});

describe("what blocks the case sits above its history (gap 3)", () => {
  it(
    "on an order: the coverage line and the flags come before the history and DW1's activity",
    async () => {
      order = { ...orderInBravo(), findings: [finding()] };
      show("order");
      const flags = await screen.findByText("Cờ cần quyết định");
      const coverage = screen.getByText(/^Phạm vi đã kiểm:/);
      const history = screen.getByText("Hành trình hồ sơ");
      const activity = screen.getByText("DW1 đã làm gì");
      expect(before(coverage, flags)).toBe(true);
      expect(before(flags, history)).toBe(true);
      expect(before(flags, activity)).toBe(true);
    },
    SLOW,
  );

  it(
    "on a quote: the coverage line and the quote's flags come before the history",
    async () => {
      quote = {
        ...pendingQuote(),
        findings: [
          {
            key: "price_below_policy_floor:1",
            code: "price_below_policy_floor",
            blocking: false,
            line_no: 1,
            missing: [],
            flagged: [],
            source_not_served: [],
            confirmed: [],
            expected: null,
            actual: null,
            rule_versions: [],
            disposition: { kind: "open" },
          } as unknown as Quote["findings"][number],
        ],
      };
      show("quote");
      const flags = await screen.findByText("Cờ của báo giá", {
        selector: ".ant-card-head-title",
      });
      const coverage = screen.getByText(/^Phạm vi đã đọc:/);
      const history = screen.getByText("Hành trình hồ sơ");
      const activity = screen.getByText("DW1 đã làm gì");
      expect(before(coverage, flags)).toBe(true);
      expect(before(flags, history)).toBe(true);
      expect(before(flags, activity)).toBe(true);
    },
    SLOW,
  );
});

describe("the quote's coverage statement (gap 4)", () => {
  const covered = (coverage: Partial<Quote["coverage"]>) =>
    quoteCoverageStatement({
      ...pendingQuote(),
      coverage: { ...pendingQuote().coverage, ...coverage },
    });

  it("says what was read, from where, what a model read and the flags", () => {
    expect(
      covered({
        lines_read: 3,
        regions: ["RFQ", "page 2", "message_text"],
        model_read: 4,
        model_read_confirmed: 1,
        findings: 2,
      }),
    ).toBe(
      "Đã đọc 3 dòng từ sheet RFQ, trang 2, nội dung thư; 4 giá trị mô hình đọc, 1 đã xác nhận; 2 cờ",
    );
  });

  it("never claims N/N: the reader counts no printed rows", () => {
    const words = covered({ lines_read: 3, regions: ["page 1"] });
    expect(words).not.toMatch(/\d+\/\d+/);
    expect(words).toContain("không giá trị nào do mô hình đọc");
  });

  it(
    "is on the quote page, warning while a model-read value is unconfirmed",
    async () => {
      quote = {
        ...pendingQuote(),
        coverage: {
          lines_read: 1,
          regions: ["message_text"],
          model_read: 2,
          model_read_confirmed: 1,
          findings: 1,
        },
      };
      show("quote");
      const alert = (
        await screen.findByText(
          "Phạm vi đã đọc: Đã đọc 1 dòng từ nội dung thư; 2 giá trị mô hình đọc, 1 đã xác nhận; 1 cờ.",
        )
      ).closest(".ant-alert") as HTMLElement;
      expect(alert.textContent).toContain(
        "Còn 1 giá trị mô hình đọc chưa xác nhận",
      );
    },
    SLOW,
  );
});

describe("a value that waits on its source (gap 2)", () => {
  /** A request at intake whose quantity a model read from page 1. */
  const waiting = (unserved: string[]): Quote => ({
    ...pendingQuote(),
    status: "received",
    pricing: null,
    submission: null,
    decision: null,
    lines: [
      {
        line_no: 1,
        customer_item_code: null,
        description: "Cáp 2C AWG24 BLK",
        quantity: "1200",
        uom: "m",
        target_price: null,
        needed_by: null,
        anchors: {
          quantity: {
            attachment_id: "M10-A1",
            attachment_sha256: "f".repeat(64),
            cell_ref: null,
            page: 1,
            boxes: [],
            quote: null,
          },
        },
        model_read: ["quantity"],
        candidates: [],
      },
    ],
    findings: [
      {
        key: "value_uncertain:1",
        code: "value_uncertain",
        blocking: true,
        line_no: 1,
        missing: [],
        flagged: ["quantity"],
        source_not_served: unserved,
        confirmed: [],
        expected: null,
        actual: null,
        rule_versions: [],
        disposition: { kind: "open" },
      },
    ],
  });

  async function openAndClose() {
    fireEvent.click(
      await screen.findByRole("button", { name: "Xem nguồn Số lượng dòng 1" }),
    );
    const drawer = await screen.findByRole("dialog");
    fireEvent.click(within(drawer).getAllByRole("button")[0]!);
  }

  it(
    "reads the case again when its source is closed, so 'Xác nhận' follows the server",
    async () => {
      quote = waiting(["quantity"]);
      show("quote");
      await openAndClose();
      await vi.waitFor(() => expect(api.quote).toHaveBeenCalledTimes(2));
    },
    SLOW,
  );

  it(
    "does not read it again when nothing waits on a source",
    async () => {
      quote = waiting([]);
      show("quote");
      await openAndClose();
      await new Promise((resolve) => setTimeout(resolve, 300));
      expect(api.quote).toHaveBeenCalledTimes(1);
    },
    SLOW,
  );
});
