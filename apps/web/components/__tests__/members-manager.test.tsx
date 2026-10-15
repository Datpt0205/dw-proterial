import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { App } from "antd";

vi.mock("../../lib/auth/auth-context", () => ({
  useAuth: () => ({ active: { workspaceId: "ws-1" }, roles: ["org_admin"] }),
}));

const grantMember = vi.fn();
vi.mock("../../lib/session", () => ({
  apiClient: () => ({
    grantMember,
    listWorkspaceMembers: async () => [
      {
        user_id: "u-1",
        email: "lan@x.vn",
        display_name: "Lan Phạm",
        department: "general",
        role_keys: ["member"],
        permission_set_keys: [],
      },
    ],
    listGrantCandidates: async () => [],
    listPermissionSets: async () => [],
  }),
}));

import { MembersManager } from "../admin/members-manager";

beforeAll(() => {
  // antd's responsive helpers ask for media queries jsdom does not implement.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  grantMember.mockReset();
});

describe("the members manager sends one Idempotency-Key per press", () => {
  it("reuses it when a role save is retried, and mints a new one after it lands", async () => {
    grantMember
      .mockRejectedValueOnce(new Error("mất mạng"))
      .mockResolvedValue({ userId: "u-1", email: "lan@x.vn", displayName: "" });
    render(
      <App>
        <MembersManager />
      </App>,
    );
    const save = await screen.findByRole("button", { name: /Lưu$/ });

    fireEvent.click(save);
    await screen.findByText("mất mạng");
    await waitFor(() => expect(save.className).not.toContain("loading"));
    fireEvent.click(save);
    await waitFor(() => expect(grantMember).toHaveBeenCalledTimes(2));
    // A loading button drops clicks: press again once the save has settled.
    const again = await screen.findByRole("button", { name: /Lưu$/ });
    await waitFor(() => expect(again.className).not.toContain("loading"));
    fireEvent.click(again);
    await waitFor(() => expect(grantMember).toHaveBeenCalledTimes(3));

    const [first, retry, next] = grantMember.mock.calls.map(
      (call) => call[1] as string,
    );
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(retry).toBe(first);
    expect(next).not.toBe(first);
  });
});
