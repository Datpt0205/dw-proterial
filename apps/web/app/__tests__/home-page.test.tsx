import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// The landing page offers exactly the areas the nav registry would, for the
// scopes the session holds. The audit trail is `audit.events` on the API
// (approval-audit-and-workspace/02), so a member holding only the inbox's
// `approvals.read` must not be offered it.
let scopes: string[] = [];
vi.mock("../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    displayName: "Lan",
    active: { workspaceId: "w1", workspaceName: "W1" },
    isPlatformOperator: false,
    roles: [],
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));

import HomePage from "../page";

afterEach(() => {
  cleanup();
  replace.mockReset();
});

function offered(label: string): boolean {
  return screen.queryByRole("link", { name: new RegExp(label) }) !== null;
}

describe("home page destinations", () => {
  it("does not offer the audit log to a member who reads only the inbox", () => {
    scopes = ["approvals.read", "runs.read"];
    render(<HomePage />);

    expect(offered("Duyệt")).toBe(true);
    expect(offered("Nhật ký kiểm toán")).toBe(false);
  });

  it("offers the audit log to a holder of audit.events", () => {
    scopes = ["approvals.read", "runs.read", "audit.events"];
    render(<HomePage />);

    expect(offered("Duyệt")).toBe(true);
    expect(offered("Nhật ký kiểm toán")).toBe(true);
  });

  it("sends someone who works Sales to their work list, the bar's first page", () => {
    scopes = ["sales.case.read"];
    render(<HomePage />);

    expect(replace).toHaveBeenCalledWith("/sales");
  });

  it("keeps everyone else on the landing page", () => {
    scopes = ["approvals.read"];
    render(<HomePage />);

    expect(replace).not.toHaveBeenCalled();
  });
});
