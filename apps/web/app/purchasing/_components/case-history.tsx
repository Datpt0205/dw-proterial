"use client";

import type { ReactNode } from "react";
import { Flex, Timeline, Typography } from "antd";
import type { PurchaseCase } from "@dw/api-client";
import { formatDateTime } from "../../../lib/dates";
import { formatQuantity } from "../../../lib/money";
import { SOURCE, type Mark } from "../_lib/labels";
import type { Actor } from "../_lib/people";
import { MarkTag } from "./tags";

interface Step {
  at: string;
  what: string;
  by: Actor | null;
  mark?: Mark;
  note?: ReactNode;
}

/**
 * What happened to one case, oldest first, read from the stamps the case
 * carries (who, when, and what each step was made from). A step DW2's own
 * account took reads "DW2 (tự làm)"; a value the model read from words or a
 * text it wrote keeps its mark after a person moved the case on (ui-quality
 * §7), so "Máy đọc" never turns into a fact a person checked.
 */
export function caseSteps(
  c: PurchaseCase,
  actor: (id: string | null | undefined) => Actor,
): Step[] {
  const steps: Step[] = [
    {
      at: c.received_at,
      what: `Nhận yêu cầu (${SOURCE[c.source]})`,
      by: actor(c.received_by),
      mark: c.source === "mail" ? "machine_read" : "person",
    },
  ];
  if (c.review) {
    steps.push({
      at: c.review.asked_at,
      what: "DW2 đọc yêu cầu, chờ người xem lại",
      by: null,
      mark: "machine_read",
    });
    if (c.review.reviewed_at)
      steps.push({
        at: c.review.reviewed_at,
        what: "Đã xem lại yêu cầu máy đọc",
        by: actor(c.review.reviewed_by),
      });
  }
  if (c.approval)
    steps.push({
      at: c.approval.submitted_at,
      what: `Gửi duyệt: ${c.approval.tier_label}`,
      by: actor(c.approval.submitted_by),
    });
  if (c.decision)
    steps.push({
      at: c.decision.decided_at,
      what: c.decision.approved ? "Đã duyệt" : "Từ chối",
      by: actor(c.decision.decided_by),
      note: c.decision.comment || undefined,
    });
  if (c.rfq)
    steps.push({
      at: c.rfq.drafted_at,
      what: `Soạn ${c.rfq.drafts.length} thư hỏi giá`,
      by: actor(c.rfq.drafted_by),
      mark: c.rfq.drafts.some((d) => d.written_by === "model")
        ? "machine_written"
        : "template",
    });
  for (const offer of c.offers)
    steps.push({
      at: offer.recorded_at,
      what: `Ghi báo giá của ${offer.supplier_code} cho dòng ${offer.line_no}`,
      by: actor(offer.recorded_by),
      mark: offer.source === "mail" ? "machine_read" : "person",
    });
  if (c.reapproval) {
    steps.push({
      at: c.reapproval.approval.submitted_at,
      what: `Lựa chọn vượt hạn mức đã duyệt, gửi duyệt lại: ${c.reapproval.approval.tier_label}`,
      by: actor(c.reapproval.approval.submitted_by),
      mark: c.reapproval.explanation ? "machine_written" : undefined,
      note: c.reapproval.explanation ?? undefined,
    });
    if (c.reapproval.decision)
      steps.push({
        at: c.reapproval.decision.decided_at,
        what: c.reapproval.decision.approved
          ? "Đã duyệt lại"
          : "Từ chối lựa chọn",
        by: actor(c.reapproval.decision.decided_by),
        note: c.reapproval.decision.comment || undefined,
      });
  }
  if (c.selection)
    steps.push({
      at: c.selection.selected_at,
      what: "Chọn nhà cung cấp cho từng dòng",
      by: actor(c.selection.selected_by),
    });
  if (c.po)
    steps.push({
      at: c.po.drafted_at,
      what: `Soạn ${c.po.orders.length} PO nháp và file Bravo`,
      by: actor(c.po.drafted_by),
    });
  for (const t of c.tracking ?? []) {
    if (t.bravo_no && t.bravo_at)
      steps.push({
        at: t.bravo_at,
        what: `Ghi số PO Bravo ${t.bravo_no} cho ${t.po_ref}`,
        by: actor(t.bravo_by),
      });
    const confirmed = t.confirmation;
    if (confirmed) {
      steps.push({
        at: confirmed.read_at,
        what: confirmed.differences.length
          ? `Đọc xác nhận của nhà cung cấp cho ${t.po_ref}: khác đơn ở ${confirmed.differences.length} chỗ`
          : `Đọc xác nhận của nhà cung cấp cho ${t.po_ref}: khớp đơn`,
        by: actor(confirmed.read_by),
        mark: "machine_read",
      });
      if (confirmed.accepted_at)
        steps.push({
          at: confirmed.accepted_at,
          what: `Chấp nhận xác nhận cho ${t.po_ref}`,
          by: actor(confirmed.accepted_by),
        });
    }
    for (const r of t.receipts)
      steps.push({
        at: r.recorded_at,
        what: `Ghi nhận hàng về: ${t.po_ref} dòng ${r.line_no}, ${formatQuantity(r.quantity)}`,
        by: actor(r.recorded_by),
      });
  }
  const sorted = steps.sort((a, b) => a.at.localeCompare(b.at));
  // Moved there by the receipt that completed everything: its moment.
  const last = sorted[sorted.length - 1];
  if (c.status === "delivered" && last)
    sorted.push({ at: last.at, what: "Đã nhận đủ hàng", by: last.by });
  return sorted;
}

export function CaseHistory({
  c,
  actor,
}: {
  c: PurchaseCase;
  actor: (id: string | null | undefined) => Actor;
}) {
  return (
    <Timeline
      items={caseSteps(c, actor).map((step, index) => ({
        key: `${step.at}:${index}`,
        content: (
          <Flex vertical gap={2}>
            <Flex gap={8} wrap align="center">
              <Typography.Text strong>{step.what}</Typography.Text>
              {step.mark ? <MarkTag mark={step.mark} /> : null}
            </Flex>
            <Typography.Text>
              {formatDateTime(step.at)}
              {step.by?.name
                ? ` · ${step.by.machine ? `${step.by.name} (tự làm)` : step.by.name}`
                : ""}
            </Typography.Text>
            {step.note ? (
              <Typography.Paragraph className="mb-0">
                {step.note}
              </Typography.Paragraph>
            ) : null}
          </Flex>
        ),
      }))}
    />
  );
}
