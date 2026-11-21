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
const assistantConfirm = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({
    assistantStream,
    assistantConversation,
    assistantConfirm,
  }),
}));

import { useMemo } from "react";
import {
  WithCaseChat,
  useCaseChatDecided,
  useCaseChatOffers,
  type CaseOffers,
} from "../../_components/case-chat";

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
  [assistantStream, assistantConversation, assistantConfirm].forEach((m) =>
    m.mockReset(),
  );
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

/** A case page registering its own controls, as the order page does. */
function Page({ offers }: { offers: CaseOffers }) {
  const memo = useMemo(() => offers, [offers]);
  useCaseChatOffers(memo);
  return <p>Nội dung hồ sơ</p>;
}

const OFFERS: CaseOffers = {
  thread_summary: <button type="button">DW1 tóm tắt</button>,
};

describe("A step asked of the case offers the page's own control (ticket 46)", () => {
  it("draws the control the page registered under the answer", async () => {
    widthOf(1280);
    assistantConversation.mockResolvedValue({
      case: { kind: "order", case_id: CASE, label: "PO NRV-PO-26-0457" },
      turns: [
        {
          ...TURN,
          question: "Tóm tắt chuỗi thư",
          kind: "explain_thread",
          answer: "Bấm nút dưới đây để DW1 tóm tắt chuỗi thư của hồ sơ này.",
          offer: "thread_summary",
        },
        {
          ...TURN,
          seq: 2,
          question: "Nhắc khách",
          kind: "remind_customer",
          answer: "Bấm nút dưới đây để DW1 soạn thư nhắc khách.",
          offer: "customer_reminder",
        },
      ],
    });
    render(
      <UiProvider>
        <WithCaseChat onCase={ON_CASE}>
          <Page offers={OFFERS} />
        </WithCaseChat>
      </UiProvider>,
    );
    await screen.findByRole("complementary", { name: "Hỏi DW1 về hồ sơ này" });
    await screen.findByRole("button", { name: "DW1 tóm tắt" });
    // The page draws no reminder at this point of the case: the chat says so
    // instead of drawing one of its own.
    expect(
      screen.getByText(
        "Ở bước hiện tại, trang hồ sơ không có nút cho việc này.",
      ),
    ).toBeTruthy();
  });
});

const HASH = "ab12cd34".repeat(8);
const STATED = {
  ...TURN,
  seq: 2,
  kind: "decide_finding",
  question: "chấp nhận cờ ngày giao, khách đồng ý",
  answer:
    "DW1 sẽ ghi cho cờ requested_date_short_lt (dòng 3): chấp nhận (lý do: khách đồng ý). Bấm Xác nhận để ghi; DW1 không ghi gì khi chưa xác nhận.",
  proposal: {
    finding_key: "requested_date_short_lt:3",
    decision: "accepted",
    reason: "khách đồng ý",
    case_version: 4,
    content_hash: HASH,
  },
};

/** A case page that reloads when the chat records a decision. */
function Reloading({ reload }: { reload: () => void }) {
  useCaseChatDecided(reload);
  return <p>Nội dung hồ sơ</p>;
}

describe("A flag decided in the case's conversation (ticket 56)", () => {
  it("records nothing until confirmed, then sends the statement's hash and reloads the page", async () => {
    widthOf(1280);
    assistantConversation.mockResolvedValue({
      case: { kind: "order", case_id: CASE, label: "PO NRV-PO-26-0457" },
      turns: [STATED],
    });
    assistantConfirm.mockResolvedValue({
      answer: "Đã ghi cho cờ requested_date_short_lt (dòng 3): chấp nhận.",
      case_version: 5,
    });
    const reload = vi.fn();
    render(
      <UiProvider>
        <WithCaseChat onCase={ON_CASE}>
          <Reloading reload={reload} />
        </WithCaseChat>
      </UiProvider>,
    );
    expect(await screen.findByText(STATED.answer)).toBeTruthy();
    // What is confirmed is shown: the case's version and the hash.
    expect(screen.getByText(/Hồ sơ phiên bản 4/)).toBeTruthy();
    expect(screen.getByText(HASH.slice(0, 8))).toBeTruthy();
    expect(assistantConfirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Xác nhận" }));
    await waitFor(() => expect(assistantConfirm).toHaveBeenCalledTimes(1));
    expect(assistantConfirm.mock.calls[0]!.slice(0, 3)).toEqual([
      ON_CASE,
      2,
      HASH,
    ]);
    expect(
      await screen.findByText(
        "Đã ghi cho cờ requested_date_short_lt (dòng 3): chấp nhận.",
      ),
    ).toBeTruthy();
    expect(reload).toHaveBeenCalled();
    // Recorded once: the button does not send it again.
    expect(
      (screen.getByRole("button", { name: "Xác nhận" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
  }, 30_000);
});
