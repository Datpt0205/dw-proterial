"use client";

import { Suspense, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Button,
  Card,
  Empty,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  ClockCircleOutlined,
  ExclamationCircleOutlined,
} from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { RegionState } from "../../../components/region-state";
import {
  dayDeadline,
  formatAge,
  formatDateTime,
  TIME_ZONE_LABEL,
} from "../../../lib/dates";
import { useNow } from "../../../lib/use-now";
import { salesApi } from "../_lib/api";
import { label, QUOTE_STATE } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useResource } from "../_lib/use-resource";
import { useStatusFilter } from "../_lib/use-status-filter";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";
import { QuoteStateTag } from "../_components/tags";

type Quote = SalesSchemas["QuoteSummaryView"];

const DONE = ["sent", "master_list_recorded", "declined"];

/**
 * Báo giá: the requests by due date, the overdue ones as their own group on
 * top (`overdue` is the API's, from the quote due date), time left in giờ Việt
 * Nam. The API returns them unsorted; the order here is by due date, then the
 * oldest request, and a request whose due date was not read sorts last as
 * "Chưa rõ hạn", never as no deadline.
 */
export default function QuotesPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <Quotes />
      </Suspense>
    </ScopeGate>
  );
}

function byDue(a: Quote, b: Quote): number {
  if (a.quote_due !== b.quote_due) {
    if (a.quote_due === null) return 1;
    if (b.quote_due === null) return -1;
    return a.quote_due < b.quote_due ? -1 : 1;
  }
  return a.received_at < b.received_at
    ? -1
    : a.received_at > b.received_at
      ? 1
      : 0;
}

function Quotes() {
  const now = useNow();
  const name = usePeople();
  const quotes = useResource(
    "sales/quotes",
    useCallback(() => salesApi().quotes(), []),
  );
  const [status, setStatus] = useStatusFilter();
  const all = useMemo(() => quotes.data ?? [], [quotes.data]);
  const shown = useMemo(
    () =>
      [
        ...(status.length ? all.filter((q) => status.includes(q.status)) : all),
      ].sort(byDue),
    [all, status],
  );
  const overdue = shown.filter((q) => q.overdue && !DONE.includes(q.status));
  const open = shown.filter((q) => !q.overdue && !DONE.includes(q.status));
  const done = shown.filter((q) => DONE.includes(q.status));

  const table = (rows: Quote[], empty: string) => (
    <Table<Quote>
      rowKey="case_id"
      loading={quotes.loading}
      dataSource={rows}
      pagination={false}
      sticky
      size="small"
      scroll={{ x: "max-content" }}
      locale={{ emptyText: quotes.loading ? " " : empty }}
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
          key: "status",
          render: (_, q) => <QuoteStateTag status={q.status} />,
        },
        {
          title: `Hạn báo giá (${TIME_ZONE_LABEL})`,
          key: "due",
          render: (_, q) => {
            if (!q.quote_due)
              return (
                <Tag
                  color="purple"
                  icon={<ExclamationCircleOutlined aria-hidden />}
                >
                  Chưa rõ hạn
                </Tag>
              );
            const deadline = dayDeadline(q.quote_due, now);
            return (
              <Space orientation="vertical" size={0}>
                <span>{deadline?.absolute}</span>
                {DONE.includes(q.status) ? null : q.overdue ? (
                  <Tag color="error" icon={<ClockCircleOutlined aria-hidden />}>
                    Quá hạn · {deadline?.relative}
                  </Tag>
                ) : (
                  <Typography.Text>{deadline?.relative}</Typography.Text>
                )}
              </Space>
            );
          },
        },
        {
          title: "YCBG",
          dataIndex: "ycbg_no",
          render: (no: string | null) => no ?? "Chưa lập",
        },
        {
          title: "Cờ chưa quyết định",
          dataIndex: "open_findings",
          align: "right",
        },
        {
          title: `Nhận lúc (${TIME_ZONE_LABEL})`,
          key: "received",
          render: (_, q) => (
            <Space orientation="vertical" size={0}>
              <span>{formatDateTime(q.received_at, { zoneLabel: false })}</span>
              <Typography.Text>
                {formatAge(q.received_at, now)} trước
              </Typography.Text>
            </Space>
          ),
        },
        {
          title: "Phụ trách",
          key: "assigned",
          render: (_, q) =>
            q.assigned_to
              ? name(q.assigned_to)
              : "Chưa giao, mọi PIC nhận được",
        },
      ]}
    />
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Báo giá"
        description="Yêu cầu báo giá theo hạn: quá hạn trước, rồi hạn gần nhất. Hạn là hết ngày ghi trên yêu cầu, giờ Việt Nam."
        extra={<Link href="/sales/quotes/screening">Rà soát báo giá năm</Link>}
      />
      <Space wrap>
        <Select
          mode="multiple"
          allowClear
          className="min-w-64"
          placeholder="Lọc theo trạng thái"
          aria-label="Lọc theo trạng thái"
          value={status}
          onChange={setStatus}
          options={Object.entries(QUOTE_STATE).map(([value, text]) => ({
            value,
            label: text,
          }))}
        />
        {status.length ? (
          <Button onClick={() => setStatus([])}>Xóa bộ lọc</Button>
        ) : null}
      </Space>
      {quotes.error ? (
        <RegionState error={quotes.error} onRetry={quotes.reload} />
      ) : !quotes.loading && all.length === 0 ? (
        <Empty description="Chưa có yêu cầu báo giá. Hồ sơ được tạo khi DW1 xử lý thư có RFQ trong Hộp thư.">
          <Link href="/sales/inbox">Mở Hộp thư</Link>
        </Empty>
      ) : (
        <>
          {status.length && shown.length === 0 ? (
            <Empty
              description={`Không có báo giá ở trạng thái ${status.map((s) => label(QUOTE_STATE, s)).join(", ")}.`}
            >
              <Button onClick={() => setStatus([])}>Xóa bộ lọc</Button>
            </Empty>
          ) : null}
          <Card size="small" title={`Quá hạn (${overdue.length})`}>
            {table(overdue, "Không có báo giá quá hạn.")}
          </Card>
          <Card size="small" title={`Đang làm (${open.length})`}>
            {table(open, "Không có báo giá đang làm.")}
          </Card>
          <Card size="small" title={`Đã gửi hoặc từ chối (${done.length})`}>
            {table(done, "Chưa có báo giá nào xong.")}
          </Card>
        </>
      )}
    </div>
  );
}
