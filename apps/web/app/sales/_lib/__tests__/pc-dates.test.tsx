import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

const readPcDates = vi.fn();
vi.mock("../api", () => ({ salesApi: () => ({ readPcDates }) }));

import { PcDatesReader } from "../../orders/[caseId]/pc-dates";

afterEach(() => {
  cleanup();
  readPcDates.mockReset();
});

function renderIt(onDates = vi.fn()) {
  render(
    <UiProvider>
      <PcDatesReader caseId="c-1" caseVersion={4} onDates={onDates} />
    </UiProvider>,
  );
  fireEvent.click(screen.getByText("Dán thư trả lời của PC để DW1 điền ngày"));
  return onDates;
}

describe("DW1 đọc ngày giao trong thư PC (AI item 7)", () => {
  it("hands the dates read to the form and says how many, as the machine's", async () => {
    const dates = [
      { line_no: 1, delivery: 1, date: "2026-11-10", quote: "10/11/2026" },
    ];
    readPcDates.mockResolvedValue({ status: "read", dates, dropped: 1 });
    const onDates = renderIt();
    fireEvent.change(
      await screen.findByRole("textbox", { name: "Thư trả lời của PC" }),
      { target: { value: "Dòng 1: 10/11/2026" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "DW1 đọc ngày" }));
    expect(
      await screen.findByText(/Đã điền 1 ngày từ thư PC \(máy đọc\)/),
    ).toBeTruthy();
    expect(screen.getByText(/1 ngày bị bỏ/)).toBeTruthy();
    expect(onDates).toHaveBeenCalledWith(dates);
    expect(readPcDates).toHaveBeenCalledWith(
      "c-1",
      4,
      "Dòng 1: 10/11/2026",
      expect.any(String),
    );
  });

  it("fills nothing when the mail gives no date", async () => {
    readPcDates.mockResolvedValue({ status: "nothing", dates: [], dropped: 0 });
    const onDates = renderIt();
    fireEvent.change(
      await screen.findByRole("textbox", { name: "Thư trả lời của PC" }),
      { target: { value: "PC sẽ báo sau" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "DW1 đọc ngày" }));
    expect(await screen.findByText(/không thấy ngày nào/)).toBeTruthy();
    expect(onDates).not.toHaveBeenCalled();
  });
});
