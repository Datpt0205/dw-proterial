"use client";

import { useState } from "react";
import Link from "next/link";
import { Alert, Card, Space, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";
import { formatDateTime } from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import type { Viewer } from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { GuardedButton } from "../../_components/guarded-button";
import { QuoteStateTag } from "../../_components/tags";

type Order = SalesSchemas["OrderCaseView"];

const PREPARE = "sales.order.prepare";
const QUOTE = "sales.quote.prepare";
// Where a quote is opened from the order (`OrderCase.open_quote`): in review,
// before the self-check.
const QUOTABLE: readonly string[] = ["checked", "in_review"];
// A quote whose approved terms the order's lines are checked against.
const APPROVED: readonly string[] = [
  "approved",
  "sent",
  "master_list_recorded",
];

/** Why "Mở báo giá" cannot be pressed now; null when it can. The server
 * refuses the same, whatever this says. */
export function openQuoteReason(order: Order, viewer: Viewer): string | null {
  if (!viewer.hasScope(PREPARE) || !viewer.hasScope(QUOTE))
    return "Cần quyền ghi trên đơn hàng và trên hồ sơ báo giá.";
  if (!QUOTABLE.includes(order.status))
    return "Chỉ mở báo giá khi đơn đang xem xét, trước khi tự kiểm xong.";
  if (order.quote_links.some((link) => link.waiting))
    return "Đã có hồ sơ báo giá mở từ đơn này, đang chờ duyệt.";
  return null;
}

/**
 * "Mở báo giá" (ticket 09), on a line with no valid quotation: a quote case
 * for the customer and every such line of the order, which then waits on it.
 * A person presses it; DW1 never opens one by itself.
 */
export function OpenQuoteButton({
  order,
  viewer,
  onOpened,
}: {
  order: Order;
  viewer: Viewer;
  onOpened: () => void;
}) {
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const open = async () => {
    const result = await run(
      "quote/open",
      { version: order.case_version },
      (key) => salesApi().openQuote(order.case_id, order.case_version, key),
      "Đã mở hồ sơ báo giá",
    );
    if (result.ok) {
      setError(null);
      onOpened();
    } else setError(result.error);
  };
  return (
    <Space orientation="vertical" size={4}>
      <GuardedButton
        size="small"
        reason={openQuoteReason(order, viewer)}
        loading={pending === "quote/open"}
        onClick={() => void open()}
      >
        Mở báo giá
      </GuardedButton>
      <ActionError error={error} />
    </Space>
  );
}

/**
 * The quote cases opened from the order: each one's status and a link to it,
 * the wait while one is open, and "Kiểm tra lại" once one is approved and a
 * line it was opened for still reads no quotation.
 */
export function QuoteLinksPanel({
  order,
  viewer,
  onChanged,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
}) {
  const name = usePeople();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  if (!order.quote_links.length) return null;
  const missing = new Set(
    order.findings
      .filter((f) => f.code === "quotation_missing")
      .map((f) => f.line_no),
  );
  const waiting = order.quote_links.some((link) => link.waiting);
  const recheckable = order.quote_links.some(
    (link) =>
      link.status !== null &&
      APPROVED.includes(link.status) &&
      link.lines.some((line) => missing.has(line)),
  );
  const recheck = async () => {
    const result = await run(
      "quote/check",
      { version: order.case_version },
      (key) =>
        salesApi().recheckQuotedLines(order.case_id, order.case_version, key),
      "Đã kiểm tra lại theo báo giá",
    );
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };
  return (
    <Card size="small" title="Báo giá mở từ đơn này">
      <Space orientation="vertical" className="w-full">
        {order.quote_links.map((link) => (
          <Space wrap key={link.quote_case_id}>
            {link.waiting ? (
              <StatusTag tone="warn">Đơn chờ báo giá</StatusTag>
            ) : null}
            <Link href={`/sales/quotes/${link.quote_case_id}`}>
              Hồ sơ báo giá · dòng {link.lines.join(", ")}
            </Link>
            {link.status ? <QuoteStateTag status={link.status} /> : null}
            <Typography.Text type="secondary">
              {name(link.by)} mở lúc {formatDateTime(link.at)}
            </Typography.Text>
          </Space>
        ))}
        {waiting ? (
          <Alert
            type="warning"
            showIcon
            title="Chưa tự kiểm xong được cho tới khi báo giá được duyệt hoặc từ chối."
          />
        ) : null}
        {recheckable ? (
          <GuardedButton
            size="small"
            reason={
              viewer.hasScope(PREPARE)
                ? null
                : "Bạn không có quyền ghi trên đơn hàng (cần vai Sales phụ trách)."
            }
            loading={pending === "quote/check"}
            onClick={() => void recheck()}
          >
            Kiểm tra lại theo báo giá
          </GuardedButton>
        ) : null}
        <ActionError error={error} />
      </Space>
    </Card>
  );
}
