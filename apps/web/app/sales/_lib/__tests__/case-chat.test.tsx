import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scope === "sales.case.read",
  }),
}));

const assistantStream = vi.fn();
const assistantConversation = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ assistantStream, assistantConversation }),
}));

import { WithCaseChat } from "../../_components/case-chat";

const CASE = "ca5e0000-0000-4000-8000-000000000001";
const ON_CASE = { kind: "order" as const, caseId: CASE };
const TURN = {
  seq: 1,
  asked_at: "2026-10-30T03:00:00+00:00",
  question: "Hồ sơ này đang ở bước nào?",
  kind: "order_status",
  answer: "PO NRV-PO-26-0457 (rev 0) của khách NRV: Chờ PIC tự kiểm.",
  cites: [{ kind: "order", case_id: CASE, label: "PO NRV-PO-26-0457" }],
  answered_by: "code",
};

const original = window.matchMedia;

/** A screen ``width`` px wide, as antd's breakpoints ask it. */
function widthOf(width: number) {
  window.matchMedia = ((query: string) => {
    const min = /min-width:\s*(\d+)px/.exec(query);
    const max = /max-width:\s*(\d+)px/.exec(query);
    const matches =
      (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]));
    return {
      matches,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    };
  }) as typeof window.matchMedia;
}

afterEach(() => {
  cleanup();
  window.matchMedia = original;
  [assistantStream, assistantConversation].forEach((m) => m.mockReset());
});

function renderIt(turns: unknown[] = []) {
  assistantConversation.mockResolvedValue({
    case: { kind: "order", case_id: CASE, label: "PO NRV-PO-26-0457" },
    turns,
  });
  render(
    <UiProvider>
      <WithCaseChat onCase={ON_CASE}>
        <p>Nội dung hồ sơ</p>
      </WithCaseChat>
    </UiProvider>,
  );
}

describe("The case is its conversation (ticket 46)", () => {
  it("sits open beside the case on a desktop, the case's own conversation", async () => {
    widthOf(1280);
    renderIt([TURN]);
    expect(screen.getByText("Nội dung hồ sơ")).toBeTruthy();
    expect(
      screen.getByRole("complementary", { name: "Hỏi DW1 về hồ sơ này" }),
    ).toBeTruthy();
    expect(await screen.findByText(TURN.answer)).toBeTruthy();
    expect(assistantConversation).toHaveBeenCalledWith(ON_CASE);
    // No session to make, none to pick.
    expect(screen.queryByText("Phiên mới")).toBeNull();
  });

  it("asks in the case's conversation, never a general one", async () => {
    widthOf(1280);
    assistantStream.mockResolvedValue({ turn: TURN });
    renderIt();
    const box = await screen.findByRole("textbox", { name: "Câu hỏi cho DW1" });
    fireEvent.change(box, { target: { value: TURN.question } });
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(assistantStream).toHaveBeenCalledTimes(1));
    expect(assistantStream.mock.calls[0]!.slice(0, 2)).toEqual([
      TURN.question,
      ON_CASE,
    ]);
  });

  it("is a button on a phone, read only once opened as a bottom sheet", async () => {
    widthOf(390);
    renderIt([TURN]);
    expect(screen.getByText("Nội dung hồ sơ")).toBeTruthy();
    expect(screen.queryByRole("complementary")).toBeNull();
    // Opening the case does not read the conversation, so nothing is marked
    // seen that nobody saw.
    expect(assistantConversation).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Hỏi DW1 về hồ sơ này" }),
    );
    expect(await screen.findByText(TURN.answer)).toBeTruthy();
    expect(assistantConversation).toHaveBeenCalledWith(ON_CASE);
  });
});
