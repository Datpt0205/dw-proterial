import {
  cleanup,
  fireEvent,
  render,
  screen,
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
vi.mock("../api", () => ({ salesApi: () => ({}) }));

import { LinesTable } from "../../orders/[caseId]/lines";

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
          },
          {
            quantity: "1000",
            requested_date: "2026-11-30",
            anchor: at,
            suggested_delivery_date: "2026-11-30",
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
