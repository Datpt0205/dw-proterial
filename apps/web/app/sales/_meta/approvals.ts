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
 * generic inbox links to the case instead, and a PO layout's
 * (`sales.layout`, ticket 30) to the layouts page. A rule version's
 * (`sales.rules`, ticket 38) names no subject version (its document never
 * changes), so it is decided on `/approvals`; the rules page (`/sales/rules`)
 * shows the document and links to the approval, and decides nothing. A
 * payload that names no known case links to the Sales work list, never
 * outside the app.
 */
export const salesApprovalHost: ApprovalHost = {
  prefix: "sales.",
  inbox: {
    label: "Mở hồ sơ để quyết định",
    href: (approval: Approval) => {
      if (approval.approval_type === "sales.rules") return null;
      // A master-data import (ticket 41) is decided here too: its payload
      // names the list, the file and the counts; `/sales/master-data` shows
      // the preview and links to it.
      if (approval.approval_type === "sales.catalog") return null;
      if (approval.approval_type === "sales.layout") return "/sales/layouts";
      const kind = String(approval.payload.case_kind ?? "");
      const caseId = String(approval.payload.case_id ?? "");
      const page = CASE_PAGE[kind];
      return page && /^[0-9a-f-]{36}$/i.test(caseId)
        ? `${page}/${caseId}`
        : "/sales";
    },
  },
};
