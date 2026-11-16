import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Approval } from "@dw/contracts";

let scopes = ["sales.rules.approve"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({ apiClient: () => ({}) }));

const PROPOSED = "0aa10aa0-c939-7000-8539-31fd3e621710";
const CASE = "0aa10aa0-c939-7000-8539-31fd3e621799";
const KEPT = { description: "Dây AWG22 đen", prv_code: "HW-1004" };
const ADDED = {
  description: "Dây điện AWG20 màu xanh lá",
  prv_code: "HW-1011",
  label_id: "0aa10aa0-c939-7000-8539-31fd3e621720",
  case_id: CASE,
  customer_code: "C001",
};
const DROPPED = { description: "Cáp 2 lõi xám", prv_code: "HW-1020" };
const version = (status: string, demonstrations: unknown[]) => ({
  version_id: PROPOSED,
  ref: "sales_prompt_description_attributes@1.3.0",
  status,
  proposed_by: "00000000-0000-0000-0000-000000000043",
  proposed_at: "2026-11-16T02:00:00Z",
  decided_by: null,
  decided_at: null,
  comment: null,
  approval_id: "a-1",
  demonstrations,
  replay: { cases: 20, right_before: 0, right_after: 19, security_cases: 9 },
});
let versions = [version("proposed", [KEPT, ADDED])];
const api = {
  prompts: vi.fn(async () => ({
    step: "description_attributes",
    prompt: "sales.description_attributes@1.1.0",
    in_force: "sales_prompt_description_attributes@1.2.0",
    layer: "tenant",
    demonstrations: [KEPT, DROPPED],
    versions,
  })),
};
vi.mock("../../_lib/api", () => ({ salesApi: () => api }));

import {
  approvalDetail,
  approvalInbox,
} from "../../../../lib/approvals/registry";
import { PromptApprovalChanges } from "../prompt-approval";

const APPROVAL = {
  id: "a-1",
  approval_type: "sales.prompts",
  reason: "r",
  status: "pending",
  run_id: null,
  payload: {
    key: "sales_prompt_description_attributes",
    version: "1.3.0",
    version_id: PROPOSED,
  },
  created_at: "2026-11-16T02:00:00Z",
  decided_at: null,
  requires_comment: true,
  required_scope: "sales.rules.approve",
  can_decide: true,
  requested_by_me: false,
} as Approval;

function draw() {
  render(
    <UiProvider>
      <PromptApprovalChanges approval={APPROVAL} />
    </UiProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes = ["sales.rules.approve"];
  versions = [version("proposed", [KEPT, ADDED])];
});

describe("a prompt version where the head decides it (ticket 43)", () => {
  it("is decided on /approvals, its lines drawn under the payload", () => {
    expect(approvalInbox(APPROVAL)).toBeNull();
    expect(approvalDetail(APPROVAL)).toBe(PromptApprovalChanges);
  });

  it("shows the replay and the decided lines it adds and drops against the version in force", async () => {
    draw();
    expect(
      await screen.findByText(
        "Đọc đúng 19/20 dòng đã quyết (bản đang dùng: 0/20) · Qua cả 9 ca bảo mật",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Thêm 1 dòng mẫu")).toBeTruthy();
    expect(screen.getByText(ADDED.description)).toBeTruthy();
    expect(screen.getByText("Bỏ 1 dòng mẫu")).toBeTruthy();
    expect(screen.getByText(DROPPED.description)).toBeTruthy();
    expect(screen.getByText("Giữ 1 dòng mẫu như bản đang dùng.")).toBeTruthy();
    // Which decided line it came from: the customer, and its order.
    expect(screen.getByText(/khách C001/)).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "Mở đơn" }).getAttribute("href"),
    ).toBe(`/sales/orders/${CASE}`);
  });

  it("says why it is not shown, and reads nothing, without sales.rules.approve", () => {
    scopes = ["sales.rules.propose"];
    draw();
    expect(screen.getByText(/Chỉ người có quyền duyệt quy tắc/)).toBeTruthy();
    expect(api.prompts).not.toHaveBeenCalled();
  });

  it("compares nothing once the version is decided", async () => {
    versions = [version("rejected", [ADDED])];
    draw();
    expect(
      await screen.findByText(
        "Phiên bản sales_prompt_description_attributes@1.3.0: đã từ chối.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText("Thêm 1 dòng mẫu")).toBeNull();
  });
});
