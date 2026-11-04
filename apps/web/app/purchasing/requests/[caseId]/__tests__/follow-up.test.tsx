import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

vi.mock("../../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));
vi.mock("../../../../../lib/session", () => ({ apiClient: () => ({}) }));
vi.mock("../../../_lib/api", () => ({ purchasingApi: () => ({}) }));

import { OrderFollowUp } from "../follow-up";

afterEach(cleanup);

const order = {
  po_ref: "PR-2611-004-03",
  supplier_code: "KIMURA",
  currency: "VND",
  lines: [
    {
      line_no: 1,
      item_code: "DC-200",
      description: "Dao cắt cáp",
      quantity: "4",
      unit: "cái",
      unit_price: "1200000",
      amount: "4800000",
      need_by: "2026-11-20",
    },
  ],
};
const tracking = {
  po_ref: "PR-2611-004-03",
  bravo_no: "PO-26110007",
  confirmation: null,
  receipts: [{ line_no: 1, quantity: "4", received_on: "2026-11-19" }],
};

function draw(status: "po_drafted" | "delivered") {
  render(
    <UiProvider>
      <OrderFollowUp
        c={
          {
            case_id: "c-1",
            case_version: 9,
            status,
            tracking: [tracking],
          } as never
        }
        order={order as never}
        mails={[]}
        onChanged={vi.fn()}
      />
    </UiProvider>,
  );
}

describe("an order followed to its goods", () => {
  it("offers nothing more to record once every line arrived", () => {
    draw("delivered");
    const receive = screen.getByRole("button", { name: /Ghi nhận hàng/ });
    expect(receive.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText(/dòng 1 4\/4 cái/)).toBeTruthy();
  });

  it("lets a buyer record what arrived while the order is followed", () => {
    draw("po_drafted");
    const receive = screen.getByRole("button", { name: /Ghi nhận hàng/ });
    expect(receive.hasAttribute("disabled")).toBe(false);
  });
});
