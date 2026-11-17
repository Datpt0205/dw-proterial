import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Approval } from "@dw/contracts";

let scopes = ["sales.rules.propose", "sales.rules.approve"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({ apiClient: () => ({}) }));

const PROPOSED = "0aa10aa0-c939-7000-8539-31fd3e621730";
const SKILL = {
  name: "mail-kinds",
  ref: "sales_skill_mail_kinds@1.0.0",
  platform_ref: "sales_skill_mail_kinds@1.0.0",
  layer: "platform",
  description: "Đọc loại thư.",
  instructions: "Dòng một\nDòng hai cũ\nDòng ba",
};
const version = (status: string) => ({
  version_id: PROPOSED,
  name: "mail-kinds",
  ref: "sales_skill_mail_kinds@1.0.1",
  status,
  proposed_by: "00000000-0000-0000-0000-000000000040",
  decided_by: null,
  description: "Đọc loại thư.",
  instructions: "Dòng một\nDòng hai mới\nDòng ba\nDòng bốn",
  approval_id: "a-1",
  replay: {
    version_id: PROPOSED,
    replayed_at: "2026-11-16T02:00:00Z",
    source: "platform_examples",
    outcome: "replayed",
    messages: 60,
    right_with: 52,
    right_without: 48,
    unanswered: 0,
    security_failed: ["INJ2"],
  },
  trigger: null,
});
let compared: { skill: unknown; version: unknown } = {
  skill: SKILL,
  version: version("proposed"),
};
const api = {
  skillVersion: vi.fn(async (versionId: string) => {
    if (versionId !== PROPOSED) throw new Error("not found");
    return compared;
  }),
};
vi.mock("../../_lib/api", () => ({ salesApi: () => api }));

import {
  approvalDetail,
  approvalInbox,
} from "../../../../lib/approvals/registry";
import { SkillApprovalChanges } from "../skill-approval";

const APPROVAL = {
  id: "a-1",
  approval_type: "sales.skills",
  reason: "r",
  status: "pending",
  run_id: null,
  payload: {
    key: "sales_skill_mail_kinds",
    version: "1.0.1",
    version_id: PROPOSED,
  },
  created_at: "2026-11-16T02:00:00Z",
  decided_at: null,
  requires_comment: true,
  required_scope: "sales.rules.approve",
  can_decide: true,
  requested_by_me: false,
} as Approval;

function draw(approval: Approval = APPROVAL) {
  render(
    <UiProvider>
      <SkillApprovalChanges approval={approval} />
    </UiProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes = ["sales.rules.propose", "sales.rules.approve"];
  compared = { skill: SKILL, version: version("proposed") };
});

describe("a skill version where the head decides it (ticket 40)", () => {
  it("is decided on /approvals, not sent to /sales, its words drawn under the payload", () => {
    expect(approvalInbox(APPROVAL)).toBeNull();
    expect(approvalDetail(APPROVAL)).toBe(SkillApprovalChanges);
  });

  it("shows the replay and the lines it adds and drops against the skill in force", async () => {
    draw();
    expect(
      await screen.findByText(
        "Đúng 52/60 với bản đề xuất · 48/60 với bản đang dùng",
      ),
    ).toBeTruthy();
    expect(screen.getByText(/trượt 1 ca bảo mật/)).toBeTruthy();
    expect(screen.getByText("sales_skill_mail_kinds@1.0.0")).toBeTruthy();
    expect(screen.getByText("Dùng khi nào: giữ nguyên")).toBeTruthy();
    const words = screen.getByLabelText("Lời hướng dẫn");
    expect(
      within(words).getByText("Lời hướng dẫn: thêm 2 dòng, bỏ 1 dòng"),
    ).toBeTruthy();
    const dropped = within(words).getByText("Dòng hai cũ");
    expect(dropped.closest("del")).toBeTruthy();
    expect(within(words).getByText("Dòng hai mới")).toBeTruthy();
    expect(within(words).getByText("Dòng bốn")).toBeTruthy();
    expect(within(words).getAllByText("Thêm")).toHaveLength(2);
    expect(within(words).getAllByText("Bỏ")).toHaveLength(1);
  });

  it("says why it is not shown, and reads nothing, without sales.rules.propose", () => {
    scopes = ["sales.rules.approve"];
    draw();
    expect(screen.getByText(/Chỉ người có quyền đề xuất quy tắc/)).toBeTruthy();
    expect(api.skillVersion).not.toHaveBeenCalled();
  });

  it("compares nothing once the version is decided", async () => {
    compared = { skill: SKILL, version: version("approved") };
    draw();
    expect(
      await screen.findByText(
        "Phiên bản sales_skill_mail_kinds@1.0.1: đã duyệt.",
      ),
    ).toBeTruthy();
    expect(screen.queryByLabelText("Lời hướng dẫn")).toBeNull();
  });

  it("reads the approval's own version", async () => {
    draw();
    await screen.findByLabelText("Lời hướng dẫn");
    expect(api.skillVersion).toHaveBeenCalledWith(PROPOSED);
  });

  it("compares a customer's SalesOrder version with the customer's in force (ticket 41)", async () => {
    compared = {
      skill: {
        name: "salesorder-khb",
        ref: "sales_skill_salesorder_khb@1.0.1",
        platform_ref: "sales_skill_salesorder_khb@1.0.0",
        layer: "tenant",
        description: "PO của KHB thành SalesOrder.",
        instructions: "Cột AF: ngày giao\nĐơn vị: cuộn",
      },
      version: {
        ...version("proposed"),
        name: "salesorder-khb",
        ref: "sales_skill_salesorder_khb@1.0.2",
        description: "PO của KHB thành SalesOrder.",
        instructions: "Cột AF: ngày giao trừ 2 ngày\nĐơn vị: cuộn",
        replay: {
          version_id: PROPOSED,
          replayed_at: "2026-11-16T02:00:00Z",
          source: "customer_pairs",
          outcome: "replayed",
          messages: 3,
          right_with: 2,
          right_without: 3,
          unanswered: 0,
          security_failed: [],
        },
      },
    };
    draw({
      ...APPROVAL,
      payload: {
        key: "sales_skill_salesorder_khb",
        version: "1.0.2",
        version_id: PROPOSED,
      },
    } as Approval);
    expect(
      await screen.findByText(
        "Điền đúng 2/3 cặp ví dụ của khách với bản đề xuất · 3/3 với bản đang dùng",
      ),
    ).toBeTruthy();
    expect(screen.getByText("sales_skill_salesorder_khb@1.0.1")).toBeTruthy();
    expect(screen.getByText(/riêng của công ty/)).toBeTruthy();
    const words = screen.getByLabelText("Lời hướng dẫn");
    expect(
      within(words).getByText("Lời hướng dẫn: thêm 1 dòng, bỏ 1 dòng"),
    ).toBeTruthy();
    expect(
      within(words).getByText("Cột AF: ngày giao").closest("del"),
    ).toBeTruthy();
    expect(
      within(words).getByText("Cột AF: ngày giao trừ 2 ngày"),
    ).toBeTruthy();
  });
});
