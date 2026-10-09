"use client";

import { Suspense, useCallback, useMemo } from "react";
import { Button, Card, Empty, Table, Typography } from "antd";
import { ExclamationCircleOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../components/load-error";
import { useAuth } from "../../lib/auth/auth-context";
import {
  dayDeadline,
  daysSince,
  formatAge,
  formatDate,
  formatDateTime,
  formatInstant,
  instantMs,
  TIME_ZONE_LABEL,
  UNKNOWN_TIME,
} from "../../lib/dates";
import { compareVi, matches } from "../../lib/search";
import { useNow } from "../../lib/use-now";
import { salesApi } from "./_lib/api";
import { useCustomerName } from "./_lib/customers";
import { ACTION, label, ROUTING_REASON } from "./_lib/labels";
import { usePeople } from "./_lib/people";
import { useResource } from "./_lib/use-resource";
import { useListView } from "./_lib/use-status-filter";
import { salesCrumbs } from "./_components/crumbs";
import {
  Assignee,
  DueText,
  ListToolbar,
  listFooter,
  PriorityPanel,
  RowTitle,
  type PriorityItem,
} from "./_components/list-parts";
import { SCOPE } from "./_components/sales-frame";
import { ScopeGate } from "./_components/scope-gate";
import {
  MessageDispositionTag,
  OrderStateTag,
  QuoteStateTag,
} from "./_components/tags";

type WorkItem = SalesSchemas["WorkItem"];

const TABS = ["all", "order", "quote", "message"] as const;
const SORTS = ["api", "age", "customer"] as const;
const SOON_MS = 48 * 3_600_000;

/**
 * Việc cần làm (G22): what is mine to do next, in the order the API sorts it
 * (due date first, then the oldest), with how long each has waited and the
 * deadline in giờ Việt Nam. The list is the API's `my-work`, which already
 * leaves out a cross-check the caller made part of and an approval of a quote
 * they priced; the screen never re-filters it, and re-sorts it only when the
 * person picks another order.
 */
export default function MyWorkPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <MyWork />
      </Suspense>
    </ScopeGate>
  );
}

function MyWork() {
  const now = useNow();
  const { hasScope } = useAuth();
  const person = usePeople();
  const customerName = useCustomerName();
  const view = useListView(TABS, "all", SORTS, "api");
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

  /** The record's own identifier, in monospace on the row's second line. */
  const code = (item: WorkItem) => {
    if (item.kind === "order") {
      const o = orderById.get(item.id);
      return o
        ? `PO ${o.po_no}${o.revision ? ` · Rev.${o.revision}` : ""}`
        : null;
    }
    if (item.kind === "quote") {
      const q = quoteById.get(item.id);
      return q ? `RFQ ${q.rfq_no}` : null;
    }
    return item.id;
  };

  const title = (item: WorkItem) =>
    code(item) ??
    (item.kind === "order"
      ? "Đơn hàng"
      : item.kind === "quote"
        ? "Báo giá"
        : `Thư ${item.id}`);

  const actionText = (item: WorkItem) => {
    if (item.kind === "message") {
      const reason = item.action.replace(/^handle_/, "");
      return `Xử lý thư: ${label(ROUTING_REASON, reason)}`;
    }
    return label(ACTION, item.action);
  };

  const subject = (item: WorkItem) =>
    item.kind === "message" ? messageById.get(item.id)?.subject : undefined;

  const openFlags = (item: WorkItem) =>
    item.kind === "order"
      ? orderById.get(item.id)?.open_findings
      : item.kind === "quote"
        ? quoteById.get(item.id)?.open_findings
        : undefined;

  const items = useMemo(() => work.data ?? [], [work.data]);
  const overdue = items.filter((i) => dayDeadline(i.due, now)?.overdue);
  const soon = items.filter((i) => {
    const d = dayDeadline(i.due, now);
    return d && !d.overdue && d.leftMs < SOON_MS;
  });
  const unknownDue = items.filter((i) => i.kind === "quote" && !i.due);

  const waiting = useMemo(
    () =>
      [...(ycbg.data?.items ?? [])].sort((a, b) =>
        a.issued_on < b.issued_on ? -1 : a.issued_on > b.issued_on ? 1 : 0,
      ),
    [ycbg.data],
  );

  const inTab = (tab: (typeof TABS)[number]) =>
    tab === "all" ? items : items.filter((i) => i.kind === tab);
  const shown = (() => {
    const rows = (
      view.tab === "all" ? items : items.filter((i) => i.kind === view.tab)
    ).filter((i) =>
      matches(view.query, [
        actionText(i),
        title(i),
        subject(i),
        i.customer_code,
        customerName(i.customer_code),
      ]),
    );
    if (view.sort === "age")
      return [...rows].sort(
        (a, b) =>
          (instantMs(a.received_at) ?? 0) - (instantMs(b.received_at) ?? 0),
      );
    if (view.sort === "customer")
      return [...rows].sort((a, b) =>
        compareVi(
          customerName(a.customer_code) || a.customer_code,
          customerName(b.customer_code) || b.customer_code,
        ),
      );
    return rows;
  })();
  const filtered = view.tab !== "all" || view.query !== "";

  const priority: PriorityItem[] = [];
  if (overdue[0]) {
    const d = dayDeadline(overdue[0].due, now)!;
    priority.push({
      key: "overdue",
      tone: "err",
      lead: `Quá hạn · ${title(overdue[0])}`,
      text: actionText(overdue[0]),
      sub: `${d.withZone} · ${d.relative}${overdue.length > 1 ? ` · và ${overdue.length - 1} việc quá hạn khác` : ""}`,
      href: href(overdue[0]),
    });
  }
  if (soon[0]) {
    const d = dayDeadline(soon[0].due, now)!;
    priority.push({
      key: "soon",
      tone: "warn",
      lead: `Sắp đến hạn · ${title(soon[0])}`,
      text: actionText(soon[0]),
      sub: `${d.withZone} · ${d.relative}`,
      href: href(soon[0]),
    });
  }
  if (unknownDue.length)
    priority.push({
      key: "unknown",
      tone: "unk",
      lead: `${unknownDue.length} báo giá chưa rõ hạn`,
      text: "DW1 không đọc được hạn báo giá trên yêu cầu; hạn chưa rõ, không phải không có hạn.",
      href: "/sales?tab=quote",
    });
  if (waiting.length) {
    const days = daysSince(waiting[0]!.issued_on, now);
    priority.push({
      key: "ycbg",
      tone: "pri",
      lead: `${waiting.length} YCBG chờ Design`,
      text: days === null ? undefined : `lâu nhất ${days} ngày`,
      href: "#ycbg-cho-design",
    });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Việc cần làm")}
        title="Việc cần làm"
        subtitle={
          <span role="status">
            {work.data
              ? `${items.length} việc đang chờ bạn${overdue.length ? `, ${overdue.length} việc đã quá hạn` : ""}. `
              : ""}
            Theo hạn rồi theo thời gian chờ (cũ nhất trước). Mọi giờ là{" "}
            {TIME_ZONE_LABEL}.
          </span>
        }
      />
      {work.error ? (
        <LoadError error={work.error} onRetry={work.reload} />
      ) : (
        <>
          {work.data ? (
            <PriorityPanel
              items={priority}
              calm="Không có việc quá hạn hay sắp đến hạn."
            />
          ) : null}
          <ListToolbar
            tabs={[
              { value: "all", label: "Tất cả", count: inTab("all").length },
              {
                value: "order",
                label: "Đơn hàng",
                count: inTab("order").length,
              },
              {
                value: "quote",
                label: "Báo giá",
                count: inTab("quote").length,
              },
              {
                value: "message",
                label: "Thư",
                count: inTab("message").length,
              },
            ]}
            tab={view.tab}
            onTab={view.setTab}
            query={view.query}
            onQuery={view.setQuery}
            placeholder="Số PO, số RFQ, khách hàng"
            sorts={[
              { value: "api", label: "Theo hạn" },
              { value: "age", label: "Chờ lâu nhất" },
              { value: "customer", label: "Khách hàng (A–Z)" },
            ]}
            sort={view.sort}
            onSort={view.setSort}
          />
          <Table<WorkItem>
            rowKey={(i) => `${i.kind}:${i.id}:${i.action}`}
            loading={work.loading}
            dataSource={shown}
            pagination={false}
            sticky
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: work.loading ? (
                " "
              ) : filtered && items.length ? (
                <Empty description="Không có việc nào khớp bộ lọc.">
                  <Button
                    onClick={() => {
                      view.setQuery("");
                      view.setTab("all");
                    }}
                  >
                    Xóa bộ lọc
                  </Button>
                </Empty>
              ) : (
                <Empty description="Không có việc nào đang chờ bạn. Thư mới vào Hộp thư; DW1 xử lý rồi giao việc tại đây." />
              ),
            }}
            footer={() =>
              `${listFooter(shown.length, inTab(view.tab).length, items.length, "việc", view.query !== "")} · cập nhật lúc ${formatInstant(now)}`
            }
            columns={[
              {
                title: "Việc",
                key: "action",
                render: (_, item) => (
                  <RowTitle
                    href={href(item)}
                    title={actionText(item)}
                    code={code(item)}
                    sub={
                      subject(item) ??
                      ([item.customer_code, customerName(item.customer_code)]
                        .filter(Boolean)
                        .join(" · ") ||
                        UNKNOWN_TIME)
                    }
                  />
                ),
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
                  <span className="flex flex-col">
                    <span>{formatAge(item.received_at, now)}</span>
                    <Typography.Text type="secondary">
                      từ{" "}
                      {formatDateTime(item.received_at, { zoneLabel: false })}
                    </Typography.Text>
                  </span>
                ),
              },
              {
                title: `Hạn (${TIME_ZONE_LABEL})`,
                key: "due",
                align: "right",
                render: (_, item) => <DueCell item={item} now={now} />,
              },
              {
                title: "Phụ trách",
                key: "assigned",
                align: "center",
                render: (_, item) => (
                  <Assignee
                    name={item.assigned_to ? person(item.assigned_to) : null}
                  />
                ),
              },
            ]}
          />
        </>
      )}

      <Card title="YCBG chờ Design" size="small" id="ycbg-cho-design">
        {ycbg.error ? (
          <LoadError error={ycbg.error} onRetry={ycbg.reload} />
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
              {
                title: "Khách",
                dataIndex: "customer_code",
                render: (c: string) =>
                  [c, customerName(c)].filter(Boolean).join(" · "),
              },
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
      <StatusTag tone="unk" icon={<ExclamationCircleOutlined aria-hidden />}>
        Chưa rõ hạn báo giá
      </StatusTag>
    ) : (
      <span>Không đặt hạn</span>
    );
  return <DueText day={item.due} now={now} />;
}
