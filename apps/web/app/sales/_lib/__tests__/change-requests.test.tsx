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
import { formatDate } from "../../../../lib/dates";
import { AN, order } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];
type Request = SalesSchemas["ChangeRequestView"];
type Line = SalesSchemas["ChangeLineView"];

let SCOPES = ["sales.case.read", "sales.price.read", "sales.order.prepare"];
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

const TEXT = "RE: PO\n\nLine 1: 2 km. Table: 30-10-26";

function line(overrides: Partial<Line> = {}): Line {
  return {
    seq: 1,
    line_no: 1,
    field: "requested_date",
    held: "2026-11-16",
    asked: "2026-10-30",
    written: "30-10-26",
    unit: null,
    anchor: { start: 29, end: 37 },
    read_by: "table",
    blocked: null,
    state: "open",
    decided_by: null,
    decided_at: null,
    reason: null,
    ...overrides,
  };
}

function request(overrides: Partial<Request> = {}): Request {
  return {
    request_id: "11111111-1111-4111-8111-111111111111",
    message_id: "R1",
    opened_by: AN,
    opened_at: "2026-10-05T03:00:00Z",
    state: "open",
    lines: [
      line(),
      line({
        seq: 2,
        field: "quantity",
        held: "6100",
        asked: "2",
        written: "2 km",
        unit: "km",
        anchor: { start: 16, end: 20 },
        read_by: "model",
        blocked: "unit_differs",
      }),
    ],
    unread: 0,
    text: TEXT,
    reading: "read",
    prompt: "sales.change_request@1.0.0",
    ...overrides,
  };
}

const api = {
  confirmChangeLine: vi.fn(async () => ({
    case_version: 2,
    request: request(),
  })),
  rejectChangeLine: vi.fn(async () => ({
    case_version: 1,
    request: request(),
  })),
  openChangeRequest: vi.fn(),
  addChangeLine: vi.fn(),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { ChangeRequestsPanel } from "../../orders/[caseId]/change-requests";

let shown: Order = order({ status: "in_review", change_requests: [request()] });
const onChanged = vi.fn();

function page() {
  return render(
    <UiProvider>
      <ChangeRequestsPanel
        order={shown}
        viewer={{
          principalId: AN,
          hasScope: (s: string) => SCOPES.includes(s),
        }}
        onChanged={onChanged}
      />
    </UiProvider>,
  );
}

const SLOW = 20_000;

/** The buttons labelled ``name`` in ``region``: by text, since a role query
 * over antd's table is slow in jsdom. */
function buttons(
  region: ReturnType<typeof within>,
  name: string,
): HTMLButtonElement[] {
  return region
    .getAllByText(name, { selector: "button span" })
    .map((el: HTMLElement) => el.closest("button") as HTMLButtonElement);
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  SCOPES = ["sales.case.read", "sales.price.read", "sales.order.prepare"];
});

/** The request's section, found by its mail's link (a role query over the
 * whole order page is slow in jsdom). */
async function panel() {
  const link = await screen.findByText("Thư R1", { selector: "a" });
  const section = link.closest("section");
  expect(section?.getAttribute("aria-label")).toBe("Yêu cầu từ thư R1");
  return within(section as HTMLElement);
}

describe("a change the customer asked by mail (ticket 27)", () => {
  it(
    "confirms one line at a time, sending the version it was read on, and has no bulk control",
    async () => {
      shown = order({ status: "in_review", change_requests: [request()] });
      page();
      const region = await panel();

      const [first] = buttons(region, "Xác nhận");
      fireEvent.click(first!);
      await waitFor(() =>
        expect(api.confirmChangeLine).toHaveBeenCalledTimes(1),
      );
      const [caseId, requestId, seq, version] = api.confirmChangeLine.mock
        .calls[0] as unknown as [string, string, number, number];
      expect([caseId, requestId, seq, version]).toEqual([
        shown.case_id,
        request().request_id,
        1,
        shown.case_version,
      ]);
      expect(screen.queryByText(/tất cả/i)).toBeNull();
    },
    SLOW,
  );

  it(
    "a quantity in km on a line in metres cannot be confirmed, and says why",
    async () => {
      shown = order({ status: "in_review", change_requests: [request()] });
      page();
      const region = await panel();

      const confirms = buttons(region, "Xác nhận");
      expect(confirms.map((b) => b.disabled)).toEqual([false, true]);
      expect(
        region.getByText(
          /Khách ghi đơn vị km, dòng tính bằng m: DW1 không tự quy đổi/,
        ),
      ).toBeTruthy();
      expect(region.getByText("Máy đọc, cần kiểm")).toBeTruthy();
    },
    SLOW,
  );

  it(
    "a queued request waits for the one before it",
    async () => {
      shown = order({
        status: "in_review",
        change_requests: [request({ state: "queued", lines: [line()] })],
      });
      page();
      const region = await panel();

      const confirm = buttons(region, "Xác nhận")[0]!;
      expect((confirm as HTMLButtonElement).disabled).toBe(true);
      expect(
        region.getAllByText(
          "Yêu cầu này chờ yêu cầu trước của đơn được xử lý xong.",
        ).length,
      ).toBeGreaterThan(0);
      expect(region.getByText("Chờ yêu cầu trước")).toBeTruthy();
    },
    SLOW,
  );

  it(
    "rejecting asks why and sends the person's words",
    async () => {
      shown = order({ status: "in_review", change_requests: [request()] });
      page();
      const region = await panel();

      fireEvent.click(buttons(region, "Từ chối")[1]!);
      const dialog = await screen.findByRole("dialog");
      fireEvent.change(within(dialog).getByLabelText("Lý do"), {
        target: { value: "Hỏi lại khách theo mét" },
      });
      fireEvent.click(buttons(within(dialog), "Từ chối")[0]!);
      await waitFor(() =>
        expect(api.rejectChangeLine).toHaveBeenCalledTimes(1),
      );
      const call = api.rejectChangeLine.mock.calls[0] as unknown as [
        string,
        string,
        number,
        number,
        string,
      ];
      expect(call.slice(2, 5)).toEqual([
        2,
        shown.case_version,
        "Hỏi lại khách theo mét",
      ]);
    },
    SLOW,
  );

  it(
    "without the prepare scope every decision is disabled with its reason, and the mail's text is not served",
    async () => {
      SCOPES = ["sales.case.read"];
      shown = order({
        status: "in_review",
        change_requests: [request({ text: null })],
      });
      page();
      const region = await panel();

      for (const button of buttons(region, "Xác nhận"))
        expect((button as HTMLButtonElement).disabled).toBe(true);
      expect(region.queryByText("Xem trong thư")).toBeNull();
      expect(
        region.getAllByText(formatDate("2026-10-30")).length,
      ).toBeGreaterThan(0);
    },
    SLOW,
  );
});
