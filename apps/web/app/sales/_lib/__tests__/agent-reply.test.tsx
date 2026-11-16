import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

let scopes = ["sales.case.read", "sales.order.prepare"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    email: "an.nguyen@alpha.local",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));

const replyDraft = vi.fn();
vi.mock("../api", () => ({ salesApi: () => ({ replyDraft }) }));

import { AgentReply } from "../../orders/[caseId]/agent-reply";

const DRAFTED = {
  case_id: "c-1",
  kind: "change_can_do_draft",
  drafted_as: "change_can_do_draft",
  kind_label: null,
  skill: null,
  others: [],
  status: "drafted",
  to: ["hana.westbrook@norvanta.example"],
  language: "en",
  refusal: null,
  unsupported: [],
  figures_checked: 4,
  subject: "Change to order NRV-PO-26-0457 confirmed",
  body: "Line 2: 3600 m on 20 Nov 2026.",
  prompt_ref: "sales.reply_draft@1.0.0",
  model_profile: "onprem",
};

afterEach(() => {
  cleanup();
  replyDraft.mockReset();
  scopes = ["sales.case.read", "sales.order.prepare"];
});

function renderIt(kind = "change_can_do_draft", messageId?: string) {
  render(
    <UiProvider>
      <AgentReply caseId="c-1" kind={kind as never} messageId={messageId} />
    </UiProvider>,
  );
}

describe("Bản AI soạn (ticket 32)", () => {
  it("shows the machine's wording with the check's result, asked on click", async () => {
    replyDraft.mockResolvedValue(DRAFTED);
    renderIt();
    expect(replyDraft).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Bản AI soạn" }));
    expect(await screen.findByText("Máy viết")).toBeTruthy();
    expect(screen.getByText(/DW1 đã kiểm: 4 con số/)).toBeTruthy();
    expect(replyDraft).toHaveBeenCalledWith(
      "c-1",
      "change_can_do_draft",
      undefined,
    );
  });

  it("an answer to a question names the customer's mail", async () => {
    replyDraft.mockResolvedValue({
      ...DRAFTED,
      kind: "question_answer",
      drafted_as: "question_answer",
    });
    renderIt("question_answer", "R2");
    fireEvent.click(screen.getByRole("button", { name: "Bản AI soạn" }));
    await screen.findByText("Máy viết");
    expect(replyDraft).toHaveBeenCalledWith("c-1", "question_answer", "R2");
  });

  it("a dropped draft says why, points to the template, and shows the figures on click", async () => {
    replyDraft.mockResolvedValue({
      ...DRAFTED,
      status: "refused",
      refusal: "figure",
      unsupported: ["28"],
      subject: null,
      body: null,
    });
    renderIt();
    fireEvent.click(screen.getByRole("button", { name: "Bản AI soạn" }));
    expect(
      await screen.findByText(
        /có con số không có trong hồ sơ.*thư nháp theo mẫu/,
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/Số không có trong hồ sơ: 28/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Xem số không khớp" }));
    expect(screen.getByText("Số không có trong hồ sơ: 28")).toBeTruthy();
    expect(screen.queryByText("Máy viết")).toBeNull();
  });

  it("says when the step is off, and that Sales answers a question then", async () => {
    replyDraft.mockResolvedValue({
      ...DRAFTED,
      kind: "question_answer",
      drafted_as: "question_answer",
      status: "off",
      subject: null,
      body: null,
    });
    renderIt("question_answer", "R2");
    fireEvent.click(screen.getByRole("button", { name: "Bản AI soạn" }));
    expect(
      await screen.findByText(/chưa bật bước AI soạn thư.*Sales tự trả lời/),
    ).toBeTruthy();
  });

  it("offers the company's other kinds of the draft by their label (ticket 42)", async () => {
    replyDraft.mockResolvedValueOnce({
      ...DRAFTED,
      kind: "confirmation_draft",
      drafted_as: "confirmation_draft",
      skill: "sales_skill_reply_drafts@1.1.0",
      others: [{ kind: "short_confirmation", label: "Xác nhận ngắn" }],
    });
    replyDraft.mockResolvedValueOnce({
      ...DRAFTED,
      kind: "short_confirmation",
      drafted_as: "confirmation_draft",
      kind_label: "Xác nhận ngắn",
      skill: "sales_skill_reply_drafts@1.1.0",
      others: [{ kind: "confirmation_draft", label: null }],
    });
    renderIt("confirmation_draft");
    fireEvent.click(screen.getByRole("button", { name: "Bản AI soạn" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Xác nhận ngắn" }),
    );
    expect(
      await screen.findByText("Xác nhận ngắn", { selector: "strong" }),
    ).toBeTruthy();
    expect(replyDraft).toHaveBeenLastCalledWith(
      "c-1",
      "short_confirmation",
      undefined,
    );
    // The offer stays the first answer's: the platform's draft is the button above.
    expect(
      screen.queryByRole("button", { name: "confirmation_draft" }),
    ).toBeNull();
  });

  it("keeps the button off for someone who does not prepare orders", () => {
    scopes = ["sales.case.read"];
    renderIt();
    const button = screen.getByRole("button", { name: "Bản AI soạn" });
    expect(button.hasAttribute("disabled")).toBe(true);
  });
});
