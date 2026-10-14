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
import { AN, order } from "./fixtures";

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
const api = vi.hoisted(() => ({
  confirm: vi.fn(),
  artifacts: vi.fn(),
}));
vi.mock("../api", () => ({ salesApi: () => api }));

import { LinesTable } from "../../orders/[caseId]/lines";
import { OrderActions } from "../../orders/[caseId]/actions";

const PIC = { principalId: AN, hasScope: () => true };

/** M35's line 2 (ticket 21): 2,000 m over two dates, the first too soon. */
function split() {
  const base = order();
  const [line] = base.lines;
  if (line === undefined) throw new Error("the fixture order has no line");
  const at = line.anchors.description;
  if (at === undefined)
    throw new Error("the fixture line has no description anchor");
  return order({
    lines: [
      {
        ...line,
        quantity: "2000",
        requested_date: "2026-10-06",
        printed_schedules: true,
        schedules: [
          {
            quantity: "1000",
            requested_date: "2026-10-06",
            anchor: at,
            suggested_delivery_date: "2026-10-30",
            confirmed_delivery_date: null,
          },
          {
            quantity: "1000",
            requested_date: "2026-11-30",
            anchor: at,
            suggested_delivery_date: "2026-11-30",
            confirmed_delivery_date: null,
          },
        ],
      },
    ],
  });
}

function renderLines(data: ReturnType<typeof order>) {
  const onOpenSource = vi.fn();
  render(
    <UiProvider>
      <LinesTable
        order={data}
        viewer={PIC}
        onChanged={() => {}}
        onOpenSource={onOpenSource}
        onPickCode={() => {}}
      />
    </UiProvider>,
  );
  return onOpenSource;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a PO line split over several delivery dates (ticket 21)", () => {
  it("shows every schedule with its quantity, and the suggestion where the lead time moves it", () => {
    renderLines(split());

    const row = screen.getByText("2 đợt giao").closest("tr");
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement);
    const first = cells.getByText(/06\/10\/2026/).textContent ?? "";
    expect(first.startsWith("06/10/2026 · 1.000")).toBe(true);
    expect(first.endsWith("→ gợi ý 30/10/2026")).toBe(true);
    expect(cells.getByText(/30\/11\/2026 ·/).textContent).not.toContain(
      "gợi ý",
    );
  });

  it("opens each schedule's own place on the PO", () => {
    const onOpenSource = renderLines(split());

    const row = screen.getByText("2 đợt giao").closest("tr") as HTMLElement;
    const expand = row.querySelector("button.ant-table-row-expand-icon");
    expect(expand).not.toBeNull();
    fireEvent.click(expand as HTMLElement);
    fireEvent.click(screen.getByLabelText("Xem nguồn đợt giao 2 của dòng 1"));

    expect(onOpenSource).toHaveBeenCalledWith("schedule:1", 1);
  });

  it("keeps a line with one date as it was: no schedule list", () => {
    renderLines(order());

    expect(screen.queryByText(/đợt giao/)).toBeNull();
    expect(screen.getByText("16/11/2026").textContent).toBe("16/11/2026");
  });
});

describe("a split line is confirmed per schedule (ticket 35)", () => {
  it("asks a date for each schedule, pre-filled with DW1's suggestion, and sends one per schedule", async () => {
    api.confirm.mockResolvedValue({});
    api.artifacts.mockResolvedValue({
      case_version: 9,
      available: [],
      artifacts: [],
    });
    const crossed = { ...split(), status: "cross_checked", findings: [] };
    render(
      <UiProvider>
        <OrderActions
          order={crossed as ReturnType<typeof order>}
          viewer={PIC}
          sourceOpened
          onChanged={() => {}}
        />
      </UiProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /^Đã gửi xác nhận$/ }));
    expect(screen.getByLabelText("Ngày xác nhận dòng 1 đợt 1")).toBeTruthy();
    expect(screen.getByLabelText("Ngày xác nhận dòng 1 đợt 2")).toBeTruthy();
    expect(screen.queryByLabelText("Ngày xác nhận dòng 1")).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: /^Ghi đã gửi xác nhận$/ }),
    );

    await waitFor(() => expect(api.confirm).toHaveBeenCalledTimes(1));
    const [, body] = api.confirm.mock.calls[0] as [string, unknown];
    expect(body).toEqual({
      case_version: crossed.case_version,
      delivery_dates: [
        { line_no: 1, schedule_dates: ["2026-10-30", "2026-11-30"] },
      ],
    });
  });

  it("shows each schedule's confirmed date on the line", () => {
    const data = split();
    const [line] = data.lines;
    if (line === undefined) throw new Error("no line");
    renderLines({
      ...data,
      lines: [
        {
          ...line,
          schedules: line.schedules.map((s, index) => ({
            ...s,
            confirmed_delivery_date: index === 0 ? "2026-11-02" : "2026-12-04",
          })),
        },
      ],
    });

    const row = screen.getByText("2 đợt giao").closest("tr") as HTMLElement;
    const cells = within(row);
    expect(cells.getByText(/06\/10\/2026 ·/).textContent).toContain(
      "đã xác nhận 02/11/2026",
    );
    expect(cells.getByText(/30\/11\/2026 ·/).textContent).toContain(
      "đã xác nhận 04/12/2026",
    );
    expect(cells.getByText("Đã xác nhận theo 2 đợt")).toBeTruthy();
  });
});
