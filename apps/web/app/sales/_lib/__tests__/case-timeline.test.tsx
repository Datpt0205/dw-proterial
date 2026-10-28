import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

const steps = [
  {
    step_id: "O1",
    procedure: "WIV-03-012",
    coverage: "yes",
    states: ["received"],
    cases: 0,
  },
  {
    step_id: "O4",
    procedure: "WIV-03-012",
    coverage: "suggestion",
    states: [],
    cases: 0,
  },
  {
    step_id: "O7",
    procedure: "WIV-03-012",
    coverage: "yes",
    states: ["prepared", "uploaded_to_bravo"],
    cases: 1,
  },
];
vi.mock("../../_components/sales-frame", () => ({
  useSalesFrame: () => ({ overview: { data: { steps } } }),
}));

import { CaseTimeline } from "../../_components/case-timeline";

afterEach(cleanup);

describe("a case's place in its procedure (2026-10-27)", () => {
  it("titles each step by the states it holds, its WIV code beside", () => {
    render(
      <UiProvider>
        <CaseTimeline
          procedure="WIV-03-012"
          status="uploaded_to_bravo"
          next="Đến lượt Điệu."
        />
      </UiProvider>,
    );
    const list = screen.getByLabelText("Các bước của quy trình");
    expect(within(list).getByText("Đã nhận")).toBeTruthy();
    expect(
      within(list).getByText("PIC đã tự kiểm · Đã nhập Bravo"),
    ).toBeTruthy();
    // The WIV code opens the line under the title, here the current step's.
    expect(within(list).getByText("O7 · Hồ sơ đang ở bước này")).toBeTruthy();
    expect(within(list).getByText("O1")).toBeTruthy();
    // A step that holds no state of its own reads by its coverage.
    expect(within(list).getByText("DW1 gợi ý")).toBeTruthy();
    expect(within(list).getAllByText(/Hồ sơ đang ở bước này/)).toHaveLength(1);
    expect(screen.getByText("Đến lượt Điệu.")).toBeTruthy();
    // Only the case's own step is drawn active, not the first one.
    const active = list.querySelectorAll(".ant-steps-item-active");
    expect(active).toHaveLength(1);
    expect(active[0]!.textContent).toContain("Đã nhập Bravo");
  });
});
