import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// The session menu is the second door to /audit beside the nav registry. The
// audit trail is `audit.events` on the API (approval-audit-and-workspace/02),
// so a member holding only the inbox's `approvals.read` must not be offered it
// here either.
let scopes: string[] = [];
// Keycloak sign-in hands the menu a password action; dev mode hands it null.
let changePassword: (() => void) | null = null;
vi.mock("../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    status: "ready",
    displayName: "Lan",
    roles: ["member"],
    isPlatformOperator: false,
    logout: vi.fn(),
    hasScope: (scope: string) => scopes.includes(scope),
    changePassword,
  }),
}));

import { SessionChip } from "../session-chip";

afterEach(() => {
  cleanup();
  changePassword = null;
});

function openMenu(): void {
  render(<SessionChip />);
  fireEvent.click(screen.getByRole("button", { name: /Lan/ }));
}

function auditLinkShown(): boolean {
  return screen.queryByRole("link", { name: /Nhật ký hoạt động/ }) !== null;
}

describe("session menu", () => {
  it("does not offer the audit log to a member who reads only the inbox", async () => {
    scopes = ["approvals.read", "runs.read"];
    openMenu();

    // The menu is open: sign-out is in it.
    expect(await screen.findByText("Đăng xuất")).toBeTruthy();
    expect(auditLinkShown()).toBe(false);
  });

  it("offers the audit log to a holder of audit.events", async () => {
    scopes = ["approvals.read", "runs.read", "audit.events"];
    openMenu();

    expect(await screen.findByText("Đăng xuất")).toBeTruthy();
    expect(auditLinkShown()).toBe(true);
  });

  it("offers “Đổi mật khẩu” where the sign-in is Keycloak's, and it opens Keycloak's page", async () => {
    scopes = [];
    const opened = vi.fn();
    changePassword = opened;
    openMenu();

    fireEvent.click(await screen.findByText("Đổi mật khẩu"));
    expect(opened).toHaveBeenCalledTimes(1);
  });

  it("has no password to change in dev mode", async () => {
    scopes = [];
    openMenu();

    expect(await screen.findByText("Đăng xuất")).toBeTruthy();
    expect(screen.queryByText("Đổi mật khẩu")).toBeNull();
  });
});
