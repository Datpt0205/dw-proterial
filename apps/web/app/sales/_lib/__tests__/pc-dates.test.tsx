import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: "u-1",
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: () => true,
  }),
}));

const readPcDates = vi.fn();
const readPcDatesFromMail = vi.fn();
const pcMails = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ readPcDates, readPcDatesFromMail, pcMails }),
}));

import { PcDatesReader } from "../../orders/[caseId]/pc-dates";

afterEach(() => {
  cleanup();
  [readPcDates, readPcDatesFromMail, pcMails].forEach((m) => m.mockReset());
});

function renderIt(onDates = vi.fn()) {
  if (!pcMails.getMockImplementation())
    pcMails.mockResolvedValue({ mails: [], text_max: 8000 });
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
    readPcDates.mockResolvedValue({
      status: "read",
      dates,
      dropped: 1,
      unsettled: 0,
    });
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

  it("says a date written 03/04 is there for Sales to read, not that PC gave none", async () => {
    readPcDates.mockResolvedValue({
      status: "nothing",
      dates: [],
      dropped: 2,
      unsettled: 1,
    });
    const onDates = renderIt();
    fireEvent.change(
      await screen.findByRole("textbox", { name: "Thư trả lời của PC" }),
      { target: { value: "Dòng 1 giao 03/04/2027" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "DW1 đọc ngày" }));
    const status = await screen.findByRole("status");
    expect(status.textContent).toContain("DW1 không điền được ngày nào.");
    expect(status.textContent).toContain("1 ngày PC viết kiểu 03/04");
    expect(status.textContent).toContain("1 ngày bị bỏ vì không khớp thư");
    expect(status.textContent).not.toContain("không thấy ngày nào");
    expect(onDates).not.toHaveBeenCalled();
  });

  it("holds the paste to the limit the API serves, no copy of its own", async () => {
    // Audit finding 22: the limit's owner is the API (`pc_dates.MAX_TEXT`).
    pcMails.mockResolvedValue({ mails: [], text_max: 1234 });
    renderIt();
    const box = await screen.findByRole("textbox", {
      name: "Thư trả lời của PC",
    });
    await waitFor(() => expect(box.getAttribute("maxlength")).toBe("1234"));
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

  it("lists the verified mails naming the order and reads one of them", async () => {
    const dates = [
      { line_no: 1, delivery: 1, date: "2026-11-10", quote: "10/11/2026" },
    ];
    pcMails.mockResolvedValue({
      mails: [
        {
          message_id: "PC01",
          sender: "pc@proterial.example",
          subject: "Re: ngày giao VLX-PO-2609-0118",
          received_at: "2026-10-28T02:00:00+00:00",
        },
      ],
      text_max: 8000,
    });
    readPcDatesFromMail.mockResolvedValue({
      status: "read",
      dates,
      dropped: 0,
    });
    render(
      <UiProvider>
        <PcDatesReader caseId="c-1" caseVersion={4} onDates={vi.fn()} />
      </UiProvider>,
    );
    fireEvent.click(await screen.findByText(/Thư nêu đơn này \(1\)/));
    expect(await screen.findByText(/pc@proterial.example/)).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "DW1 đọc ngày từ thư này" }),
    );
    expect(
      await screen.findByText(/Đã điền 1 ngày từ thư PC \(máy đọc\)/),
    ).toBeTruthy();
    expect(readPcDatesFromMail).toHaveBeenCalledWith(
      "c-1",
      "PC01",
      4,
      expect.any(String),
    );
    expect(readPcDates).not.toHaveBeenCalled();
  });
});
