"use client";

import { Suspense, useCallback, useMemo } from "react";
import Link from "next/link";
import { CloseOutlined, ExclamationCircleOutlined } from "@ant-design/icons";
import { Button, Empty, Select, Space, Table, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import {
  dayDeadline,
  formatAge,
  formatDateTime,
  instantMs,
  TIME_ZONE_LABEL,
} from "../../../lib/dates";
import { compareVi, matches } from "../../../lib/search";
import { useNow } from "../../../lib/use-now";
import { salesApi } from "../_lib/api";
import { useCustomerName } from "../_lib/customers";
import { label, QUOTE_STATE } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useResource } from "../_lib/use-resource";
import { useListView, useStatusFilter } from "../_lib/use-status-filter";
import { salesCrumbs } from "../_components/crumbs";
import {
  Assignee,
  DueText,
  ListToolbar,
  listFooter,
  PriorityPanel,
  RowTitle,
  type PriorityItem,
} from "../_components/list-parts";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";
import { QuoteStateTag } from "../_components/tags";

type Quote = SalesSchemas["QuoteSummaryView"];

const DONE = ["sent", "master_list_recorded", "declined"];
const TABS = ["open", "done", "all"] as const;
const SORTS = ["due", "newest", "customer"] as const;

/**
 * Báo giá: the requests by due date, the overdue ones first (`overdue` is the
 * API's, from the quote due date), time left in giờ Việt Nam. The API returns
 * them unsorted; the default order here is by due date, then the oldest
 * request, and a request whose due date was not read sorts last as "Chưa rõ
 * hạn", never as no deadline.
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
  // Overdue and still open first: their own group on top.
  const late = (q: Quote) => (q.overdue && !DONE.includes(q.status) ? 0 : 1);
  if (late(a) !== late(b)) return late(a) - late(b);
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
  const customerName = useCustomerName();
  const view = useListView(TABS, "open", SORTS, "due");
  const quotes = useResource(
    "sales/quotes",
    useCallback(() => salesApi().quotes(), []),
  );
  const [status, setStatus] = useStatusFilter();
  const all = useMemo(() => quotes.data ?? [], [quotes.data]);
  const open = all.filter((q) => !DONE.includes(q.status));
  const done = all.filter((q) => DONE.includes(q.status));
  const overdue = open.filter((q) => q.overdue);
  const unknownDue = open.filter((q) => !q.quote_due);
  const pending = open.filter((q) => q.status === "pending_approval");

  const shown = (() => {
    const rows = (view.tab === "open" ? open : view.tab === "done" ? done : all)
      .filter((q) => !status.length || status.includes(q.status))
      .filter((q) =>
        matches(view.query, [
          q.rfq_no,
          q.ycbg_no,
          q.customer_code,
          customerName(q.customer_code),
          q.assigned_to ? name(q.assigned_to) : null,
        ]),
      );
    if (view.sort === "newest")
      return [...rows].sort(
        (a, b) =>
          (instantMs(b.received_at) ?? 0) - (instantMs(a.received_at) ?? 0),
      );
    if (view.sort === "customer")
      return [...rows].sort((a, b) =>
        compareVi(
          customerName(a.customer_code) || a.customer_code,
          customerName(b.customer_code) || b.customer_code,
        ),
      );
    return [...rows].sort(byDue);
  })();
  const clear = () => {
    setStatus([]);
    view.setQuery("");
  };

  const priority: PriorityItem[] = [];
  const firstLate = [...overdue].sort(byDue)[0];
  if (firstLate) {
    const d = dayDeadline(firstLate.quote_due, now);
    priority.push({
      key: "overdue",
      tone: "err",
      lead: `${overdue.length} báo giá quá hạn`,
      text: `RFQ ${firstLate.rfq_no} · ${label(QUOTE_STATE, firstLate.status)}`,
      sub: d ? `${d.withZone} · ${d.relative}` : undefined,
      href: `/sales/quotes/${firstLate.case_id}`,
    });
  }
  if (unknownDue.length)
    priority.push({
      key: "unknown",
      tone: "unk",
      lead: `${unknownDue.length} báo giá chưa rõ hạn`,
      text: "DW1 không đọc được hạn trên yêu cầu; hỏi khách hoặc xem bản gốc.",
      href: `/sales/quotes/${unknownDue[0]!.case_id}`,
    });
  if (pending.length)
    priority.push({
      key: "pending",
      tone: "pri",
      lead: `${pending.length} báo giá chờ duyệt`,
      text: pending
        .slice(0, 3)
        .map((q) => q.rfq_no)
        .join(", "),
      href: "/sales/review",
    });

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Báo giá")}
        title="Báo giá"
        subtitle={
          quotes.data
            ? `${open.length} yêu cầu đang làm · ${overdue.length} quá hạn · ${done.length} đã gửi hoặc từ chối. Hạn là hết ngày ghi trên yêu cầu, giờ Việt Nam.`
            : "Yêu cầu báo giá theo hạn: quá hạn trước, rồi hạn gần nhất. Hạn là hết ngày ghi trên yêu cầu, giờ Việt Nam."
        }
        actions={
          <Link href="/sales/quotes/screening">Rà soát báo giá năm</Link>
        }
      />
      {quotes.error ? (
        <LoadError error={quotes.error} onRetry={quotes.reload} />
      ) : !quotes.loading && all.length === 0 ? (
        <Empty description="Chưa có yêu cầu báo giá. Hồ sơ được tạo khi DW1 xử lý thư có RFQ trong Hộp thư.">
          <Link href="/sales/inbox">Mở Hộp thư</Link>
        </Empty>
      ) : (
        <>
          {quotes.data ? (
            <PriorityPanel
              items={priority}
              calm="Không có báo giá quá hạn, chưa rõ hạn hay chờ duyệt."
            />
          ) : null}
          <ListToolbar
            tabs={[
              { value: "open", label: "Đang làm", count: open.length },
              {
                value: "done",
                label: "Đã gửi hoặc từ chối",
                count: done.length,
              },
              { value: "all", label: "Tất cả", count: all.length },
            ]}
            tab={view.tab}
            onTab={view.setTab}
            query={view.query}
            onQuery={view.setQuery}
            placeholder="Số RFQ, số YCBG, khách hàng"
            filter={
              <Select
                mode="multiple"
                allowClear
                maxTagCount="responsive"
                className="w-full sm:w-64"
                placeholder="Mọi trạng thái"
                aria-label="Lọc theo trạng thái"
                value={status}
                onChange={setStatus}
                options={Object.entries(QUOTE_STATE).map(([value, text]) => ({
                  value,
                  label: text,
                }))}
              />
            }
            sorts={[
              { value: "due", label: "Theo hạn báo giá" },
              { value: "newest", label: "Mới nhận" },
              { value: "customer", label: "Khách hàng (A–Z)" },
            ]}
            sort={view.sort}
            onSort={view.setSort}
          />
          {status.length ? (
            <Space wrap>
              {status.map((s) => (
                <Button
                  key={s}
                  size="small"
                  icon={<CloseOutlined aria-hidden />}
                  iconPlacement="end"
                  aria-label={`Bỏ lọc trạng thái ${label(QUOTE_STATE, s)}`}
                  onClick={() => setStatus(status.filter((x) => x !== s))}
                >
                  {label(QUOTE_STATE, s)}
                </Button>
              ))}
              <Button size="small" type="link" onClick={() => setStatus([])}>
                Xóa tất cả
              </Button>
            </Space>
          ) : null}
          <Table<Quote>
            rowKey="case_id"
            loading={quotes.loading}
            dataSource={shown}
            pagination={false}
            sticky
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: quotes.loading ? (
                " "
              ) : (
                <Empty
                  description={
                    status.length
                      ? `Không có báo giá ở trạng thái ${status.map((s) => label(QUOTE_STATE, s)).join(", ")} trong nhóm này.`
                      : "Không có báo giá nào khớp bộ lọc."
                  }
                >
                  <Button onClick={clear}>Xóa bộ lọc</Button>
                </Empty>
              ),
            }}
            footer={() =>
              listFooter(
                shown.length,
                (view.tab === "open" ? open : view.tab === "done" ? done : all)
                  .length,
                all.length,
                "báo giá",
                view.query !== "" || status.length > 0,
              )
            }
            columns={[
              {
                title: "Yêu cầu báo giá",
                key: "rfq",
                render: (_, q) => (
                  <RowTitle
                    href={`/sales/quotes/${q.case_id}`}
                    title={
                      customerName(q.customer_code) ||
                      `Khách ${q.customer_code}`
                    }
                    code={`RFQ ${q.rfq_no}`}
                    sub={q.ycbg_no ? `YCBG ${q.ycbg_no}` : "YCBG chưa lập"}
                  />
                ),
              },
              {
                title: "Trạng thái",
                key: "status",
                render: (_, q) => <QuoteStateTag status={q.status} />,
              },
              {
                title: "Cờ chưa quyết định",
                key: "flags",
                render: (_, q) =>
                  q.open_findings ? (
                    <StatusTag
                      tone="warn"
                      icon={<ExclamationCircleOutlined aria-hidden />}
                    >
                      {q.open_findings} cờ
                    </StatusTag>
                  ) : (
                    <Typography.Text type="secondary">
                      Không còn cờ
                    </Typography.Text>
                  ),
              },
              {
                title: `Hạn báo giá (${TIME_ZONE_LABEL})`,
                key: "due",
                align: "right",
                render: (_, q) =>
                  !q.quote_due ? (
                    <StatusTag
                      tone="unk"
                      icon={<ExclamationCircleOutlined aria-hidden />}
                    >
                      Chưa rõ hạn
                    </StatusTag>
                  ) : (
                    <DueText
                      day={q.quote_due}
                      now={now}
                      done={DONE.includes(q.status)}
                    />
                  ),
              },
              {
                title: `Nhận lúc (${TIME_ZONE_LABEL})`,
                key: "received",
                align: "right",
                render: (_, q) => (
                  <span className="flex flex-col items-end">
                    <span>{formatAge(q.received_at, now)} trước</span>
                    <Typography.Text type="secondary">
                      {formatDateTime(q.received_at, { zoneLabel: false })}
                    </Typography.Text>
                  </span>
                ),
              },
              {
                title: "Phụ trách",
                key: "assigned",
                align: "center",
                render: (_, q) => (
                  <Assignee
                    name={q.assigned_to ? name(q.assigned_to) : null}
                    none="Chưa giao, mọi PIC nhận được"
                  />
                ),
              },
            ]}
          />
        </>
      )}
    </div>
  );
}
