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
import { AN, order, pcRequest } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];
type View = SalesSchemas["ReadBackView"];

// An prepared the order and is about to record its Bravo entry (ticket 03).
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

const prepared: Order = order({
  status: "prepared",
  case_version: 6,
  prepared_by: AN,
  makers: [AN],
});

const NOTHING_READ: View = {
  read_back: null,
  stale: false,
  prices_hidden: false,
};
const READ: View = {
  read_back: {
    case_id: prepared.case_id,
    case_version: 6,
    differences: [],
    file_sha256: "0".repeat(64),
    po_no: "PO-1",
    read_at: "2026-11-17T02:00:00Z",
    read_by: AN,
    rows_read: 1,
    so_no: "SO-2611-0042",
  },
  stale: false,
  prices_hidden: false,
};

let readBack: View = NOTHING_READ;
const api = {
  pcRequest: vi.fn(async () => pcRequest()),
  order: vi.fn(async () => prepared),
  bravoReadBack: vi.fn(async () => readBack),
  bravoEntry: vi.fn(async () => ({})),
  myWork: vi.fn(async () => []),
  history: vi.fn(async () => []),
  caseActivity: vi.fn(async () => ({ entries: [] })),
  customers: vi.fn(async () => ({ items: [] })),
  artifacts: vi.fn(async () => ({
    case_version: prepared.case_version,
    available: [],
    artifacts: [],
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import OrderPage from "../../orders/[caseId]/page";
import { SalesFrameProvider } from "../../_components/sales-frame";

const SLOW = 20_000;

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  readBack = NOTHING_READ;
});

async function openTheBravoDialog(): Promise<HTMLInputElement> {
  render(
    <UiProvider>
      <SalesFrameProvider>
        <OrderPage />
      </SalesFrameProvider>
    </UiProvider>,
  );
  fireEvent.click(
    await screen.findByRole(
      "button",
      { name: "Đã nhập Bravo" },
      { timeout: 5000 },
    ),
  );
  return (await screen.findByLabelText(
    "Số đơn bán hàng trên Bravo",
  )) as HTMLInputElement;
}

describe("ticket 03: the SO number Bravo was read back with fills the entry", () => {
  it(
    "offers the read-back's SO number, which the PIC still records",
    async () => {
      readBack = READ;
      const field = await openTheBravoDialog();
      await waitFor(() => expect(field.value).toBe("SO-2611-0042"));
      expect(screen.getByText(/Lấy từ lần đọc lại SO/)).toBeTruthy();

      // Filled is not recorded: nothing is sent until the PIC states the
      // comparison and presses the button.
      expect(api.bravoEntry).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole("checkbox"));
      fireEvent.click(screen.getByRole("button", { name: "Ghi số đơn Bravo" }));
      await waitFor(() => expect(api.bravoEntry).toHaveBeenCalledTimes(1));
      const [, body] = api.bravoEntry.mock.calls[0] as unknown as [
        string,
        { so_no: string },
      ];
      expect(body.so_no).toBe("SO-2611-0042");
    },
    SLOW,
  );

  it(
    "leaves the field empty with nothing read back",
    async () => {
      const field = await openTheBravoDialog();
      await waitFor(() => expect(api.bravoReadBack).toHaveBeenCalled());
      expect(field.value).toBe("");
      expect(screen.queryByText(/Lấy từ lần đọc lại SO/)).toBeNull();
    },
    SLOW,
  );
});
