"use client";

import type { Approval } from "@dw/contracts";
import { approvalDetail } from "../lib/approvals/registry";

/**
 * What the approval's context draws about it (`ApprovalHost.detail`), on the
 * inbox and on the approval's own page alike: one lookup, both places.
 */
export function ApprovalHostDetail({ approval }: { approval: Approval }) {
  const Detail = approvalDetail(approval);
  return Detail ? <Detail approval={approval} /> : null;
}
