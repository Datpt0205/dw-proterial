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

const senderCustomer = vi.fn();
const confirmSenderCustomer = vi.fn();
const customers = vi.fn();
vi.mock("../api", () => ({
  salesApi: () => ({ senderCustomer, confirmSenderCustomer, customers }),
}));

import { SenderCustomerPanel } from "../../inbox/sender-customer";

const SUGGESTED = {
  message_id: "S01",
  sender: "tran.minh@freemail.example",
  status: "suggested",
  customer_code: "BRN",
  customer_name: "Công ty TNHH Brennic Việt Nam",
  evidence: "Công ty TNHH Brennic Việt Nam",
  prompt_ref: "sales.sender_customer@1.0.0",
  model_profile: "onprem",
};

afterEach(() => {
  cleanup();
  for (const f of [senderCustomer, confirmSenderCustomer, customers]) f.mockReset();
  scopes = ["sales.case.read", "sales.inbox.process"];
});

function renderIt(onConfirmed = vi.fn()) {
  customers.mockResolvedValue({ items: [] });
  render(
    <UiProvider>
      <SenderCustomerPanel messageId="S01" onConfirmed={onConfirmed} />
    </UiProvider>,
  );
  return onConfirmed;
}

describe("DW1 đoán khách cho người gửi lạ (AI item 5)", () => {
  it("shows the guess as the machine's, with the words it rests on, and confirms it", async () => {
    senderCustomer.mockResolvedValue(SUGGESTED);
    confirmSenderCustomer.mockResolvedValue({ job_id: "j-1", message_id: "S01" });
    const onConfirmed = renderIt();
    expect(await screen.findByText("Máy đoán")).toBeTruthy();
    expect(
      screen.getByText("Căn cứ trong thư: “Công ty TNHH Brennic Việt Nam”"),
    ).toBeTruthy();
    fireEvent.click(
      screen.getByRole("button", { name: "Xác nhận thư S01 của khách BRN" }),
    );
    await vi.waitFor(() => expect(onConfirmed).toHaveBeenCalled());
    expect(confirmSenderCustomer).toHaveBeenCalledWith(
      "S01",
      "BRN",
      expect.any(String),
    );
  });

  it("names the company the mail signs when it matches no customer", async () => {
    senderCustomer.mockResolvedValue({
      ...SUGGESTED,
      status: "no_match",
      customer_code: null,
      customer_name: null,
      evidence: "Talverra Trading",
    });
    renderIt();
    expect(await screen.findByText(/“Talverra Trading”, không khớp khách nào/)).toBeTruthy();
    expect(screen.queryByText("Máy đoán")).toBeNull();
  });

  it("asks nothing for someone who cannot process mail", async () => {
    scopes = ["sales.case.read"];
    renderIt();
    expect(
      screen.getByRole("combobox", { name: "Chọn khách cho thư S01" }),
    ).toBeTruthy();
    expect(senderCustomer).not.toHaveBeenCalled();
  });
});
