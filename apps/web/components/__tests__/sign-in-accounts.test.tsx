import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { App } from "antd";
import { ApiError } from "@dw/api-client";

// The members screen with sign-in accounts (member_accounts.py): what it
// offers, what it disables and why, and that a temporary password is shown
// once, in its dialog only.

let roles = ["org_admin"];
vi.mock("../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    active: { workspaceId: "ws-1" },
    roles,
    principalId: "me",
  }),
}));

const listLoginAccounts = vi.fn();
const createMemberAccount = vi.fn();
const resetMemberPassword = vi.fn();
const setMemberSignIn = vi.fn();
vi.mock("../../lib/session", () => ({
  apiClient: () => ({
    listWorkspaceMembers: async () => [
      member("me", "Tâm Ngô", "tam@x.vn", ["org_admin"]),
      member("u-lan", "Lan Phạm", "lan@x.vn", ["sales_pic"]),
      member("u-it", "Hùng IT", "hung@x.vn", ["org_admin"]),
      member("u-ad", "Minh AD", "minh@x.vn", ["member"]),
    ],
    listGrantCandidates: async () => [],
    listPermissionSets: async () => [],
    listAdminRoles: async () => [
      {
        key: "member",
        name: "Nhân viên",
        scopes: ["crm.read"],
        administrative: false,
      },
      {
        key: "sales_pic",
        name: "Sales PIC",
        scopes: ["sales.case.read"],
        administrative: false,
      },
      {
        key: "org_admin",
        name: "Quản trị",
        scopes: ["platform.members.write"],
        administrative: true,
      },
    ],
    listLoginAccounts,
    createMemberAccount,
    resetMemberPassword,
    setMemberSignIn,
    grantMember: vi.fn(),
  }),
}));

import { MembersManager } from "../admin/members-manager";

function member(id: string, name: string, email: string, roleKeys: string[]) {
  return {
    user_id: id,
    email,
    display_name: name,
    department: "general",
    role_keys: roleKeys,
    permission_set_keys: [],
  };
}

const MANAGED = [
  { email: "tam@x.vn", enabled: true },
  { email: "lan@x.vn", enabled: true },
  { email: "hung@x.vn", enabled: true },
  // minh@x.vn signs in through AD: not an account DW created.
];

beforeAll(() => {
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
  roles = ["org_admin"];
  for (const fn of [
    listLoginAccounts,
    createMemberAccount,
    resetMemberPassword,
    setMemberSignIn,
  ])
    fn.mockReset();
});

function show() {
  render(
    <App>
      <MembersManager />
    </App>,
  );
}

const isDisabled = (el: HTMLElement) => (el as HTMLButtonElement).disabled;

async function row(name: string): Promise<HTMLElement> {
  const label = await screen.findByText(name);
  return label.closest("li") as HTMLElement;
}

describe("sign-in accounts on the members screen", () => {
  it("disables “Thêm người” with the server's reason when the deployment has no accounts client", async () => {
    listLoginAccounts.mockRejectedValue(
      new ApiError(503, {
        code: "upstream_unavailable",
        message: "Máy chủ này chưa bật tạo tài khoản đăng nhập.",
        details: { reason_code: "login_accounts_not_configured" },
      } as never),
    );
    show();
    // Re-queried: the tooltip that carries the reason wraps a new node.
    await waitFor(() =>
      expect(
        isDisabled(screen.getByRole("button", { name: /Thêm người/ })),
      ).toBe(true),
    );
    // The reason is visible text, not only a tooltip (ui-quality §5).
    expect(
      (
        await screen.findAllByText(
          "Máy chủ này chưa bật tạo tài khoản đăng nhập.",
        )
      ).length,
    ).toBeGreaterThan(0);
  });

  it("creates the person with a role and shows the temporary password once", async () => {
    listLoginAccounts.mockResolvedValue(MANAGED);
    createMemberAccount.mockResolvedValue({
      user_id: "u-new",
      email: "vy@x.vn",
      display_name: "Trần Vy",
      temporary_password: "Abcd-Efgh-Jkm2",
    });
    show();
    const add = await screen.findByRole("button", { name: /Thêm người/ });
    await waitFor(() => expect(isDisabled(add)).toBe(false));
    fireEvent.click(add);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Họ và tên"), {
      target: { value: "Trần Vy" },
    });
    fireEvent.change(within(dialog).getByLabelText("Email công ty"), {
      target: { value: "vy@x.vn" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: /Tạo tài khoản/ }),
    );

    await screen.findByText("Mật khẩu tạm của Trần Vy");
    expect(screen.getByText("Abcd-Efgh-Jkm2")).toBeTruthy();
    const [input, key] = createMemberAccount.mock.calls[0]!;
    expect(input).toEqual({
      displayName: "Trần Vy",
      email: "vy@x.vn",
      workspaceId: "ws-1",
      roleKeys: ["member"],
    });
    expect(key).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("says the password was shown before when a replay answers without it", async () => {
    listLoginAccounts.mockResolvedValue(MANAGED);
    resetMemberPassword.mockResolvedValue({
      user_id: "u-lan",
      temporary_password: null,
    });
    show();
    const lan = await row("Lan Phạm");
    const reset = within(lan).getByRole("button", { name: /Đặt lại mật khẩu/ });
    await waitFor(() => expect(isDisabled(reset)).toBe(false));
    fireEvent.click(reset);
    fireEvent.click(await screen.findByRole("button", { name: "Đặt lại" }));
    await screen.findByText(/máy chủ không lưu lại mật khẩu tạm/);
  });

  it("locks after a confirmation that names the person", async () => {
    listLoginAccounts.mockResolvedValue(MANAGED);
    setMemberSignIn.mockResolvedValue(undefined);
    show();
    const lan = await row("Lan Phạm");
    const lock = within(lan).getByRole("button", { name: /Khóa đăng nhập/ });
    await waitFor(() => expect(isDisabled(lock)).toBe(false));
    fireEvent.click(lock);
    await screen.findAllByText("Khóa đăng nhập của Lan Phạm?");
    fireEvent.click(
      within(screen.getAllByRole("dialog").at(-1)!).getByRole("button", {
        name: "Khóa đăng nhập",
      }),
    );
    await waitFor(() => expect(setMemberSignIn).toHaveBeenCalledTimes(1));
    expect(setMemberSignIn.mock.calls[0]!.slice(0, 2)).toEqual([
      "u-lan",
      false,
    ]);
  });

  it("disables each action whose refusal it can already name", async () => {
    listLoginAccounts.mockResolvedValue(MANAGED);
    show();
    // An account DW did not create (AD): neither action.
    const minh = await row("Minh AD");
    await waitFor(() =>
      expect(
        isDisabled(
          within(minh).getByRole("button", { name: /Đặt lại mật khẩu/ }),
        ),
      ).toBe(true),
    );
    expect(
      isDisabled(within(minh).getByRole("button", { name: /Khóa đăng nhập/ })),
    ).toBe(true);
    // An administrator's sign-in, to an org admin: neither action.
    const hung = await row("Hùng IT");
    expect(
      isDisabled(
        within(hung).getByRole("button", { name: /Đặt lại mật khẩu/ }),
      ),
    ).toBe(true);
    // The admin's own row: reset yes, lock no.
    const me = await row("Tâm Ngô");
    expect(
      isDisabled(within(me).getByRole("button", { name: /Khóa đăng nhập/ })),
    ).toBe(true);
  });

  it("offers every business role from the catalog, and no administrative one to an org admin", async () => {
    listLoginAccounts.mockResolvedValue(MANAGED);
    show();
    fireEvent.click(await screen.findByRole("button", { name: /Thêm người/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByRole("combobox"));
    // antd's visible items; its role="option" nodes carry the value only.
    await waitFor(() =>
      expect(
        document.querySelectorAll(".ant-select-item-option-content").length,
      ).toBeGreaterThan(0),
    );
    const labels = [
      ...document.querySelectorAll(".ant-select-item-option-content"),
    ].map((o) => o.textContent);
    expect(labels).toContain("Sales phụ trách (PIC)");
    expect(labels).not.toContain("Quản trị hệ thống");
  });
});
