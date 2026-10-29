import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

const threadSummary = vi.fn();
vi.mock("../api", () => ({ salesApi: () => ({ threadSummary }) }));

import { ThreadSummary } from "../../_components/thread-summary";

afterEach(() => {
  cleanup();
  threadSummary.mockReset();
});

function renderIt() {
  render(
    <UiProvider>
      <ThreadSummary kind="order" caseId="c-1" />
    </UiProvider>,
  );
}

const BASE = {
  case_id: "c-1",
  mails: 3,
  dropped: 0,
  points: [],
  prompt_ref: "sales.thread_summary@1.0.0",
  model_profile: "onprem",
};

describe("Tóm tắt chuỗi thư (AI item 8)", () => {
  it("shows each point with links to the mails it cites, as the machine's", async () => {
    threadSummary.mockResolvedValue({
      ...BASE,
      status: "summarized",
      dropped: 1,
      points: [{ text: "Khách gửi bản sửa Rev.1.", cites: ["M07"] }],
    });
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: "DW1 tóm tắt" }));
    expect(await screen.findByText(/Khách gửi bản sửa Rev\.1\./)).toBeTruthy();
    expect(screen.getByText("Máy viết")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Mở thư M07" }).getAttribute("href"),
    ).toBe("/sales/inbox?message=M07");
    expect(screen.getByText(/1 ý bị bỏ vì không khớp thư được trích/)).toBeTruthy();
    expect(threadSummary).toHaveBeenCalledWith("order", "c-1");
  });

  it("says why there is none when no point was kept", async () => {
    threadSummary.mockResolvedValue({ ...BASE, status: "refused", dropped: 2 });
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: "DW1 tóm tắt" }));
    expect(await screen.findByText(/không khớp thư trong hồ sơ/)).toBeTruthy();
    expect(screen.queryByText("Máy viết")).toBeNull();
  });
});
