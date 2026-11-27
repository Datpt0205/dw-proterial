import type { Approval } from "@dw/contracts";
import type { ApprovalHost } from "../../../lib/approvals/types";
import { BravoWriteApprovalChanges } from "./bravo-write-approval";
import { PromptApprovalChanges } from "./prompt-approval";
import { RuleApprovalChanges } from "./rule-approval";
import { SkillApprovalChanges } from "./skill-approval";

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
      // A prompt version DW1 proposed (ticket 43) is decided here too, its
      // lines drawn below; `/sales/rules/prompts` lists them.
      if (approval.approval_type === "sales.prompts") return null;
      // So is a skill version (ticket 40), its words drawn below;
      // `/sales/rules/skills` lists them.
      if (approval.approval_type === "sales.skills") return null;
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
  // A rule version is decided where it is listed, so its changes are drawn
  // there, under the payload (ticket 40), and so are a prompt version's
  // (ticket 43) and a skill version's.
  detail: (approval: Approval) => {
    if (approval.approval_type === "sales.rules") return RuleApprovalChanges;
    if (approval.approval_type === "sales.prompts")
      return PromptApprovalChanges;
    if (approval.approval_type === "sales.skills") return SkillApprovalChanges;
    return null;
  },
};

/**
 * A DW1 line's write into Bravo (`bravo_write.sales_order`, tickets 53, 71):
 * not under `sales.`, because its one decider is the person whose Bravo user
 * writes it, and it is decided on `/approvals`, where this draws the SO line
 * and the change; the order page's "Ghi vào Bravo" panel links to it.
 */
export const salesBravoWriteHost: ApprovalHost = {
  prefix: "bravo_write.",
  detail: (approval: Approval) =>
    approval.approval_type === "bravo_write.sales_order"
      ? BravoWriteApprovalChanges
      : null,
};
