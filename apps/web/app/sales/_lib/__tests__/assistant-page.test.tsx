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

const nav = vi.hoisted(() => {
  const listeners = new Set<() => void>();
  let current = new URLSearchParams();
  return {
    reset() {
      current = new URLSearchParams();
    },
    get: () => current,
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => void listeners.delete(listener);
    },
    replace: vi.fn((url: string) => {
      current = new URLSearchParams(url.split("?")[1] ?? "");
      listeners.forEach((l) => l());
    }),
  };
});
vi.mock("next/navigation", async () => {
  const { useSyncExternalStore } = await import("react");
  return {
    useSearchParams: () => useSyncExternalStore(nav.subscribe, nav.get),
    usePathname: () => "/sales/assistant",
    useRouter: () => ({ push: vi.fn(), replace: nav.replace, back: vi.fn() }),
  };
});

const assistantStream = vi.fn();
const assistantSessions = vi.fn();
const assistantSession = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ assistantStream, assistantSessions, assistantSession }),
}));

import AssistantPage from "../../assistant/page";

const SESSION = "5e55e55e-0000-4000-8000-000000000001";
const CASE = "ca5e0000-0000-4000-8000-000000000001";
const TURN = {
  seq: 1,
  asked_at: "2026-10-30T03:00:00+00:00",
  question: "PO NRV-PO-26-0457 tới đâu rồi?",
  kind: "order_status",
  answer: "PO NRV-PO-26-0457 đang chờ PIC tự kiểm.",
  cites: [{ kind: "order", case_id: CASE, label: "PO NRV-PO-26-0457" }],
  answered_by: "model",
};

afterEach(() => {
  cleanup();
  nav.reset();
  [assistantStream, assistantSessions, assistantSession, nav.replace].forEach(
    (m) => m.mockReset(),
  );
});

function renderIt() {
  assistantSessions.mockResolvedValue([]);
  assistantSession.mockResolvedValue({
    session_id: SESSION,
    title: TURN.question,
    created_at: TURN.asked_at,
    last_turn_at: TURN.asked_at,
    turns: [TURN],
  });
  render(
    <UiProvider>
      <AssistantPage />
    </UiProvider>,
  );
}

describe("Hỏi đáp DW1 (ADR 0007)", () => {
  it("says what DW1 answers before anyone asks, and that no session exists yet", async () => {
    renderIt();
    expect(screen.getByText(/không có số tiền/)).toBeTruthy();
    expect(await screen.findByText(/Chưa có phiên nào/)).toBeTruthy();
  });

  it("asks on Enter, shows the answer marked as the machine's with its case, and opens the session", async () => {
    assistantStream.mockResolvedValue({ session_id: SESSION, turn: TURN });
    renderIt();
    const box = screen.getByRole("textbox", { name: "Câu hỏi cho DW1" });
    fireEvent.change(box, { target: { value: TURN.question } });
    fireEvent.keyDown(box, { key: "Enter" });
    await waitFor(() => expect(assistantStream).toHaveBeenCalledTimes(1));
    expect(assistantStream.mock.calls[0]!.slice(0, 2)).toEqual([
      TURN.question,
      null,
    ]);
    expect(nav.replace).toHaveBeenCalledWith(
      `/sales/assistant?session=${SESSION}`,
    );
    expect(await screen.findByText("Máy viết")).toBeTruthy();
    const link = screen.getByRole("link", { name: "PO NRV-PO-26-0457" });
    expect(link.getAttribute("href")).toBe(`/sales/orders/${CASE}`);
  });

  it("sends nothing while a word is still being composed, nor on Shift+Enter", () => {
    renderIt();
    const box = screen.getByRole("textbox", { name: "Câu hỏi cho DW1" });
    fireEvent.change(box, { target: { value: "PO đó" } });
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
    expect(assistantStream).not.toHaveBeenCalled();
  });
});
