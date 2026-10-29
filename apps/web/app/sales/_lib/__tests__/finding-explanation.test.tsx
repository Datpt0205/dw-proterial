import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

const explainFinding = vi.fn();
vi.mock("../api", () => ({ salesApi: () => ({ explainFinding }) }));

import { FindingExplanation } from "../../orders/[caseId]/findings";

afterEach(() => {
  cleanup();
  explainFinding.mockReset();
});

function renderIt() {
  render(
    <UiProvider>
      <FindingExplanation caseId="c-1" findingKey="price_mismatch:2" />
    </UiProvider>,
  );
}

describe("DW1 giải thích (AI item 12)", () => {
  it("asks for the finding's explanation and shows it as the machine's words", async () => {
    explainFinding.mockResolvedValue({
      finding_key: "price_mismatch:2",
      status: "explained",
      explanation: "Đơn giá trên PO là 0.75, báo giá Q26-0104 ghi 0.712.",
      check: "Kiểm báo giá Q26-0104.",
      prompt_ref: "sales.finding_explanation@1.0.0",
      model_profile: "onprem",
    });
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: "DW1 giải thích" }));
    expect(await screen.findByText(/báo giá Q26-0104 ghi 0.712/)).toBeTruthy();
    expect(screen.getByText("Máy viết")).toBeTruthy();
    expect(screen.getByText("Nên kiểm: Kiểm báo giá Q26-0104.")).toBeTruthy();
    expect(explainFinding).toHaveBeenCalledWith("c-1", "price_mismatch:2");
  });

  it("says why there is none when the answer was refused", async () => {
    explainFinding.mockResolvedValue({
      finding_key: "price_mismatch:2",
      status: "refused",
      explanation: null,
      check: null,
      prompt_ref: "sales.finding_explanation@1.0.0",
      model_profile: "onprem",
    });
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: "DW1 giải thích" }));
    expect(await screen.findByText(/con số không có trong hồ sơ/)).toBeTruthy();
  });
});
