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
import { GIANG, pendingQuote } from "./fixtures";

/**
 * DW1 suggests each line's price with the row it came from (Q7, 2026-10-28:
 * "Sales nhập giá; DW1 chỉ đưa căn cứ"). "Điền giá DW1 gợi ý" fills only the
 * fields still empty and records nothing: Sales presses "Ghi giá".
 */
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: GIANG,
    displayName: "Giang",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ listWorkspaceMembers: vi.fn().mockResolvedValue([]) }),
}));

type Quote = SalesSchemas["QuoteCaseView"];
type Evidence = SalesSchemas["EvidenceView"];

function line(lineNo: number): Quote["lines"][number] {
  return {
    line_no: lineNo,
    customer_item_code: null,
    description: `Cáp dòng ${lineNo}`,
    quantity: "3000",
    uom: "m",
    target_price: null,
    needed_by: null,
    anchors: {},
    model_read: [],
    candidates: [],
  };
}

function evidence(
  lineNo: number,
  suggestion: Evidence["suggestion"],
): Evidence {
  return {
    line_no: lineNo,
    prv_code: "CB-2007",
    as_of: "2026-10-02",
    pricing_policy: "sales_pricing@0.2.0",
    target_price: null,
    own_history: [],
    other_customers: [],
    orders: [],
    lme: null,
    copper_usd_per_uom: null,
    floor: null,
    freight_usd_per_km: null,
    reference_price: null,
    suggestion,
  };
}

/** Line 1 from the customer's own quotation (with its terms), line 2 from
 * their last order, raised to the floor; line 3 has nothing to go on. */
function designReplied(): Quote {
  return {
    ...pendingQuote(),
    status: "design_replied",
    case_version: 6,
    lines: [line(1), line(2), line(3)],
    pricing: null,
    submission: null,
    decision: null,
    evidence: [
      evidence(1, {
        unit_price: "0.6980",
        basis: "own_quotation",
        source_no: "Q26-0122",
        raised_to_floor: false,
        moq: "3000",
        lead_time_days: 28,
        copper_basis: {
          kind: "lme_band",
          low_usd_per_tonne: "10500",
          high_usd_per_tonne: "11000",
        },
      }),
      evidence(2, {
        unit_price: "0.5500",
        basis: "last_order",
        source_no: "SO25-1120",
        raised_to_floor: true,
        moq: null,
        lead_time_days: null,
        copper_basis: null,
      }),
      evidence(3, null),
    ],
  };
}

const api = {
  lme: vi.fn(async () => ({ items: [] })),
  price: vi.fn(async () => ({ case_version: 7 })),
  quote: vi.fn(),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { PricingForm } from "../../quotes/[caseId]/pricing";

const value = (label: string) =>
  (screen.getByLabelText(label) as HTMLInputElement).value;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("DW1's suggested price (Q7)", () => {
  it("shows each suggestion with the row it came from", async () => {
    render(
      <UiProvider>
        <PricingForm quote={designReplied()} onDone={vi.fn()} />
      </UiProvider>,
    );

    expect(
      await screen.findByText("báo giá Q26-0122 còn hiệu lực của khách"),
    ).toBeTruthy();
    expect(
      screen.getByText("đơn SO25-1120 gần nhất của khách, nâng lên giá sàn"),
    ).toBeTruthy();
    expect(screen.getByText("Chưa có căn cứ để gợi ý")).toBeTruthy();
  }, 20_000);

  it("fills only the empty fields, and records nothing until 'Ghi giá'", async () => {
    render(
      <UiProvider>
        <PricingForm quote={designReplied()} onDone={vi.fn()} />
      </UiProvider>,
    );
    // Sales already typed line 2's price: the suggestion leaves it alone.
    fireEvent.change(await screen.findByLabelText("Đơn giá dòng 2"), {
      target: { value: "0,61" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Điền giá DW1 gợi ý" }));

    await waitFor(() => expect(value("Đơn giá dòng 1")).toMatch(/^0,698/));
    expect(value("MOQ dòng 1")).toMatch(/^3[.]?000$/);
    expect(value("Lead time dòng 1")).toBe("28");
    expect(value("LME từ (USD/tấn) dòng 1")).toMatch(/^10[.]?500$/);
    expect(value("Đơn giá dòng 2")).toBe("0,61");
    expect(value("Đơn giá dòng 3")).toBe("");
    expect(api.price).not.toHaveBeenCalled();
  }, 20_000);
});
