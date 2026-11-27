import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { SalesSchemas } from "@dw/api-client";
import { AN, order } from "./fixtures";

type Order = SalesSchemas["OrderCaseView"];

let SCOPES = ["sales.case.read", "sales.order.prepare"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => SCOPES.includes(scope),
  }),
}));

const api = {
  pcMails: vi.fn(async () => ({ mails: [], text_max: 4321 })),
  readInternalChange: vi.fn(),
  applyInternalChange: vi.fn(async () => ({
    case_kind: "order",
    case_id: "c",
    case_version: 9,
    status: "change_review",
  })),
};
vi.mock("../api", () => ({ salesApi: () => api }));

import { InternalChangePanel } from "../../orders/[caseId]/internal-change";

afterEach(() => {
  cleanup();
  api.readInternalChange.mockReset();
  api.applyInternalChange.mockClear();
  SCOPES = ["sales.case.read", "sales.order.prepare"];
});

function page(shown: Order) {
  return render(
    <UiProvider>
      <InternalChangePanel
        order={shown}
        viewer={{
          principalId: AN,
          hasScope: (s: string) => SCOPES.includes(s),
        }}
        onChanged={vi.fn()}
      />
    </UiProvider>,
  );
}

const confirmed = () =>
  order({
    status: "confirmation_sent",
    case_version: 8,
    internal_change_open: true,
  });

describe("Thay đổi nội bộ (ticket 10)", () => {
  it("is offered only where the server says the order takes one", () => {
    page(order({ status: "in_review", internal_change_open: false }));
    expect(screen.queryByText("Thay đổi nội bộ")).toBeNull();
  });

  it("says why a caller without the PIC's scope cannot open it", () => {
    SCOPES = ["sales.case.read"];
    page(confirmed());
    const button = screen
      .getAllByText("Thay đổi nội bộ", { selector: "button span" })[0]!
      .closest("button") as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it("fills the form from PC's mail as the machine's, shows refused lines, and changes nothing until applied", async () => {
    api.readInternalChange.mockResolvedValue({
      status: "read",
      dropped: 0,
      text_max: 4321,
      prompt_ref: "sales.internal_change@1.0.0",
      model_profile: "onprem",
      lines: [
        {
          line_no: 1,
          words: "Dòng 1",
          held_quantity: "6100",
          uom: "m",
          held_deliveries: [],
          deliveries: [
            {
              quantity: "6100",
              date: null,
              quantity_words: "6100",
              date_words: "03/12",
            },
          ],
          problem: "unread",
        },
        {
          line_no: null,
          words: "Dòng 7",
          deliveries: [],
          held_deliveries: [],
          problem: "no_such_line",
        },
      ],
    });
    page(confirmed());
    fireEvent.click(
      screen
        .getAllByText("Thay đổi nội bộ", { selector: "button span" })[0]!
        .closest("button") as HTMLButtonElement,
    );
    fireEvent.click(await screen.findByText("Dán thư PC để DW1 điền các dòng"));
    const box = await screen.findByRole("textbox", {
      name: "Thư PC đổi lịch giao",
    });
    await waitFor(() => expect(box.getAttribute("maxlength")).toBe("4321"));
    fireEvent.change(box, {
      target: { value: "Dòng 1: 03/12. Dòng 7: 05/12" },
    });
    fireEvent.click(screen.getByRole("button", { name: "DW1 đọc thư PC" }));

    expect(
      await screen.findByText(/Đã điền 1 dòng từ thư PC \(máy đọc\)/),
    ).toBeTruthy();
    expect(screen.getByText("Cần nhập: thư chưa rõ")).toBeTruthy();
    expect(screen.getByText("Dòng 7")).toBeTruthy();
    expect(api.readInternalChange).toHaveBeenCalledWith(
      order().case_id,
      8,
      "Dòng 1: 03/12. Dòng 7: 05/12",
      expect.any(String),
    );
    // The date the mail left open is a person's: "Áp dụng" is refused by
    // the form, and nothing is sent.
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng" }));
    expect(await screen.findByText(/cần sửa/)).toBeTruthy();
    expect(api.applyInternalChange).not.toHaveBeenCalled();
  });

  it("applies a line PC cancels whole as a cancel with no delivery, and offers no line already cancelled", async () => {
    const shown = confirmed();
    const held = shown.lines[0]!;
    page({
      ...shown,
      lines: [held, { ...held, line_no: 2, cancelled: true }],
    });
    fireEvent.click(
      screen
        .getAllByText("Thay đổi nội bộ", { selector: "button span" })[0]!
        .closest("button") as HTMLButtonElement,
    );
    const [reason, line] = await screen.findAllByRole("combobox");
    fireEvent.mouseDown(reason!);
    fireEvent.click(await screen.findByText("Thiếu hàng, vật tư"));
    fireEvent.mouseDown(line!);
    expect(await screen.findByText("Dòng 1: BRN-W-0007")).toBeTruthy();
    expect(screen.queryByText("Dòng 2: BRN-W-0007")).toBeNull();
    fireEvent.click(screen.getByText("Dòng 1: BRN-W-0007"));
    fireEvent.click(screen.getByRole("checkbox", { name: "PC hủy cả dòng" }));
    // A cancelled line asks for no delivery.
    await waitFor(() => expect(screen.queryByText("Thêm một đợt")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng" }));
    const asked = await waitFor(() => {
      const found = document.querySelector(".ant-modal-confirm");
      expect(found).toBeTruthy();
      return found!;
    });
    expect(asked.textContent).toContain("1 dòng hủy cả");
    fireEvent.click(
      Array.from(asked.querySelectorAll("button")).find(
        (b) => b.textContent === "Áp dụng",
      )!,
    );
    await waitFor(() => expect(api.applyInternalChange).toHaveBeenCalled());
    expect(api.applyInternalChange).toHaveBeenCalledWith(
      shown.case_id,
      {
        case_version: 8,
        reason: "short_stock",
        lines: [{ line_no: 1, cancelled: true, deliveries: [] }],
      },
      expect.any(String),
    );
  });
});
