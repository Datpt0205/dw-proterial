"use client";

import Link from "next/link";
import { Alert, Descriptions, Space, Typography } from "antd";
import type { Approval } from "@dw/contracts";
import { bravoWriteValue, type BravoWriteField } from "../_lib/bravo-write";
import { BRAVO_WRITE_FIELD, label } from "../_lib/labels";

const CASE_ID = /^[0-9a-f-]{36}$/i;

function isField(value: unknown): value is BravoWriteField {
  return typeof value === "string" && value in BRAVO_WRITE_FIELD;
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/**
 * A `bravo_write.sales_order` approval (tickets 53, 71), where its one
 * decider decides it (`/approvals`): the SO line, Bravo's value and the new
 * one, and the content's hash the decision is bound to (ui-quality §10).
 * Drawn from the approval's own payload, which the server checks against
 * the proposal before it signs (`BravoWriteDecisions`).
 */
export function BravoWriteApprovalChanges({
  approval,
}: {
  approval: Approval;
}) {
  const p = approval.payload;
  const field = p.field;
  if (!isField(field)) return null;
  const caseId = String(p.case_id ?? "");
  return (
    <Space orientation="vertical" className="w-full">
      {field === "cancel" ? (
        <Alert
          type="warning"
          showIcon
          title="Hủy dòng: Bravo đưa số lượng và thành tiền của dòng về 0 và ghi lý do vào cột lý do hủy."
        />
      ) : null}
      <Descriptions
        size="small"
        bordered
        column={1}
        items={[
          { key: "so", label: "SO Bravo", children: String(p.so_no ?? "") },
          { key: "line", label: "Dòng", children: String(p.line_no ?? "") },
          {
            key: "item",
            label: "Mã hàng",
            children: String(p.item_code ?? ""),
          },
          {
            key: "field",
            label: "Đổi gì",
            children: label(BRAVO_WRITE_FIELD, field),
          },
          {
            key: "change",
            label: "Trong Bravo → sau khi ghi",
            children: (
              <span className="whitespace-pre-wrap break-words">
                {`${bravoWriteValue(field, text(p.before))} → ${bravoWriteValue(field, text(p.after))}`}
              </span>
            ),
          },
          {
            key: "hash",
            label: "Mã nội dung",
            children: (
              <Typography.Text code>
                {(text(p.content_hash) ?? "").slice(0, 8)}
              </Typography.Text>
            ),
          },
        ]}
      />
      {CASE_ID.test(caseId) ? (
        <Link href={`/sales/orders/${caseId}`}>Mở hồ sơ đơn hàng</Link>
      ) : null}
    </Space>
  );
}
