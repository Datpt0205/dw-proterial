import { describe, expect, it, vi } from "vitest";
import type { Approval } from "@dw/contracts";

vi.mock("../../../../lib/session", () => ({ apiClient: () => ({}) }));

import { approvalInbox } from "../../../../lib/approvals/registry";

const CASE = "6f1c2a40-0d3e-4b8a-9f55-1c2d3e4f5a6b";

function approval(
  approval_type: string,
  payload: Record<string, unknown>,
): Approval {
  return {
    id: "a-1",
    approval_type,
    reason: "r",
    status: "pending",
    run_id: "run-1",
    payload,
    created_at: "2026-10-08T00:00:00Z",
    decided_at: null,
    requires_comment: true,
    required_scope: "sales.quote.approve",
    can_decide: true,
    requested_by_me: false,
  };
}

describe("a DW1 approval in the generic inbox", () => {
  it("links to its case, where the decision carries the case version", () => {
    expect(
      approvalInbox(
        approval("sales.quote", { case_kind: "quote", case_id: CASE }),
      ),
    ).toEqual({
      kind: "link",
      label: "Mở hồ sơ để quyết định",
      href: `/sales/quotes/${CASE}`,
    });
    expect(
      approvalInbox(
        approval("sales.order.cross_check", {
          case_kind: "order",
          case_id: CASE,
        }),
      ),
    ).toMatchObject({ href: `/sales/orders/${CASE}` });
  });

  it("never builds a path from a payload it does not recognise", () => {
    for (const payload of [
      {},
      { case_kind: "quote", case_id: "../../admin" },
      { case_kind: "elsewhere", case_id: CASE },
    ]) {
      expect(approvalInbox(approval("sales.quote", payload))).toMatchObject({
        kind: "link",
        href: "/sales",
      });
    }
  });

  it("leaves every other type on /approvals", () => {
    expect(approvalInbox(approval("memory.review", {}))).toBeNull();
  });
});
