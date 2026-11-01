import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Approval } from "@dw/api-client";
import { DecideApproval } from "../../_components/decide-approval";

const decideApproval = vi.fn().mockResolvedValue({});
vi.mock("../../../../lib/session", () => ({
  apiClient: () => ({ decideApproval }),
}));

function approval(over: Partial<Approval> = {}): Approval {
  return {
    id: "a-1",
    approval_type: "purchasing.request",
    reason: "",
    status: "pending",
    run_id: null,
    payload: { case_id: "c-1", case_version: 2 },
    created_at: null,
    decided_at: null,
    requires_comment: true,
    required_scope: "purchasing.approve.tier3",
    can_decide: true,
    requested_by_me: false,
    ...over,
  };
}

function draw(a: Approval, onDecided = vi.fn()) {
  render(
    <UiProvider>
      <DecideApproval
        approval={a}
        subjectVersion={2}
        what="yêu cầu DW2-1"
        onDecided={onDecided}
      />
    </UiProvider>,
  );
  return onDecided;
}

afterEach(() => {
  cleanup();
  decideApproval.mockClear();
});

/**
 * One press decides a purchasing approval, after the reason the strict type
 * requires; who may decide is the server's `can_decide`, and a maker is told
 * why they cannot (separation of duties), never shown a live button.
 */
describe("deciding a purchasing approval", () => {
  it("waits for the reason, then decides the version the person saw", async () => {
    const onDecided = draw(approval());
    const approve = screen.getByRole("button", { name: "Duyệt yêu cầu DW2-1" });
    expect((approve as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("note").textContent).toContain("Ghi lý do");
    fireEvent.change(
      screen.getByRole("textbox", { name: "Lý do quyết định yêu cầu DW2-1" }),
      {
        target: { value: "Đúng nhu cầu" },
      },
    );
    expect((approve as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(approve);
    await waitFor(() => expect(onDecided).toHaveBeenCalled());
    expect(decideApproval).toHaveBeenCalledWith(
      "a-1",
      { approve: true, comment: "Đúng nhu cầu", subject_version: 2 },
      expect.any(String),
    );
  });

  it("tells a maker why they cannot decide, with nothing to type", () => {
    draw(approval({ can_decide: false, requested_by_me: true }));
    expect(
      (
        screen.getByRole("button", {
          name: "Duyệt yêu cầu DW2-1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(
      (
        screen.getByRole("button", {
          name: "Từ chối yêu cầu DW2-1",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("note").textContent).toContain("tách nhiệm");
  });
});
