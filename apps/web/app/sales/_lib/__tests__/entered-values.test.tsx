import { cleanup, render, screen, within } from "@testing-library/react";
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
const AT = "2026-10-02T02:00:00Z";

/** The fixture's line 1 with the given values typed by Sales (ticket 15). */
function corrected(values: Record<string, string>) {
  const base = order();
  const [line] = base.lines;
  if (line === undefined) throw new Error("the fixture order has no line");
  return order({
    lines: [
      {
        ...line,
        corrections: Object.entries(values).map(([field, value]) => ({
          field,
          value,
          by: AN,
          at: AT,
        })),
      },
    ],
  });
}

function row(data: ReturnType<typeof order>) {
  render(
    <UiProvider>
      <LinesTable
        order={data}
        viewer={PIC}
        onChanged={() => {}}
        onOpenSource={() => {}}
        onPickCode={() => {}}
      />
    </UiProvider>,
  );
  return within(
    screen.getByRole("button", { name: "Xem nguồn dòng 1" }).closest("tr")!,
  );
}

afterEach(cleanup);

describe("the lines table shows each line as it is entered (ticket 15)", () => {
  it("shows a corrected item code, description and unit beside the value as read", () => {
    const cells = row(
      corrected({
        customer_item_code: "BRN-W-0070",
        description: "HOOK-UP WIRE 1C AWG22",
        uom: "roll",
      }),
    );

    expect(cells.getByText("BRN-W-0070")).toBeTruthy();
    expect(cells.getByText("Đọc được: BRN-W-0007")).toBeTruthy();
    expect(cells.getByText("HOOK-UP WIRE 1C AWG22")).toBeTruthy();
    expect(cells.getByText("HOOK-UP WIRE 1C AWG24")).toBeTruthy();
    // The quantity is untouched, its unit is the one typed, and the value as
    // read keeps the unit it was read with.
    expect(cells.getByText("6.100 roll")).toBeTruthy();
    expect(cells.getByText("6.100 m")).toBeTruthy();
  }, 20_000);

  it("prints a split line's delivery quantities in the unit as entered", () => {
    const base = corrected({ uom: "roll" });
    const [line] = base.lines;
    if (line === undefined) throw new Error("the fixture order has no line");
    const [first] = line.schedules;
    if (first === undefined) throw new Error("the fixture line has no date");
    const cells = row(
      order({
        lines: [
          {
            ...line,
            printed_schedules: true,
            schedules: [
              { ...first, quantity: "4000" },
              { ...first, quantity: "2100", requested_date: "2026-12-01" },
            ],
          },
        ],
      }),
    );

    expect(cells.getByText("2 đợt giao")).toBeTruthy();
    expect(cells.getByText("4.000 roll")).toBeTruthy();
    expect(cells.getByText("2.100 roll")).toBeTruthy();
    expect(cells.queryByText("4.000 m")).toBeNull();
  }, 20_000);

  it("shows a line nobody corrected as read, with nothing under it", () => {
    const cells = row(order());

    expect(cells.getByText("BRN-W-0007")).toBeTruthy();
    expect(cells.getByText("6.100 m")).toBeTruthy();
    expect(cells.queryByText(/Đọc được/)).toBeNull();
  }, 20_000);
});
