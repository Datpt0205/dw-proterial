"use client";

import { useCallback, useMemo } from "react";
import Link from "next/link";
import { Card, Space, Table, Typography } from "antd";
import { CheckCircleOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatAge, formatDateTime } from "../../../lib/dates";
import { useNow } from "../../../lib/use-now";
import { salesApi } from "../_lib/api";
import { label, SALES_ROLE } from "../_lib/labels";
import { MAKER_CHECKER } from "../_lib/order-actions";
import { usePeople } from "../_lib/people";
import { PRICER_APPROVER } from "../_lib/quote-actions";
import { useResource } from "../_lib/use-resource";
import { useSalesViewer } from "../_lib/viewer";
import { SCOPE } from "../_components/sales-frame";
import { salesCrumbs } from "../_components/crumbs";
import { ScopeGate } from "../_components/scope-gate";
import { OrderStateTag, QuoteStateTag } from "../_components/tags";

type Order = SalesSchemas["OrderSummaryView"];
type Quote = SalesSchemas["QuoteSummaryView"];

/**
 * Kiểm chéo & duyệt (V3Approvals re-cut): orders waiting for their
 * cross-check and quotes waiting for approval, each saying whether the viewer
 * may take it. Whether they may is read from `my-work`, which the API builds
 * with the maker/checker rule; the screen does not decide it again. One item
 * at a time: each opens its case, where the decision is made.
 */
export default function ReviewPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Review />
    </ScopeGate>
  );
}

function Review() {
  const now = useNow();
  const name = usePeople();
  const viewer = useSalesViewer();
  const orders = useResource(
    "sales/orders",
    useCallback(() => salesApi().orders(), []),
  );
  const quotes = useResource(
    "sales/quotes",
    useCallback(() => salesApi().quotes(), []),
  );
  const work = useResource(
    "sales/my-work",
    useCallback(() => salesApi().myWork(), []),
  );
  const mine = useMemo(
    () =>
      new Set((work.data ?? []).map((w) => `${w.kind}:${w.id}:${w.action}`)),
    [work.data],
  );

  const checks = (orders.data ?? []).filter(
    (o) => o.status === "uploaded_to_bravo",
  );
  const approvals = (quotes.data ?? []).filter(
    (q) => q.status === "pending_approval",
  );

  const orderWhy = (o: Order) =>
    mine.has(`order:${o.case_id}:cross_check`)
      ? null
      : !viewer.hasScope("sales.order.cross_check")
        ? `Bạn không có quyền kiểm chéo đơn (cần vai ${label(SALES_ROLE, "sales_pic")}).`
        : `Bạn đã làm một phần hồ sơ này nên không tự kiểm chéo được (${MAKER_CHECKER}).`;
  const quoteWhy = (q: Quote) =>
    mine.has(`quote:${q.case_id}:approve`)
      ? null
      : !viewer.hasScope("sales.quote.approve")
        ? `Bạn không có quyền duyệt báo giá (cần vai ${label(SALES_ROLE, "sales_head")} hoặc quyền "${label(SALES_ROLE, "sales_quote_approver")}").`
        : `Bạn đã định giá báo giá này nên không tự duyệt được (${PRICER_APPROVER}).`;

  const can = (why: string | null) =>
    why === null ? (
      <Typography.Text>
        <CheckCircleOutlined aria-hidden className="me-1" />
        Bạn làm được
      </Typography.Text>
    ) : (
      <Typography.Text role="note">{why}</Typography.Text>
    );

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Kiểm chéo & duyệt")}
        title="Kiểm chéo & duyệt"
        subtitle="Người làm hồ sơ không tự kiểm: đơn được một Sales khác kiểm chéo với Bravo, báo giá được người không định giá duyệt."
      />
      <Card size="small" title={`Đơn chờ kiểm chéo (${checks.length})`}>
        {orders.error ? (
          <LoadError error={orders.error} onRetry={orders.reload} />
        ) : (
          <Table<Order>
            rowKey="case_id"
            size="small"
            loading={orders.loading || work.loading}
            dataSource={checks}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: orders.loading
                ? " "
                : "Không có đơn nào chờ kiểm chéo.",
            }}
            columns={[
              {
                title: "Số PO",
                key: "po",
                render: (_, o) => (
                  <Link href={`/sales/orders/${o.case_id}`}>
                    {o.po_no}
                    {o.revision ? ` · Rev.${o.revision}` : ""}
                  </Link>
                ),
              },
              { title: "Khách", dataIndex: "customer_code" },
              {
                title: "Trạng thái",
                key: "s",
                render: (_, o) => <OrderStateTag status={o.status} />,
              },
              {
                title: "Phụ trách",
                key: "a",
                render: (_, o) =>
                  o.assigned_to ? name(o.assigned_to) : "Chưa giao",
              },
              {
                title: "Nhận PO",
                key: "r",
                render: (_, o) => (
                  <Space orientation="vertical" size={0}>
                    <span>{formatDateTime(o.received_at)}</span>
                    <span>{formatAge(o.received_at, now)} trước</span>
                  </Space>
                ),
              },
              {
                title: "Bạn kiểm chéo được không",
                key: "why",
                render: (_, o) => can(orderWhy(o)),
              },
            ]}
          />
        )}
      </Card>
      <Card size="small" title={`Báo giá chờ duyệt (${approvals.length})`}>
        {quotes.error ? (
          <LoadError error={quotes.error} onRetry={quotes.reload} />
        ) : (
          <Table<Quote>
            rowKey="case_id"
            size="small"
            loading={quotes.loading || work.loading}
            dataSource={approvals}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: quotes.loading
                ? " "
                : "Không có báo giá nào chờ duyệt.",
            }}
            columns={[
              {
                title: "Số RFQ",
                key: "rfq",
                render: (_, q) => (
                  <Link href={`/sales/quotes/${q.case_id}`}>{q.rfq_no}</Link>
                ),
              },
              { title: "Khách", dataIndex: "customer_code" },
              {
                title: "Trạng thái",
                key: "s",
                render: (_, q) => <QuoteStateTag status={q.status} />,
              },
              {
                title: "Phụ trách",
                key: "a",
                render: (_, q) =>
                  q.assigned_to ? name(q.assigned_to) : "Chưa giao",
              },
              {
                title: "Bạn duyệt được không",
                key: "why",
                render: (_, q) => can(quoteWhy(q)),
              },
            ]}
          />
        )}
      </Card>
    </div>
  );
}
