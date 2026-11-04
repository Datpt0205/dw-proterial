import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scope === "purchasing.request.read",
  }),
}));
vi.mock("../../../../lib/session", () => ({ apiClient: () => ({}) }));

const CASE = "0aa10aa0-c939-7000-8539-31fd3e621702";
const mail = (
  message_id: string,
  disposition: "opened" | "to_person" | "supplier" | null,
  extra: Record<string, unknown> = {},
) => ({
  message_id,
  sender: "sales@kimura.example",
  subject: `Thư ${message_id}`,
  received_at: "2026-11-04T02:00:00Z",
  disposition,
  reason: null,
  case_id: null,
  ...extra,
});
const api = {
  mailbox: vi.fn(async () => [
    mail("C01", "supplier", { case_id: CASE }),
    mail("P05", "to_person", { reason: "no_pr_number" }),
  ]),
};
vi.mock("../../_lib/api", () => ({ purchasingApi: () => api }));

import InboxPage from "../page";

afterEach(cleanup);

describe("the purchasing mailbox", () => {
  it("shows a supplier's mail DW2 handled at its case, not as one for a person", async () => {
    render(
      <UiProvider>
        <InboxPage />
      </UiProvider>,
    );
    const row = (await screen.findByText("Thư C01")).closest("tr")!;
    expect(within(row).getByText("Thư nhà cung cấp")).toBeTruthy();
    expect(within(row).queryByText("Cần người xem")).toBeNull();
    expect(
      within(row).getByRole("link", { name: "Mở hồ sơ" }).getAttribute("href"),
    ).toBe(`/purchasing/requests/${CASE}`);
    const other = screen.getByText("Thư P05").closest("tr")!;
    expect(within(other).getByText("Cần người xem")).toBeTruthy();
  });
});
