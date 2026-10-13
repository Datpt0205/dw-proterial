import type { SupportHost } from "../../../lib/support/registry";

/**
 * Where FPT support lands under a grant of Sales' set (`sales.case_support`,
 * dw_sales ADR 0003 §5): the orders list, one of the five reads the set opens
 * (ticket 22). The work list and every write answer a support context with
 * 403, so a grant never opens on them. The shell's own banner is drawn.
 */
export const salesSupportHost: SupportHost = {
  scopeSetKeys: ["sales.case_support"],
  landing: () => "/sales/orders",
};
