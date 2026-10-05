import type { SalesSchemas } from "@dw/api-client";
import { label, SALES_ROLE } from "./labels";
import type { Offer, Viewer } from "./order-actions";

type Quote = SalesSchemas["QuoteCaseView"];

/**
 * Which quotation steps the screen offers in which state, and why one is
 * refused, in words. Display only: `QuoteCase` in `dw_sales.domain.quotes`
 * owns every move and refuses whatever this file says.
 */
export type QuoteAction =
  | "draftYcbg"
  | "recordYcbg"
  | "designSent"
  | "specStart"
  | "specSettle"
  | "specAskDesign"
  | "price"
  | "submit"
  | "approve"
  | "returnPrice"
  | "sent"
  | "masterList"
  | "decline";

/** The rule WIV-03-023 step 9 names. */
export const PRICER_APPROVER = "tách nhiệm, WIV-03-023 bước 9";

const PIC = label(SALES_ROLE, "sales_pic");
const HEAD = label(SALES_ROLE, "sales_head");
const DEPUTY = label(SALES_ROLE, "sales_quote_approver");

const BEFORE_SENT = [
  "received",
  "ycbg_drafted",
  "ycbg_recorded",
  "sent_to_design",
  "design_replied",
  "spec_discussion",
  "priced",
  "pending_approval",
  "returned",
  "approved",
];

/** Who priced the quote: the one person who may not approve it. */
export function pricer(quote: Quote): string | null {
  return quote.submission?.priced_by ?? quote.pricing?.decided_by ?? null;
}

/** Why this viewer may not approve or return this quote; null if they may. */
export function approvalReason(quote: Quote, viewer: Viewer): string | null {
  if (!viewer.hasScope("sales.quote.approve"))
    return `Bạn không có quyền duyệt báo giá (cần vai ${HEAD} hoặc quyền "${DEPUTY}").`;
  if (viewer.principalId && pricer(quote) === viewer.principalId)
    return `Bạn đã định giá báo giá này nên không tự duyệt được (${PRICER_APPROVER}).`;
  return null;
}

export function quoteOffers(
  quote: Quote,
  viewer: Viewer,
): Partial<Record<QuoteAction, Offer>> {
  const offers: Partial<Record<QuoteAction, Offer>> = {};
  const status = quote.status;
  const prep = viewer.hasScope("sales.quote.prepare")
    ? null
    : `Bạn không có quyền làm bước này của báo giá (cần vai ${PIC}).`;
  const intake = quote.findings.filter(
    (f) =>
      ["rfq_incomplete", "customer_unknown"].includes(f.code) &&
      f.disposition.kind === "open",
  );
  const intakeReason = intake.length
    ? `Còn ${intake.length} thông tin của yêu cầu báo giá chưa đủ: bổ sung trước khi soạn YCBG.`
    : null;

  if (status === "received") {
    offers.draftYcbg = { reason: prep ?? intakeReason };
    offers.recordYcbg = { reason: prep ?? intakeReason };
  }
  if (status === "ycbg_drafted") offers.recordYcbg = { reason: prep };
  if (status === "ycbg_recorded") offers.designSent = { reason: prep };
  if (status === "design_replied") {
    offers.price = { reason: prep };
    offers.specStart = { reason: prep };
  }
  if (status === "spec_discussion") {
    offers.specSettle = { reason: prep };
    offers.specAskDesign = { reason: prep };
  }
  if (["priced", "returned", "pending_approval", "approved"].includes(status))
    offers.price = { reason: prep };
  if (status === "priced") offers.submit = { reason: prep };
  if (status === "pending_approval") {
    const reason = approvalReason(quote, viewer);
    offers.approve = { reason };
    offers.returnPrice = { reason };
  }
  if (status === "approved") offers.sent = { reason: prep };
  if (status === "sent") offers.masterList = { reason: prep };
  if (BEFORE_SENT.includes(status)) offers.decline = { reason: prep };
  return offers;
}
