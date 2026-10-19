import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Approval } from "@dw/contracts";

const SCHEMAS = JSON.parse(
  readFileSync(
    resolve(__dirname, "../../../../../../contracts/jsonschema/sales_rules.json"),
    "utf-8",
  ),
) as Record<string, Record<string, unknown>>;

let scopes = ["sales.rules.propose", "sales.rules.approve"];
vi.mock("../../../../lib/auth/auth-context", () => ({
  useAuth: () => ({
    active: { workspaceId: "w-1" },
    hasScope: (scope: string) => scopes.includes(scope),
  }),
}));
vi.mock("../../../../lib/session", () => ({ apiClient: () => ({}) }));

const kpi = (version: string, hours: number) => ({
  schema_version: "1.0",
  policy_id: "sales_kpi",
  policy_version: version,
  order_confirmation_target_hours: hours,
  quotation_target_days: 1,
  manual_baseline_minutes: { O1: 5 },
});

const PROPOSED = "0aa10aa0-c939-7000-8539-31fd3e621702";
const base = {
  key: "sales_kpi",
  layer: "tenant",
  proposed_by: "u-1",
  proposed_at: "2026-10-14T02:00:00Z",
  comment: null,
  approval_id: "a-1",
};

const api = {
  rules: vi.fn(async () => ({
    in_force: { sales_kpi: "sales_kpi@1.0.0" },
    layers: { sales_kpi: "platform" },
    platform: [{ key: "sales_kpi", ref: "sales_kpi@1.0.0" }],
    versions: [
      {
        ...base,
        version_id: PROPOSED,
        version: "1.0.1",
        ref: "sales_kpi@1.0.1",
        status: "proposed",
        decided_by: null,
        decided_at: null,
        document: kpi("1.0.1", 6),
      },
    ],
  })),
  ruleSchema: vi.fn(async (key: string) => ({ key, json_schema: SCHEMAS[key]! })),
  rulePlatformDocuments: vi.fn(async () => [
    {
      key: "sales_kpi",
      ref: "sales_kpi@1.0.0",
      version: "1.0.0",
      current: true,
      document: kpi("1.0.0", 8),
    },
  ]),
};
vi.mock("../../_lib/api", () => ({ salesApi: () => api }));

import { approvalDetail } from "../../../../lib/approvals/registry";
import { RuleApprovalChanges } from "../rule-approval";

function approval(approval_type: string, payload: Record<string, unknown>): Approval {
  return {
    id: "a-1",
    approval_type,
    reason: "r",
    status: "pending",
    run_id: null,
    payload,
    created_at: "2026-10-14T02:00:00Z",
    decided_at: null,
    requires_comment: true,
    required_scope: "sales.rules.approve",
    can_decide: true,
    requested_by_me: false,
  } as Approval;
}

const RULES = approval("sales.rules", {
  approval_type: "sales.rules",
  key: "sales_kpi",
  version: "1.0.1",
  version_id: PROPOSED,
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  scopes = ["sales.rules.propose", "sales.rules.approve"];
});

describe("a rule version's changes where the head decides it (ticket 40)", () => {
  it("is drawn for sales.rules only", () => {
    expect(approvalDetail(RULES)).toBe(RuleApprovalChanges);
    expect(approvalDetail(approval("sales.layout", {}))).toBeNull();
    expect(approvalDetail(approval("tool.call", {}))).toBeNull();
  });

  it(
    "shows each field the version changes against the one in force",
    async () => {
      render(
        <UiProvider>
          <RuleApprovalChanges approval={RULES} />
        </UiProvider>,
      );
      expect(await screen.findByText("2 thay đổi so với sales_kpi@1.0.0.")).toBeTruthy();
      const row = screen
        .getByText("Mục tiêu xác nhận đơn hàng", { selector: "strong" })
        .closest("tr")!;
      expect(within(row).getByText("8")).toBeTruthy();
      expect(within(row).getByText("6")).toBeTruthy();
      expect(api.ruleSchema).toHaveBeenCalledWith("sales_kpi");
    },
    20_000,
  );

  it("says why it is not shown, and reads nothing, without sales.rules.propose", () => {
    scopes = ["sales.rules.approve"];
    render(
      <UiProvider>
        <RuleApprovalChanges approval={RULES} />
      </UiProvider>,
    );
    expect(screen.getByText(/Chỉ người có quyền đề xuất quy tắc/)).toBeTruthy();
    expect(api.rules).not.toHaveBeenCalled();
  });
});
