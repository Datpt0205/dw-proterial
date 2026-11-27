import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

let scopes: string[] = ["sales.case.read"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/sales/inbox",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

const assistantStream = vi.fn();
const assistantConversation = vi.fn();
const assistantCases = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ assistantStream, assistantConversation, assistantCases }),
}));

import {
  AssistantWidget,
  useHideAssistantWidget,
} from "../../_components/assistant-widget";

const CASE = "ca5e0000-0000-4000-8000-000000000001";

afterEach(() => {
  cleanup();
  scopes = ["sales.case.read"];
  [assistantStream, assistantConversation, assistantCases].forEach((m) =>
    m.mockReset(),
  );
});

/** A page that draws a conversation of its own, mounted until toggled off. */
function OwnChat() {
  useHideAssistantWidget();
  return <p>Trang có cuộc trò chuyện riêng</p>;
}

function Page({ ownChat = false }: { ownChat?: boolean }) {
  const [mounted, setMounted] = useState(ownChat);
  return (
    <>
      {mounted ? <OwnChat /> : null}
      <button type="button" onClick={() => setMounted((m) => !m)}>
        đổi trang
      </button>
    </>
  );
}

function draw(ownChat = false) {
  assistantConversation.mockResolvedValue({ case: null, turns: [] });
  assistantCases.mockResolvedValue([
    {
      case: { kind: "order", case_id: CASE, label: "PO NRV-PO-26-0457" },
      last_turn_at: "2026-11-26T03:00:00+00:00",
      unread: true,
    },
  ]);
  assistantStream.mockReturnValue(new Promise(() => {}));
  render(
    <UiProvider>
      <AssistantWidget>
        <Page ownChat={ownChat} />
      </AssistantWidget>
    </UiProvider>,
  );
}

const widget = () => screen.queryByRole("button", { name: "Hỏi DW1" });

describe("the Hỏi DW1 widget (Đạt, 2026-11-26)", () => {
  it("opens on the person's sessions: greeting, the general one and each case asked about", async () => {
    draw();
    expect(assistantCases).not.toHaveBeenCalled();
    fireEvent.click(widget()!);
    expect(await screen.findByText("Xin chào, An!")).toBeTruthy();
    const kept = await screen.findByRole("link", { name: /PO NRV-PO-26-0457/ });
    expect(kept.getAttribute("href")).toBe(`/sales/orders/${CASE}`);
    expect(kept.textContent).toContain("Có trả lời chưa xem");
    expect(
      screen.getByRole("link", { name: "Xem tất cả" }).getAttribute("href"),
    ).toBe("/sales/assistant");
  });

  it("goes to the general conversation from the sessions", async () => {
    draw();
    fireEvent.click(widget()!);
    fireEvent.click(
      await screen.findByRole("button", { name: "Đặt câu hỏi cho DW1" }),
    );
    await waitFor(() =>
      expect(assistantConversation).toHaveBeenCalledWith(null),
    );
    expect(
      await screen.findByRole("textbox", { name: "Câu hỏi cho DW1" }),
    ).toBeTruthy();
  });

  it("asks a suggested question at once, in the general conversation", async () => {
    draw();
    fireEvent.click(widget()!);
    fireEvent.click(
      await screen.findByRole("button", { name: /Có việc nào quá hạn không/ }),
    );
    await waitFor(() => expect(assistantStream).toHaveBeenCalledOnce());
    expect(assistantStream.mock.calls[0]![0]).toBe(
      "Có việc nào quá hạn không?",
    );
    expect(assistantStream.mock.calls[0]![1]).toBeNull();
  });

  it("is not drawn for someone who does not read cases", () => {
    scopes = ["sales.overview.read"];
    draw();
    expect(widget()).toBeNull();
  });

  it("hides while a page draws its own conversation, and comes back after", () => {
    draw(true);
    expect(widget()).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "đổi trang" }));
    expect(widget()).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "đổi trang" }));
    expect(widget()).toBeNull();
  });
});
