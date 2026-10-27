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

vi.mock("../../lib/auth/auth-context", () => ({
  useAuth: () => ({ active: { workspaceId: "ws-1" }, roles: ["org_admin"] }),
}));

const grantMember = vi.fn();
vi.mock("../../lib/session", () => ({
  apiClient: () => ({
    grantMember,
    listWorkspaceMembers: async () => [
      member("u-1", "Lan Phạm", "lan@x.vn", ["member"]),
      // Two roles: the case that lost "Sales PIC" when the row showed one.
      member("u-2", "An Nguyễn", "an@x.vn", ["member", "sales_pic"]),
      // A role the catalog does not offer this admin: kept as it is on save.
      member("u-3", "Diệu Hoàng", "dieu@x.vn", ["sales_pic", "legacy_role"]),
      member("u-4", "Hùng IT", "hung@x.vn", ["org_admin"]),
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
        key: "approver",
        name: "Người duyệt",
        scopes: ["approvals.decide"],
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
    listLoginAccounts: async () => [],
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

function show() {
  render(
    <App>
      <MembersManager />
    </App>,
  );
}

const isDisabled = (el: HTMLElement) => (el as HTMLButtonElement).disabled;

async function row(name: string): Promise<HTMLElement> {
  return (await screen.findByText(name)).closest("li") as HTMLElement;
}

/** Add a role to a row through its multi-select (antd's visible option). */
async function addRole(name: string, role: string) {
  const r = await row(name);
  fireEvent.mouseDown(within(r).getByRole("combobox"));
  const options = await waitFor(() => {
    const found = [
      ...document.querySelectorAll<HTMLElement>(".ant-select-item-option"),
    ].filter((o) => o.textContent === role && o.offsetParent !== undefined);
    expect(found.length).toBeGreaterThan(0);
    return found;
  });
  fireEvent.click(options[options.length - 1]!);
}

function saveButton(r: HTMLElement): HTMLElement {
  return within(r).getByRole("button", { name: /Lưu$/ });
}

describe("member roles on the members screen", () => {
  it("shows every role a person holds, not the first one", async () => {
    show();
    const an = await row("An Nguyễn");
    await waitFor(() => expect(within(an).getByText("Sales phụ trách (PIC)")).toBeTruthy());
    expect(within(an).getByText("Nhân viên")).toBeTruthy();
  });

  it("keeps Lưu off until a role changes", async () => {
    show();
    const an = await row("An Nguyễn");
    await waitFor(() => expect(within(an).getByText("Sales phụ trách (PIC)")).toBeTruthy());
    expect(isDisabled(saveButton(an))).toBe(true);
  });

  it("sends back every role on save, the new one included and none dropped", async () => {
    grantMember.mockResolvedValue({
      userId: "u-2",
      email: "an@x.vn",
      displayName: "",
    });
    show();
    const an = await row("An Nguyễn");
    await waitFor(() => expect(within(an).getByText("Sales phụ trách (PIC)")).toBeTruthy());
    await addRole("An Nguyễn", "Người duyệt");
    await waitFor(() => expect(isDisabled(saveButton(an))).toBe(false));
    fireEvent.click(saveButton(an));
    await waitFor(() => expect(grantMember).toHaveBeenCalledTimes(1));
    expect([...grantMember.mock.calls[0]![0].roleKeys].sort()).toEqual([
      "approver",
      "member",
      "sales_pic",
    ]);
  });

  it("keeps a role the select does not offer", async () => {
    grantMember.mockResolvedValue({
      userId: "u-3",
      email: "dieu@x.vn",
      displayName: "",
    });
    show();
    const dieu = await row("Diệu Hoàng");
    await waitFor(() =>
      expect(within(dieu).getByText("Sales phụ trách (PIC)")).toBeTruthy(),
    );
    await addRole("Diệu Hoàng", "Nhân viên");
    await waitFor(() => expect(isDisabled(saveButton(dieu))).toBe(false));
    fireEvent.click(saveButton(dieu));
    await waitFor(() => expect(grantMember).toHaveBeenCalledTimes(1));
    expect([...grantMember.mock.calls[0]![0].roleKeys].sort()).toEqual([
      "legacy_role",
      "member",
      "sales_pic",
    ]);
  });

  it("locks an administrator's roles for an org admin", async () => {
    show();
    const hung = await row("Hùng IT");
    await waitFor(() =>
      expect(
        within(hung).getByRole("combobox").closest(".ant-select-disabled"),
      ).not.toBeNull(),
    );
    expect(isDisabled(saveButton(hung))).toBe(true);
  });
});

describe("the members manager sends one Idempotency-Key per press", () => {
  it("reuses it when a role save is retried, and mints a new one after it lands", async () => {
    grantMember
      .mockRejectedValueOnce(new Error("mất mạng"))
      .mockResolvedValue({ userId: "u-1", email: "lan@x.vn", displayName: "" });
    show();
    const lan = await row("Lan Phạm");
    await addRole("Lan Phạm", "Người duyệt");
    await waitFor(() => expect(isDisabled(saveButton(lan))).toBe(false));

    fireEvent.click(saveButton(lan));
    await screen.findByText("mất mạng");
    await waitFor(() =>
      expect(saveButton(lan).className).not.toContain("loading"),
    );
    fireEvent.click(saveButton(lan));
    await waitFor(() => expect(grantMember).toHaveBeenCalledTimes(2));

    // After it lands the list reloads and the row is untouched again: the
    // next change is a new request.
    await waitFor(() => expect(isDisabled(saveButton(lan))).toBe(true));
    await addRole("Lan Phạm", "Người duyệt");
    await waitFor(() => expect(isDisabled(saveButton(lan))).toBe(false));
    fireEvent.click(saveButton(lan));
    await waitFor(() => expect(grantMember).toHaveBeenCalledTimes(3));

    const [first, retry, next] = grantMember.mock.calls.map(
      (call) => call[1] as string,
    );
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(retry).toBe(first);
    expect(next).not.toBe(first);
  });
});
