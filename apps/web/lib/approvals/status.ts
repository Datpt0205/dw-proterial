import type { Approval } from "@dw/contracts";

/** An approval's status as a person reads it: the one label table, used by
 * the inbox and the approval's own page alike. */
export const APPROVAL_STATUS: Record<
  Approval["status"],
  { label: string; color: string }
> = {
  pending: { label: "Chờ quyết", color: "warning" },
  approved: { label: "Đã duyệt", color: "success" },
  rejected: { label: "Từ chối", color: "error" },
  cancelled: { label: "Đã hủy", color: "default" },
};
