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
import { AN, finding, order } from "./fixtures";

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
  correctValue: vi.fn(async () => ({
    case_kind: "order",
    case_id: "c-1",
    case_version: 4,
    status: "in_review",
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { ValueCorrections } from "../../orders/[caseId]/value-corrections";
import { PRICE_SENTENCE } from "../../_components/money";

/** Line 1's quantity and price read from a hidden row; the quantity typed. */
function flagged(prices: boolean) {
  const base = order();
  const line = {
    ...base.lines[0]!,
    unit_price: prices ? "1150" : { hidden: true as const },
    corrections: [
      { field: "quantity", value: "6710", by: AN, at: "2026-10-02T02:00:00Z" },
    ],
  };
  return {
    order: { ...base, lines: [line] },
    finding: finding({
      key: "value_uncertain:1",
      code: "value_uncertain",
      line_no: 1,
      expected: null,
      actual: "hidden_row",
      allowed: ["ask_customer"],
      fields: ["quantity", "unit_price"],
    }),
  };
}

function control(prices: boolean, onCorrected = () => {}) {
  const { order: o, finding: f } = flagged(prices);
  return render(
    <UiProvider>
      <ValueCorrections
        order={o}
        finding={f}
        canEdit
        canTypeAmounts={prices}
        onCorrected={onCorrected}
      />
    </UiProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a value DW1 was not sure of, corrected field by field (ticket 15)", () => {
  it("shows each flagged value as read beside what Sales typed, and how many are left", () => {
    control(true);
    const quantity = screen.getByRole("row", { name: /Số lượng/ });
    expect(within(quantity).getByText("6.100")).toBeTruthy(); // as read
    expect(within(quantity).getByText("6.710")).toBeTruthy(); // as typed
    const price = screen.getByRole("row", { name: /Đơn giá/ });
    expect(within(price).getByText("Chưa chắc chắn")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Còn 1/2");
  }, 20_000);

  it("types a price with its field, the case version and a key", async () => {
    const onCorrected = vi.fn();
    control(true, onCorrected);
    fireEvent.change(
      screen.getByRole("textbox", { name: "Giá trị đúng: Đơn giá, dòng 1" }),
      { target: { value: "1.200" } },
    );
    const price = screen.getByRole("row", { name: /Đơn giá/ });
    fireEvent.click(within(price).getByRole("button", { name: "Ghi" }));
    await waitFor(() => expect(api.correctValue).toHaveBeenCalledTimes(1), {
      timeout: 5000,
    });
    const [caseId, key, body, idempotency] = api.correctValue.mock
      .calls[0] as unknown as [string, string, unknown, string];
    expect([caseId, key, body]).toEqual([
      order().case_id,
      "value_uncertain:1",
      { case_version: 3, field: "unit_price", value: "1200" },
    ]);
    expect(idempotency).toMatch(/^[0-9a-f-]{36}$/);
    await waitFor(() => expect(onCorrected).toHaveBeenCalled());
  }, 20_000);

  it("offers no price input, and shows no price, to who may not read prices", () => {
    const { container } = control(false);
    const price = screen.getByRole("row", { name: /Đơn giá/ });
    expect(within(price).queryByRole("textbox")).toBeNull();
    expect(within(price).getByText(PRICE_SENTENCE)).toBeTruthy();
    expect(container.textContent).not.toContain("1.150");
    // The quantity is no price: it is still typed.
    const quantity = screen.getByRole("row", { name: /Số lượng/ });
    expect(within(quantity).getByRole("textbox")).toBeTruthy();
  }, 20_000);
});
