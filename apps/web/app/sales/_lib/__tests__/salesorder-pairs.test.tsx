import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

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

const PAIR = {
  pair_id: "p-1",
  example_id: null,
  customer_code: "KHB",
  po_no: "PO-0001",
  received_on: "2026-11-06",
  rows: 2,
  added_by: AN,
  added_at: "2026-11-14T02:00:00Z",
  replayed: true,
};
const api = {
  salesOrderPairs: vi.fn(async () => [PAIR]),
  withdrawSalesOrderPair: vi.fn(async () => PAIR),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { SalesOrderPairs } from "../../_components/salesorder-pairs";

/**
 * A customer's worked pairs (ticket 41): listed with whether a replay reads
 * each, and a wrong one withdrawn only after a confirmation naming its PO.
 * The server refuses a caller who may not, and audits who did.
 */
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Cặp ví dụ của khách (ticket 41)", () => {
  it("lists each pair by its PO and withdraws one after a confirmation", async () => {
    render(
      <UiProvider>
        <SalesOrderPairs customerCode="KHB" />
      </UiProvider>,
    );
    expect(await screen.findByText("PO-0001")).toBeTruthy();
    expect(screen.getByText("Được chạy thử")).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "Rút cặp ví dụ PO PO-0001" }),
    );
    // Nothing leaves before the person confirms.
    expect(
      (await screen.findAllByText("Rút cặp ví dụ PO PO-0001?")).length,
    ).toBeGreaterThan(0);
    expect(api.withdrawSalesOrderPair).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Rút cặp" }));
    await waitFor(() =>
      expect(api.withdrawSalesOrderPair).toHaveBeenCalledWith(
        "p-1",
        expect.any(String),
      ),
    );
    await waitFor(() => expect(api.salesOrderPairs).toHaveBeenCalledTimes(2));
  }, 20000);
});
