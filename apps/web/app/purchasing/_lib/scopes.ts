/**
 * The DW2 scopes a page reads to choose what to offer. Navigation and
 * disabling only: every route checks its scope again
 * (`dw_purchasing.application.access.PurchasingScopes`).
 */
export const SCOPE = {
  read: "purchasing.request.read",
  readOwn: "purchasing.request.read_own",
  create: "purchasing.request.create",
  intake: "purchasing.request.intake",
  submit: "purchasing.request.submit",
  rfq: "purchasing.rfq.prepare",
  po: "purchasing.po.prepare",
  download: "purchasing.po.download",
  propose: "purchasing.rules.propose",
  rulesApprove: "purchasing.rules.approve",
  approveLast: "purchasing.approve.tier3",
  decide: "approvals.decide",
} as const;
