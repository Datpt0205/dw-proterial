import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

vi.mock("../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    hasScope: (scope: string) => scope === "platform.tenant.settings.write",
  }),
}));

const stored = {
  tenant_id: "t-1",
  slug: "alpha",
  name: "Alpha",
  timezone: "Asia/Ho_Chi_Minh",
  locale: "vi-VN",
  status: "active",
  record_visibility: "open",
  max_autonomy_level: "A1",
};
const updateTenantSettings = vi.fn(async (body: object) => ({
  ...stored,
  ...body,
}));
vi.mock("../../../lib/session", () => ({
  apiClient: () => ({
    getTenantSettings: vi.fn(async () => stored),
    updateTenantSettings,
  }),
}));

import SettingsPage from "../settings/page";

afterEach(cleanup);

describe("the company settings (2026-10-27)", () => {
  it("offers no time zone or language to type, and saves the stored ones back", async () => {
    render(
      <UiProvider>
        <SettingsPage />
      </UiProvider>,
    );
    expect(await screen.findByText(/Giờ Việt Nam \(UTC\+7\)/)).toBeTruthy();
    expect(screen.getByText("Tiếng Việt")).toBeTruthy();
    // Nothing reads either: a field to change them would change nothing.
    expect(screen.queryByPlaceholderText("Asia/Ho_Chi_Minh")).toBeNull();
    expect(screen.queryByPlaceholderText("vi-VN")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Lưu/ }));
    await waitFor(() => expect(updateTenantSettings).toHaveBeenCalledTimes(1));
    expect(updateTenantSettings.mock.calls[0]![0]).toMatchObject({
      timezone: "Asia/Ho_Chi_Minh",
      locale: "vi-VN",
    });
  });
});
