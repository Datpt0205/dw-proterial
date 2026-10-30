import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

let scopes = ["sales.case.read", "sales.quote.prepare"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    email: "an.nguyen@alpha.local",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));

const screeningFollowup = vi.fn();
vi.mock("../api", () => ({ salesApi: () => ({ screeningFollowup }) }));

import { mailtoOf } from "../../_components/drafted-mail";
import { FollowupDraft } from "../../quotes/screening/followup-draft";

const DRAFTED = {
  customer_code: "NRV",
  prv_code: "CB-2006",
  status: "drafted",
  to: ["hana.westbrook@norvanta.example"],
  subject: "Quotation Q26-0123 for CB-2006",
  body: "Dear Norvanta,\nIs quotation Q26-0123 still needed?",
  language: "en",
  prompt_ref: "sales.screening_followup@1.0.0",
  model_profile: "onprem",
};

afterEach(() => {
  cleanup();
  screeningFollowup.mockReset();
  scopes = ["sales.case.read", "sales.quote.prepare"];
});

function renderIt() {
  render(
    <UiProvider>
      <FollowupDraft customerCode="NRV" prvCode="CB-2006" />
    </UiProvider>,
  );
}

describe("DW1 soạn thư hỏi khách (AI item 11)", () => {
  it("shows the machine's draft and opens it in the person's own mail program", async () => {
    screeningFollowup.mockResolvedValue(DRAFTED);
    renderIt();
    fireEvent.click(
      screen.getByRole("button", { name: "DW1 soạn thư hỏi khách" }),
    );
    expect(await screen.findByText("Máy viết")).toBeTruthy();
    const open = screen.getByRole("link", { name: /Mở trong Outlook/ });
    expect(open.getAttribute("href")).toBe(mailtoOf(DRAFTED as never));
    expect(open.getAttribute("href")).toContain(
      "mailto:hana.westbrook%40norvanta.example?subject=Quotation%20Q26-0123",
    );
    expect(screeningFollowup).toHaveBeenCalledWith("NRV", "CB-2006");
  });

  it("says why there is none when the draft was refused", async () => {
    screeningFollowup.mockResolvedValue({
      ...DRAFTED,
      status: "refused",
      subject: null,
      body: null,
    });
    renderIt();
    fireEvent.click(
      screen.getByRole("button", { name: "DW1 soạn thư hỏi khách" }),
    );
    expect(
      await screen.findByText(/số tiền không có trong hồ sơ/),
    ).toBeTruthy();
  });

  it("keeps the button off for someone who does not prepare quotations", () => {
    scopes = ["sales.case.read"];
    renderIt();
    const button = screen.getByRole("button", {
      name: "DW1 soạn thư hỏi khách",
    });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
