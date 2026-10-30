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

const customerReminder = vi.fn();
vi.mock("../api", () => ({ salesApi: () => ({ customerReminder }) }));

import { CustomerReminder } from "../../_components/customer-reminder";

const DRAFTED = {
  case_id: "c-1",
  status: "drafted",
  to: ["hana.westbrook@norvanta.example"],
  asked_on: "2026-10-26",
  subject: "Nhắc PO NRV-PO-26-0457",
  body: "Kính gửi Norvanta,\nNgày 26/10/2026 chúng tôi đã hỏi về PO NRV-PO-26-0457.",
  language: "vi",
  prompt_ref: "sales.customer_reminder@1.0.0",
  model_profile: "onprem",
};

afterEach(() => {
  cleanup();
  customerReminder.mockReset();
  scopes = ["sales.case.read", "sales.order.prepare"];
});

function renderIt(kind: "order" | "quote" = "order") {
  render(
    <UiProvider>
      <CustomerReminder kind={kind} caseId="c-1" />
    </UiProvider>,
  );
}

describe("DW1 soạn thư nhắc khách (DW01 chức năng 4)", () => {
  it("shows the machine's reminder, the day the customer was asked, and opens it in Outlook", async () => {
    customerReminder.mockResolvedValue(DRAFTED);
    renderIt();
    fireEvent.click(
      screen.getByRole("button", { name: "DW1 soạn thư nhắc khách" }),
    );
    expect(await screen.findByText("Máy viết")).toBeTruthy();
    expect(screen.getByText("Khách được hỏi từ 26/10/2026.")).toBeTruthy();
    const open = screen.getByRole("link", { name: /Mở trong Outlook/ });
    expect(open.getAttribute("href")).toContain(
      "mailto:hana.westbrook%40norvanta.example?subject=Nh%E1%BA%AFc%20PO",
    );
    expect(customerReminder).toHaveBeenCalledWith("order", "c-1");
  });

  it("says DW1 could not draft when no model answered", async () => {
    customerReminder.mockResolvedValue({
      ...DRAFTED,
      status: "unavailable",
      subject: null,
      body: null,
    });
    renderIt();
    fireEvent.click(
      screen.getByRole("button", { name: "DW1 soạn thư nhắc khách" }),
    );
    expect(await screen.findByText(/chưa có mô hình/)).toBeTruthy();
  });

  it("keeps the button off for someone who does not prepare that kind of case", () => {
    renderIt("quote");
    const button = screen.getByRole("button", {
      name: "DW1 soạn thư nhắc khách",
    });
    expect((button as HTMLButtonElement).disabled).toBe(true);
  });
});
