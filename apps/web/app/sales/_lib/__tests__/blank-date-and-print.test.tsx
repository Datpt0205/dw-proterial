import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
import { PrintCopyNotice } from "../../orders/[caseId]/print-copy";

const PIC = { principalId: AN, hasScope: () => true };

/** M44's line 2 (ticket 34): printed with no requested date. */
function dateToFollow() {
  const base = order();
  const [line] = base.lines;
  if (line === undefined) throw new Error("the fixture order has no line");
  return order({
    lines: [{ ...line, requested_date: null, schedules: [] }],
  });
}

/** M45 (ticket 34): the workbook, with its PDF print showing line 1's date otherwise. */
function withPrint() {
  const base = order();
  const at = base.header_anchors.po_no;
  if (at === undefined) throw new Error("the fixture order has no PO anchor");
  return order({
    print_copy: {
      attachment_id: "M45-A2",
      differences: [
        {
          line_no: 1,
          field: "requested_date",
          anchor: { ...at, attachment_id: "M45-A2", quote: "23/11/2026" },
          ours: "2026-11-16",
          theirs: "2026-11-23",
        },
      ],
    },
  });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("a line printed with no date (ticket 34)", () => {
  it("reads as date to follow, never as an unknown date", () => {
    render(
      <UiProvider>
        <LinesTable
          order={dateToFollow()}
          viewer={PIC}
          onChanged={() => {}}
          onOpenSource={() => {}}
          onPickCode={() => {}}
        />
      </UiProvider>,
    );
    expect(screen.getByText("Báo sau")).toBeTruthy();
    expect(screen.queryByText("Không rõ")).toBeNull();
  }, 20_000);
});

describe("two files of one PO (tickets 34 and 22)", () => {
  it("says the second file differs, with both values, and opens it where it does", () => {
    const onOpenSource = vi.fn();
    render(
      <UiProvider>
        <PrintCopyNotice order={withPrint()} onOpenSource={onOpenSource} />
      </UiProvider>,
    );
    expect(
      screen.getByText(
        "Cùng PO có tệp thứ hai (M45-A2): 1 giá trị ghi khác tệp M03-A1.",
      ),
    ).toBeTruthy();
    // Neither file wins: both values, each as its file prints it.
    expect(screen.getByText(/16\/11\/2026 \/ 23\/11\/2026/)).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", {
        name: "Xem trên tệp thứ hai: Dòng 1: Ngày yêu cầu",
      }),
    );
    expect(onOpenSource).toHaveBeenCalledWith("print:0", null);
  }, 20_000);

  it("shows nothing for an order with no print", () => {
    const { container } = render(
      <UiProvider>
        <PrintCopyNotice order={order()} onOpenSource={() => {}} />
      </UiProvider>,
    );
    expect(container.textContent).toBe("");
  }, 20_000);
});
