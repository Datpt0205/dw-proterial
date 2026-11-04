import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssistantChat, UiProvider } from "@dw/ui";

afterEach(cleanup);

function draw(pending: boolean) {
  render(
    <UiProvider>
      <AssistantChat
        worker="DW2"
        examples={["Việc của tôi là gì?"]}
        turns={[]}
        pending={pending}
        question="PR-2611-030 tới đâu rồi?"
        onQuestion={vi.fn()}
        onAsk={vi.fn()}
        maxLength={500}
      />
    </UiProvider>,
  );
}

describe("the chat frame while a first question is answered", () => {
  it("shows the question asked and that the worker is answering", () => {
    draw(true);
    const list = screen.getByRole("list", { name: "Các lượt hỏi đáp" });
    expect(list.textContent).toContain("PR-2611-030 tới đâu rồi?");
    expect(screen.getByRole("status").textContent).toBe("DW2 đang trả lời…");
    expect(screen.queryByText("Thử hỏi")).toBeNull();
  });

  it("welcomes with examples before anything is asked", () => {
    draw(false);
    expect(screen.getByText("Thử hỏi")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });
});
