import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AssistantChat, UiProvider, type ChatLive } from "@dw/ui";
import { liveAfter, NOTHING_YET } from "../../lib/chat-live";

afterEach(cleanup);

function draw(pending: boolean, live: ChatLive | null = null) {
  render(
    <UiProvider>
      <AssistantChat
        worker="DW2"
        examples={["Việc của tôi là gì?"]}
        turns={[]}
        pending={pending}
        live={live}
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

describe("the chat frame as the answer comes", () => {
  it("says what the worker is doing, then the words so far", () => {
    draw(true, {
      steps: [{ key: "look", title: "Đang tra trong phạm vi bạn được xem" }],
      answer: "",
    });
    expect(screen.getByRole("status").textContent).toBe(
      "Đang tra trong phạm vi bạn được xem",
    );
    cleanup();
    draw(true, { steps: [], answer: "PR-2611-030 đang chờ" });
    expect(
      screen.getByRole("list", { name: "Các lượt hỏi đáp" }).textContent,
    ).toContain("PR-2611-030 đang chờ");
  });

  it("is busy while words arrive, so a screen reader waits for the answer", () => {
    draw(true, { steps: [], answer: "PR" });
    expect(
      screen
        .getByRole("list", { name: "Các lượt hỏi đáp" })
        .getAttribute("aria-busy"),
    ).toBe("true");
  });
});

describe("stopping an answer", () => {
  it("offers a stop while answering, and pressing it asks to stop", () => {
    const onStop = vi.fn();
    const { container } = render(
      <UiProvider>
        <AssistantChat
          worker="DW1"
          examples={[]}
          turns={[]}
          pending
          onStop={onStop}
          question="PO nào?"
          onQuestion={vi.fn()}
          onAsk={vi.fn()}
          maxLength={500}
        />
      </UiProvider>,
    );
    const stop = container.querySelector<HTMLButtonElement>(
      ".ant-sender-actions-btn",
    );
    expect(stop).not.toBeNull();
    fireEvent.click(stop!);
    expect(onStop).toHaveBeenCalledOnce();
  });
});

describe("a turn folded from its events", () => {
  it("adds words and steps, and a replace takes the words back", () => {
    const shown = [
      { event: "step", key: "read", title: "Đang đọc câu hỏi" },
      { event: "delta", text: "Hồ sơ " },
      { event: "delta", text: "đang " },
    ] as const;
    const live = shown.reduce(liveAfter, NOTHING_YET);
    expect(live.answer).toBe("Hồ sơ đang ");
    expect(live.steps.map((s) => s.key)).toEqual(["read"]);
    expect(
      liveAfter(live, { event: "replace", text: "Câu của code." }).answer,
    ).toBe("Câu của code.");
  });
});
