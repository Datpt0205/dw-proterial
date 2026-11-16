import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";
import { NotationTable } from "../../master-data/customer-notation";
import {
  caseHref,
  evidenceLine,
  notationValue,
  type CustomerNotation,
} from "../customer-notation";

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

/**
 * A customer's notation on the master data (ticket 37): each kind known, what
 * it rests on (on click), and the kinds not known yet left to a person. The
 * values offered are the server's own list; the server refuses the rest.
 */
const CASE = "0aa10aa0-c939-7000-8539-31fd3e621799";
const view: CustomerNotation = {
  customer_code: "VLX",
  entries: [
    {
      kind: "decimal_mark",
      value: ",",
      source: "confirmed",
      case_kind: "quote",
      case_id: CASE,
      field: "quantity",
      written: "1.200 m",
      confirmed: "1200",
      by: AN,
      at: "2026-11-16T03:00:00Z",
    },
  ],
  choices: {
    decimal_mark: [",", "."],
    date_order: ["day_first", "month_first"],
    dollar_sign: ["USD", "SGD"],
    yen_sign: ["CNY", "JPY"],
  },
};

afterEach(cleanup);

describe("a customer's notation (ticket 37)", () => {
  it("says each value and where it was learned, in words", () => {
    expect(notationValue("decimal_mark", ",")).toBe(
      "1.200 = một nghìn hai trăm",
    );
    expect(notationValue("date_order", "month_first")).toBe(
      "05/11 = ngày 11 tháng 5",
    );
    expect(notationValue("dollar_sign", "SGD")).toBe("$ = SGD");
    expect(evidenceLine(view.entries[0]!)).toBe(
      "Khách viết “1.200 m”, Sales xác nhận 1200",
    );
    expect(caseHref(view.entries[0]!)).toBe(`/sales/quotes/${CASE}`);
    expect(
      caseHref({ ...view.entries[0]!, source: "set", case_id: null }),
    ).toBeNull();
  });

  it("shows every kind, the unknown ones left to a person", () => {
    render(
      <UiProvider>
        <NotationTable
          notation={view}
          loading={false}
          blocked={null}
          pending={null}
          customerCode="VLX"
          onChange={() => undefined}
        />
      </UiProvider>,
    );
    // In the value cell and as the picker's choice.
    expect(screen.getAllByText("1.200 = một nghìn hai trăm")).toHaveLength(2);
    expect(screen.getByText("Học từ xác nhận")).toBeTruthy();
    expect(screen.getAllByText("Chưa biết: để người đọc")).toHaveLength(3);
  });

  it("forgets a kind only through its own button, and not without the scope", () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <UiProvider>
        <NotationTable
          notation={view}
          loading={false}
          blocked={null}
          pending={null}
          customerCode="VLX"
          onChange={onChange}
        />
      </UiProvider>,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Bỏ Số của khách VLX" }),
    );
    expect(onChange).toHaveBeenCalledWith("decimal_mark", null);

    rerender(
      <UiProvider>
        <NotationTable
          notation={view}
          loading={false}
          blocked="Cần quyền chuẩn bị đơn (sales.order.prepare)."
          pending={null}
          customerCode="VLX"
          onChange={onChange}
        />
      </UiProvider>,
    );
    const forget = screen.getByRole("button", {
      name: "Bỏ Số của khách VLX",
    }) as HTMLButtonElement;
    expect(forget.disabled).toBe(true);
  });
});
