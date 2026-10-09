import type { Approval } from "@dw/contracts";
import type { ApprovalHost } from "../../../lib/approvals/types";

/** The case pages, by the `case_kind` a DW1 approval's payload names. */
const CASE_PAGE: Record<string, string> = {
  quote: "/sales/quotes",
  order: "/sales/orders",
};

/**
 * DW1's approvals (`sales.quote`, `sales.order.cross_check`) are decided on
 * their case's page, which sends the case version the decision is checked
 * against; `/approvals` sends none, so a decision there is refused. The
 * generic inbox links to the case instead. A payload that names no known
 * case links to the Sales work list, never outside the app.
 */
export const salesApprovalHost: ApprovalHost = {
  prefix: "sales.",
  inbox: {
    label: "Mở hồ sơ để quyết định",
    href: (approval: Approval) => {
      const kind = String(approval.payload.case_kind ?? "");
      const caseId = String(approval.payload.case_id ?? "");
      const page = CASE_PAGE[kind];
      return page && /^[0-9a-f-]{36}$/i.test(caseId)
        ? `${page}/${caseId}`
        : "/sales";
    },
  },
};
