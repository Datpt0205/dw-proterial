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

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/sales/assistant",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const assistantStream = vi.fn();
const assistantConversation = vi.fn();
const assistantCases = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ assistantStream, assistantConversation, assistantCases }),
}));

import AssistantPage from "../../assistant/page";

const CASE = "ca5e0000-0000-4000-8000-000000000001";
const LINKED = {
  seq: 1,
  asked_at: "2026-10-30T03:00:00+00:00",
  question: "PO NRV-PO-26-0457 tới đâu rồi?",
  kind: "order_status",
  answer: "PO NRV-PO-26-0457: hỏi trong cuộc trò chuyện của hồ sơ này.",
  cites: [{ kind: "order", case_id: CASE, label: "PO NRV-PO-26-0457" }],
  answered_by: "code",
};

afterEach(() => {
  cleanup();
  [assistantStream, assistantConversation, assistantCases].forEach((m) =>
    m.mockReset(),
  );
});

function renderIt(recent: unknown[] = [], turns: unknown[] = []): void {
  assistantCases.mockResolvedValue(recent);
  assistantConversation.mockResolvedValue({ case: null, turns });
  render(
    <UiProvider>
      <AssistantPage />
    </UiProvider>,
  );
}

describe("Hỏi đáp DW1 (ADR 0007, ticket 46)", () => {
  it("opens the person's one general conversation, with no session to create or pick", async () => {
    renderIt();
    expect(screen.getAllByText(/không có số tiền/).length).toBeGreaterThan(0);
    expect(await screen.findByText(/Chưa hỏi hồ sơ nào/)).toBeTruthy();
    expect(assistantConversation).toHaveBeenCalledWith(null);
    expect(screen.queryByText("Phiên mới")).toBeNull();
  });

  it("lists the cases talked about, an unseen answer marked in words", async () => {
    renderIt([
      {
        case: { kind: "quote", case_id: CASE, label: "Yêu cầu báo giá R-1" },
        last_turn_at: "2026-10-30T03:00:00+00:00",
        unread: true,
      },
    ]);
    const link = await screen.findByRole("link", {
      name: /Yêu cầu báo giá R-1/,
    });
    expect(link.getAttribute("href")).toBe(`/sales/quotes/${CASE}`);
    expect(screen.getByText(/Có trả lời chưa xem/)).toBeTruthy();
  });

  it("asks on Enter in the general conversation and links the case it names", async () => {
    assistantStream.mockResolvedValue({ turn: LINKED });
    renderIt();
    const box = await screen.findByRole("textbox", { name: "Câu hỏi cho DW1" });
    fireEvent.change(box, { target: { value: LINKED.question } });
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(assistantStream).toHaveBeenCalledTimes(1));
    expect(assistantStream.mock.calls[0]!.slice(0, 2)).toEqual([
      LINKED.question,
      null,
    ]);
    const link = await screen.findByRole("link", { name: "PO NRV-PO-26-0457" });
    expect(link.getAttribute("href")).toBe(`/sales/orders/${CASE}`);
    // The list of cases talked about is read again.
    await waitFor(() => expect(assistantCases).toHaveBeenCalledTimes(2));
  });

  it("sends nothing while a word is still being composed, nor on Shift+Enter", async () => {
    renderIt();
    const box = await screen.findByRole("textbox", { name: "Câu hỏi cho DW1" });
    fireEvent.change(box, { target: { value: "PO đó" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(assistantStream).not.toHaveBeenCalled();
  });
});
