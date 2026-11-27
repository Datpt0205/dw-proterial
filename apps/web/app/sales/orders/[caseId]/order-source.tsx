"use client";

import { useCallback, useState, type ReactNode } from "react";
import type { SalesSchemas, SourceRegion } from "@dw/api-client";
import { salesApi } from "../../_lib/api";
import type { Viewer } from "../../_lib/order-actions";
import { anchorRegion, mailRange, markMailServed } from "../../_lib/served";
import {
  MailTextDrawer,
  type MailTarget,
} from "../../_components/mail-text-drawer";
import {
  SourceDrawer,
  type SourceTarget,
} from "../../_components/source-drawer";

type Order = SalesSchemas["OrderCaseView"];
type Anchor = SalesSchemas["SourceAnchor"];

/** Where a value of the order was read: a header field, or a line's field. */
export function anchorOf(
  order: Order,
  field: string,
  lineNo: number | null,
): Anchor | null {
  // `print:<n>`: where the PDF print shows a value differently (ticket 34).
  const printed = /^print:(\d+)$/.exec(field);
  if (printed)
    return order.print_copy?.differences[Number(printed[1])]?.anchor ?? null;
  if (lineNo === null)
    return (
      order.header_anchors[field] ??
      (field === "total"
        ? order.total_anchor
        : field === "buyer"
          ? order.buyer_anchor
          : field === "legacy_text"
            ? order.legacy_text_anchor
            : null) ??
      null
    );
  const line = order.lines.find((l) => l.line_no === lineNo);
  // `schedule:<n>`: one delivery schedule of a split line (ticket 21).
  const schedule = /^schedule:(\d+)$/.exec(field);
  if (schedule) return line?.schedules[Number(schedule[1])]?.anchor ?? null;
  return line?.anchors[field] ?? line?.anchors.description ?? null;
}

/**
 * Where an order's values open their source: the file's page or sheet in
 * `SourceDrawer`, or, for a PO written in the mail (AI item 4), the mail's
 * text, whose serving is marked so the case's source gates see it. One owner
 * for the case page and the item in "Việc của tôi" (ticket 79). `null` while
 * the order loads: nothing opens and no drawer is drawn.
 */
export function useOrderSource(order: Order | null): {
  /** Open where `field` (of line `lineNo`, or the header) was read. */
  open: (field: string, lineNo: number | null) => void;
  /** Open one region of the file, as the "Mở nguồn" of an unopened one. */
  openRegion: (region: SourceRegion) => void;
  /** The drawers, for a viewer: the mail's text asks `sales.price.read`. */
  drawers: (viewer: Viewer) => ReactNode;
} {
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [mail, setMail] = useState<MailTarget | null>(null);
  const caseId = order?.case_id ?? "";
  const loadMail = useCallback(
    () => salesApi().orderMessageText(caseId),
    [caseId],
  );
  const mailServed = useCallback(
    (version: number) => markMailServed(caseId, version),
    [caseId],
  );

  const open = (field: string, lineNo: number | null) => {
    if (!order) return;
    const anchor = anchorOf(order, field, lineNo);
    if (order.attachment_id === null) {
      const range = mailRange(anchor) ?? mailRange(order.header_anchors.po_no);
      if (range) setMail({ field, lineNo, ...range });
      return;
    }
    const region =
      anchorRegion(anchor) ?? anchorRegion(order.header_anchors.po_no);
    if (region) setSource({ region, field, lineNo });
  };

  const openRegion = (region: SourceRegion) =>
    setSource({ region, field: "po_no", lineNo: null });

  const drawers = (viewer: Viewer) =>
    !order ? null : order.attachment_id !== null ? (
      <SourceDrawer
        kind="order"
        caseId={order.case_id}
        caseVersion={order.case_version}
        attachmentId={order.attachment_id}
        target={source}
        onClose={() => setSource(null)}
      />
    ) : (
      <MailTextDrawer
        resourceKey={`sales/order/${order.case_id}/${order.case_version}/message-text`}
        load={loadMail}
        target={mail}
        mayRead={viewer.hasScope("sales.price.read")}
        onClose={() => setMail(null)}
        onServed={mailServed}
      />
    );

  return { open, openRegion, drawers };
}
