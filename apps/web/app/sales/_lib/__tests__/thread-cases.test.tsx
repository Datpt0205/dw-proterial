import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import { AN } from "./fixtures";

let scopes = ["sales.case.read", "sales.inbox.process"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    principalId: AN,
    displayName: "An",
    email: "an.nguyen@alpha.local",
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));

const pickThreadCase = vi.fn();
vi.mock("../api", () => ({ salesApi: () => ({ pickThreadCase }) }));

import { ThreadCasesPanel } from "../../inbox/thread-cases";

const OFFERED = [
  { case_kind: "order" as const, case_id: "c-1", number: "VLX-PO-2609-0131" },
  { case_kind: "order" as const, case_id: "c-2", number: "VLX-PO-2610-0004" },
  { case_kind: "quote" as const, case_id: "c-3", number: "VLX-RFQ-2609-07" },
];

afterEach(() => {
  cleanup();
  pickThreadCase.mockReset();
  scopes = ["sales.case.read", "sales.inbox.process"];
});

function renderIt(onPicked = vi.fn()) {
  render(
    <UiProvider>
      <ThreadCasesPanel messageId="R2" offered={OFFERED} onPicked={onPicked} />
    </UiProvider>,
  );
  return onPicked;
}

describe("Chọn hồ sơ: a reply its thread offered several cases for (ticket 24)", () => {
  it("lists each offered case by its number, opens it, and attaches the one picked", async () => {
    pickThreadCase.mockResolvedValue({ kind: "attached_to_case" });
    const onPicked = renderIt();

    expect(
      screen.getByRole("link", { name: "Đơn hàng VLX-PO-2610-0004" }),
    ).toHaveProperty("href", expect.stringContaining("/sales/orders/c-2"));
    expect(
      screen.getByRole("link", { name: "Báo giá VLX-RFQ-2609-07" }),
    ).toHaveProperty("href", expect.stringContaining("/sales/quotes/c-3"));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Gắn thư R2 vào hồ sơ VLX-PO-2610-0004",
      }),
    );

    await vi.waitFor(() => expect(onPicked).toHaveBeenCalled());
    expect(pickThreadCase).toHaveBeenCalledTimes(1);
    expect(pickThreadCase).toHaveBeenCalledWith(
      "R2",
      "c-2",
      expect.any(String),
    );
  });

  it("disables the pick, with the reason, for someone who cannot process mail", () => {
    scopes = ["sales.case.read"];
    renderIt();

    const button = screen.getByRole("button", {
      name: "Gắn thư R2 vào hồ sơ VLX-PO-2609-0131",
    });
    expect(button).toHaveProperty("disabled", true);
    fireEvent.click(button);
    expect(pickThreadCase).not.toHaveBeenCalled();
  });
});
