import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";
import type { Approval } from "@dw/contracts";

const SCHEMAS = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../../../contracts/jsonschema/sales_rules.json",
    ),
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
const LEARNED = "0aa10aa0-c939-7000-8539-31fd3e621703";
const LEARNED_RULES = {
  columns: [
    {
      column: "AF",
      field: "requested_date",
      customer: null,
      steps: [{ step: "shift_days", days: -10 }],
    },
  ],
};
const learned = (version: string, customers: Record<string, unknown>) => ({
  schema_version: "1.0",
  policy_id: "sales_salesorder_rules",
  policy_version: version,
  mock: false,
  description: "",
  customers,
});
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
    in_force: {
      sales_kpi: "sales_kpi@1.0.0",
      sales_salesorder_rules: "sales_salesorder_rules@1.0.0",
    },
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
      {
        ...base,
        key: "sales_salesorder_rules",
        version_id: LEARNED,
        version: "1.0.1",
        ref: "sales_salesorder_rules@1.0.1",
        status: "proposed",
        decided_by: null,
        decided_at: null,
        document: learned("1.0.1", { KHB: LEARNED_RULES }),
      },
    ],
  })),
  ruleSchema: vi.fn(async (key: string) => ({
    key,
    json_schema: SCHEMAS[key]!,
  })),
  rulePlatformDocuments: vi.fn(async (key: string) =>
    key === "sales_salesorder_rules"
      ? [
          {
            key,
            ref: "sales_salesorder_rules@1.0.0",
            version: "1.0.0",
            current: true,
            document: learned("1.0.0", {}),
          },
        ]
      : [
          {
            key: "sales_kpi",
            ref: "sales_kpi@1.0.0",
            version: "1.0.0",
            current: true,
            document: kpi("1.0.0", 8),
          },
        ],
  ),
  salesOrderExampleOfVersion: vi.fn(async () => ({
    example_id: "e-1",
    customer_code: "KHB",
    status: "submitted",
    requested_by: "u-1",
    requested_at: "2026-11-14T02:00:00Z",
    received_on: "2026-11-06",
    po_file_name: "KHB-PO-7781.xlsx",
    salesorder_file_name: "SalesOrder.xlsx",
    rules: LEARNED_RULES,
    replay: {
      layout_ref: "sales_bravo_upload@2.0.0",
      rows_expected: 2,
      rows_got: 2,
      cells_compared: 36,
      differences_total: 0,
      differences: [],
      left_blank: [],
    },
    submittable: false,
    problems: [],
    error: null,
    prompt_ref: null,
    model_profile: null,
    version_id: LEARNED,
  })),
};
vi.mock("../../_lib/api", () => ({ salesApi: () => api }));

import { approvalDetail } from "../../../../lib/approvals/registry";
import { RuleApprovalChanges } from "../rule-approval";

function approval(
  approval_type: string,
  payload: Record<string, unknown>,
): Approval {
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

  it("shows each field the version changes against the one in force", async () => {
    render(
      <UiProvider>
        <RuleApprovalChanges approval={RULES} />
      </UiProvider>,
    );
    expect(
      await screen.findByText("2 thay đổi so với sales_kpi@1.0.0."),
    ).toBeTruthy();
    const row = screen
      .getByText("Mục tiêu xác nhận đơn hàng", { selector: "strong" })
      .closest("tr")!;
    expect(within(row).getByText("8")).toBeTruthy();
    expect(within(row).getByText("6")).toBeTruthy();
    expect(api.ruleSchema).toHaveBeenCalledWith("sales_kpi");
  }, 20_000);

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

describe("a customer's learned SalesOrder rules where the head decides them (ticket 38)", () => {
  it("names the customers changed, the rules in words and the replay they were sent from", async () => {
    render(
      <UiProvider>
        <RuleApprovalChanges
          approval={approval("sales.rules", {
            approval_type: "sales.rules",
            key: "sales_salesorder_rules",
            version: "1.0.1",
            version_id: LEARNED,
          })}
        />
      </UiProvider>,
    );
    expect(
      await screen.findByText("36 ô khớp · 0 ô khác · 2 dòng"),
    ).toBeTruthy();
    expect(screen.getByText(/Khách có quy tắc mới hoặc đổi: KHB/)).toBeTruthy();
    expect(screen.getByText("AF ← requested_date: lùi 10 ngày")).toBeTruthy();
    expect(api.salesOrderExampleOfVersion).toHaveBeenCalledWith(LEARNED);
  }, 20_000);
});
