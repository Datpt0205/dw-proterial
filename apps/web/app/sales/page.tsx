"use client";

import { useCallback, useMemo } from "react";
import Link from "next/link";
import { Alert, Card, Empty, Space, Table, Tag, Typography } from "antd";
import {
  ClockCircleOutlined,
  ExclamationCircleOutlined,
} from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { RegionState } from "../../components/region-state";
import { useAuth } from "../../lib/auth/auth-context";
import {
  dayDeadline,
  daysSince,
  formatAge,
  formatDate,
  formatDateTime,
  formatInstant,
  TIME_ZONE_LABEL,
  UNKNOWN_TIME,
} from "../../lib/dates";
import { useNow } from "../../lib/use-now";
import { salesApi } from "./_lib/api";
import { ACTION, label, ROUTING_REASON } from "./_lib/labels";
import { useResource } from "./_lib/use-resource";
import { SCOPE } from "./_components/sales-frame";
import { ScopeGate } from "./_components/scope-gate";
import {
  MessageDispositionTag,
  OrderStateTag,
  QuoteStateTag,
} from "./_components/tags";

type WorkItem = SalesSchemas["WorkItem"];

/**
 * Việc cần làm (G22): what is mine to do next, in the order the API sorts it
 * (due date first, then the oldest), with how long each has waited and the
 * deadline in giờ Việt Nam. The list is the API's `my-work`, which already
 * leaves out a cross-check the caller made part of and an approval of a quote
 * they priced; the screen never re-sorts or re-filters it.
 */
export default function MyWorkPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <MyWork />
    </ScopeGate>
  );
}

function MyWork() {
  const now = useNow();
  const { hasScope } = useAuth();
  const work = useResource(
    "sales/my-work",
    useCallback(() => salesApi().myWork(), []),
  );
  const orders = useResource(
    "sales/orders",
    useCallback(() => salesApi().orders(), []),
  );
  const quotes = useResource(
    "sales/quotes",
    useCallback(() => salesApi().quotes(), []),
  );
  const inbox = useResource(
    "sales/inbox",
    useCallback(() => salesApi().inbox(), []),
    {
      enabled: hasScope(SCOPE.inbox),
    },
  );
  const ycbg = useResource(
    "sales/open-ycbg",
    useCallback(() => salesApi().openYcbg(), []),
  );

  const orderById = useMemo(
    () => new Map((orders.data ?? []).map((o) => [o.case_id, o])),
    [orders.data],
  );
  const quoteById = useMemo(
    () => new Map((quotes.data ?? []).map((q) => [q.case_id, q])),
    [quotes.data],
  );
  const messageById = useMemo(
    () => new Map((inbox.data ?? []).map((m) => [m.message_id, m])),
    [inbox.data],
  );

  const href = (item: WorkItem) =>
    item.kind === "order"
      ? `/sales/orders/${item.id}`
      : item.kind === "quote"
        ? `/sales/quotes/${item.id}`
        : `/sales/inbox?message=${encodeURIComponent(item.id)}`;

  const title = (item: WorkItem) => {
    if (item.kind === "order") {
      const o = orderById.get(item.id);
      return o
        ? `PO ${o.po_no}${o.revision ? ` · Rev.${o.revision}` : ""}`
        : "Đơn hàng";
    }
    if (item.kind === "quote") {
      const q = quoteById.get(item.id);
      return q ? `RFQ ${q.rfq_no}` : "Báo giá";
    }
    return messageById.get(item.id)?.subject ?? `Thư ${item.id}`;
  };

  const actionText = (item: WorkItem) => {
    if (item.kind === "message") {
      const reason = item.action.replace(/^handle_/, "");
      return `Xử lý thư: ${label(ROUTING_REASON, reason)}`;
    }
    return label(ACTION, item.action);
  };

  const openFlags = (item: WorkItem) =>
    item.kind === "order"
      ? orderById.get(item.id)?.open_findings
      : item.kind === "quote"
        ? quoteById.get(item.id)?.open_findings
        : undefined;

  const items = work.data ?? [];
  const overdue = items.filter((i) => dayDeadline(i.due, now)?.overdue).length;

  const waiting = useMemo(
    () =>
      [...(ycbg.data?.items ?? [])].sort((a, b) =>
        a.issued_on < b.issued_on ? -1 : a.issued_on > b.issued_on ? 1 : 0,
      ),
    [ycbg.data],
  );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Việc cần làm"
        description={`Việc đang chờ bạn, theo hạn rồi theo thời gian chờ (cũ nhất trước). Mọi giờ là ${TIME_ZONE_LABEL}.`}
      />
      {work.error ? (
        <RegionState error={work.error} onRetry={work.reload} />
      ) : (
        <>
          {items.length > 0 ? (
            <Alert
              type={overdue ? "error" : "info"}
              showIcon
              role="status"
              title={`${items.length} việc đang chờ bạn${overdue ? `, ${overdue} việc đã quá hạn` : ""}.`}
            />
          ) : null}
          <Table<WorkItem>
            rowKey={(i) => `${i.kind}:${i.id}:${i.action}`}
            loading={work.loading}
            dataSource={items}
            pagination={false}
            sticky
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: work.loading ? (
                " "
              ) : (
                <Empty description="Không có việc nào đang chờ bạn. Thư mới vào Hộp thư; DW1 xử lý rồi giao việc tại đây." />
              ),
            }}
            footer={() =>
              `${items.length} việc · cập nhật lúc ${formatInstant(now)}`
            }
            columns={[
              {
                title: "Việc",
                key: "action",
                render: (_, item) => (
                  <Space orientation="vertical" size={0}>
                    <Link href={href(item)}>{actionText(item)}</Link>
                    <Typography.Text>{title(item)}</Typography.Text>
                  </Space>
                ),
              },
              {
                title: "Khách",
                dataIndex: "customer_code",
                render: (code: string | null) => code ?? UNKNOWN_TIME,
              },
              {
                title: "Trạng thái",
                key: "status",
                render: (_, item) =>
                  item.kind === "order" ? (
                    <OrderStateTag status={item.status} />
                  ) : item.kind === "quote" ? (
                    <QuoteStateTag status={item.status} />
                  ) : (
                    <MessageDispositionTag kind={item.status} />
                  ),
              },
              {
                title: "Cờ chưa quyết định",
                key: "flags",
                align: "right",
                render: (_, item) => {
                  const n = openFlags(item);
                  return n === undefined ? "" : n;
                },
              },
              {
                title: `Đã chờ (${TIME_ZONE_LABEL})`,
                key: "age",
                render: (_, item) => (
                  <Space orientation="vertical" size={0}>
                    <span>{formatAge(item.received_at, now)}</span>
                    <Typography.Text>
                      từ{" "}
                      {formatDateTime(item.received_at, { zoneLabel: false })}
                    </Typography.Text>
                  </Space>
                ),
              },
              {
                title: `Hạn (${TIME_ZONE_LABEL})`,
                key: "due",
                render: (_, item) => <DueCell item={item} now={now} />,
              },
            ]}
          />
        </>
      )}

      <Card title="YCBG chờ Design" size="small">
        {ycbg.error ? (
          <RegionState error={ycbg.error} onRetry={ycbg.reload} />
        ) : (
          <Table
            rowKey="ycbg_no"
            size="small"
            loading={ycbg.loading}
            dataSource={waiting}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: ycbg.loading
                ? " "
                : "Không có YCBG nào đang chờ Design.",
            }}
            footer={() =>
              ycbg.data
                ? `${waiting.length} YCBG, chờ lâu nhất trước · danh sách xuất từ Bravo (giả lập) ngày ${formatDate(ycbg.data.as_of)}`
                : ""
            }
            columns={[
              { title: "Số YCBG", dataIndex: "ycbg_no" },
              { title: "Số RFQ", dataIndex: "rfq_no" },
              { title: "Khách", dataIndex: "customer_code" },
              {
                title: "Ngày lập",
                dataIndex: "issued_on",
                render: (d: string) => formatDate(d),
              },
              {
                title: "Đã chờ",
                key: "days",
                render: (_, row) => {
                  const days = daysSince(row.issued_on, now);
                  return days === null ? UNKNOWN_TIME : `${days} ngày`;
                },
              },
            ]}
          />
        )}
      </Card>
    </div>
  );
}

function DueCell({ item, now }: { item: WorkItem; now: number }) {
  if (item.kind === "message") return <span>Không đặt hạn</span>;
  if (!item.due)
    return item.kind === "quote" ? (
      <Tag color="purple" icon={<ExclamationCircleOutlined aria-hidden />}>
        Chưa rõ hạn báo giá
      </Tag>
    ) : (
      <span>Không đặt hạn</span>
    );
  const deadline = dayDeadline(item.due, now);
  if (!deadline) return <span>{UNKNOWN_TIME}</span>;
  return (
    <Space orientation="vertical" size={0}>
      <span>{deadline.absolute}</span>
      {deadline.overdue ? (
        <Tag color="error" icon={<ClockCircleOutlined aria-hidden />}>
          Quá hạn · {deadline.relative}
        </Tag>
      ) : (
        <Typography.Text>{deadline.relative}</Typography.Text>
      )}
    </Space>
  );
}
