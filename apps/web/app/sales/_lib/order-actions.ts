import type { SalesSchemas } from "@dw/api-client";
import { FINDING_CODE, label, SALES_ROLE } from "./labels";

type Order = SalesSchemas["OrderCaseView"];
type Finding = SalesSchemas["OrderFindingView"];

/**
 * Which order steps this screen offers in which state, and why one is refused,
 * in words (ui-quality §5).
 *
 * Display only. The owner of every rule here is `OrderCase` in
 * `dw_sales.domain.orders`, which refuses each step whatever this file says;
 * a refusal the screen did not foresee arrives as the server's 409 and is
 * drawn beside the button. Where the case carries the answer (its `makers`,
 * each finding's `allowed`, `cross_check_required`, `export_control_mode`),
 * it is read from the case, never re-derived.
 */
export interface Viewer {
  principalId: string | null;
  hasScope: (scope: string) => boolean;
}

export type OrderAction =
  | "prepare"
  | "correction"
  | "bravo"
  | "applyChange"
  | "crossCheck"
  | "returnOrder"
  | "confirm"
  | "close";

/** Shown in this state; `reason` is null when it can be pressed now. */
export interface Offer {
  reason: string | null;
}

/** The rule WIV-03-012 step 9 names, as the case's own refusal says it. */
export const MAKER_CHECKER = "tách nhiệm, WIV-03-012 bước 9";

const PIC = label(SALES_ROLE, "sales_pic");
const EXPORT_PIC = label(SALES_ROLE, "sales_export_control");

// The states a step is offered in (the domain's `_NEXT`, read as buttons).
const BEFORE_UPLOAD = [
  "received",
  "checked",
  "in_review",
  "correction_requested",
  "prepared",
];
/** Where lines, mappings and dispositions are decided (`_EDITABLE`). */
export const EDITABLE = ["in_review", "prepared", "change_review"];
/** Where the export-control PIC acknowledges NOC/ESF (`_ACKNOWLEDGEABLE`). */
export const ACKNOWLEDGEABLE = [
  "in_review",
  "prepared",
  "uploaded_to_bravo",
  "cross_checked",
  "change_review",
];

export function isOpen(finding: Finding): boolean {
  return finding.disposition.kind === "open";
}

/** Open findings that block preparation: every open one but NOC/ESF. */
export function openBlockingPreparation(order: Order): Finding[] {
  return order.findings.filter(
    (f) => isOpen(f) && f.code !== "missing_noc_esf",
  );
}

/** Lines whose PRV code Bravo cannot take yet. */
export function unmappedLines(order: Order): number[] {
  return order.lines
    .filter((l) => !["exact", "candidate_confirmed"].includes(l.mapping.status))
    .map((l) => l.line_no);
}

/** Lines with a short lead time and no date PC agreed. */
export function shortLeadTimeWaiting(order: Order): number[] {
  const short = new Set(
    order.findings
      .filter((f) => f.code === "requested_date_short_lt")
      .map((f) => f.line_no),
  );
  return order.lines
    .filter((l) => short.has(l.line_no) && !l.pc_confirmed_by)
    .map((l) => l.line_no);
}

/**
 * Why this person may not cross-check: they are one of the case's makers. The
 * case's `makers` list is the stamp (preparer, Bravo recorder and whoever
 * typed a value, this round or an earlier one); the sentence names the role
 * they played where the case says which.
 */
export function makerReason(order: Order, viewer: Viewer): string | null {
  const me = viewer.principalId;
  if (!me) return null;
  if (order.prepared_by === me)
    return `Bạn đã chuẩn bị đơn này nên không tự kiểm chéo được (${MAKER_CHECKER}).`;
  if (order.bravo_recorded_by === me)
    return `Bạn đã nhập Bravo cho đơn này nên không tự kiểm chéo được (${MAKER_CHECKER}).`;
  if (order.makers.includes(me))
    return `Bạn đã làm một phần hồ sơ này (chuẩn bị, nhập Bravo hoặc nhập tay một giá trị, ở vòng này hoặc vòng trước) nên không tự kiểm chéo được (${MAKER_CHECKER}).`;
  return null;
}

const NOT_SERVED =
  "Chưa mở nguồn: mở bản gốc của phiên bản hồ sơ này trước khi quyết định.";

/**
 * The cross-check is decided on the platform approval DW1's run paused on
 * (`order.decision`); with none open there is nothing to decide yet.
 */
export const NO_CROSS_CHECK_REQUEST =
  "Chưa có yêu cầu kiểm chéo đang chờ cho đơn này: tải lại trang; nếu vẫn chưa có, báo bộ phận hỗ trợ.";

export function orderOffers(
  order: Order,
  viewer: Viewer,
  { sourceOpened }: { sourceOpened: boolean },
): Partial<Record<OrderAction, Offer>> {
  const offers: Partial<Record<OrderAction, Offer>> = {};
  const status = order.status;
  const canPrepare = viewer.hasScope("sales.order.prepare");
  const noPrepare = `Bạn không có quyền làm bước này của đơn hàng (cần vai ${PIC}).`;
  const asked = order.findings.filter(
    (f) => f.disposition.kind === "ask_customer",
  );

  if (status === "in_review") {
    const open = openBlockingPreparation(order);
    const unmapped = unmappedLines(order);
    offers.prepare = {
      reason: !canPrepare
        ? noPrepare
        : open.length
          ? `Còn ${open.length} cờ chưa quyết định.`
          : asked.length
            ? `Có ${asked.length} cờ "Yêu cầu khách sửa": gửi yêu cầu sửa cho khách, không chuẩn bị xong.`
            : unmapped.length
              ? `Dòng ${unmapped.join(", ")} chưa có mã PRV.`
              : !sourceOpened
                ? NOT_SERVED
                : null,
    };
    if (asked.length)
      offers.correction = {
        reason: !canPrepare
          ? noPrepare
          : open.length
            ? `Còn ${open.length} cờ chưa quyết định: quyết định hết rồi gửi một lần.`
            : null,
      };
  }

  if (status === "prepared")
    offers.bravo = { reason: canPrepare ? null : noPrepare };

  if (status === "change_review") {
    const open = openBlockingPreparation(order);
    offers.applyChange = {
      reason: !canPrepare
        ? noPrepare
        : open.length
          ? `Còn ${open.length} cờ của bản sửa chưa quyết định.`
          : null,
    };
  }

  if (status === "uploaded_to_bravo" && order.cross_check_required !== false) {
    const reason = !viewer.hasScope("sales.order.cross_check")
      ? `Bạn không có quyền kiểm chéo đơn (cần vai ${PIC}).`
      : (makerReason(order, viewer) ??
        (!sourceOpened
          ? NOT_SERVED
          : order.decision
            ? null
            : NO_CROSS_CHECK_REQUEST));
    offers.crossCheck = { reason };
    offers.returnOrder = { reason };
  }

  const confirmable =
    status === "cross_checked" ||
    (status === "uploaded_to_bravo" && order.cross_check_required === false);
  if (confirmable) {
    const noc = order.findings.filter((f) => f.code === "missing_noc_esf");
    const waiting = shortLeadTimeWaiting(order);
    offers.confirm = {
      reason: !canPrepare
        ? noPrepare
        : noc.some(isOpen)
          ? `"${label(FINDING_CODE, "missing_noc_esf")}" chưa được ${EXPORT_PIC} xác nhận.`
          : noc.length && order.export_control_mode === "block_confirmation"
            ? `Quy tắc kiểm soát xuất khẩu đang chặn xác nhận đơn có cờ "${label(FINDING_CODE, "missing_noc_esf")}".`
            : waiting.length
              ? `Dòng ${waiting.join(", ")} có ngày yêu cầu ngắn hơn lead time và chưa ghi PC đồng ý.`
              : null,
    };
  }

  if (BEFORE_UPLOAD.includes(status))
    offers.close = { reason: canPrepare ? null : noPrepare };

  return offers;
}

/**
 * A finding's controls: null where the case's state does not take a decision
 * on it (not offered at all), else the reason they are refused, or none.
 */
export function dispositionOffer(
  order: Order,
  finding: Finding,
  viewer: Viewer,
): Offer | null {
  if (finding.code === "missing_noc_esf") {
    if (!ACKNOWLEDGEABLE.includes(order.status)) return null;
    return {
      reason: viewer.hasScope("sales.compliance.ack")
        ? null
        : `Chỉ ${EXPORT_PIC} xác nhận cờ này.`,
    };
  }
  if (!EDITABLE.includes(order.status)) return null;
  return {
    reason: viewer.hasScope("sales.order.prepare")
      ? null
      : `Bạn không có quyền quyết định cờ (cần vai ${PIC}).`,
  };
}
