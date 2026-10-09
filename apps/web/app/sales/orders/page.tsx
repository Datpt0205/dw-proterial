"use client";

import { Suspense, useCallback, useMemo } from "react";
import Link from "next/link";
import { CloseOutlined, StopOutlined } from "@ant-design/icons";
import { Button, Empty, Select, Space, Table, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import {
  formatAge,
  formatDateTime,
  instantMs,
  TIME_ZONE_LABEL,
} from "../../../lib/dates";
import { compareVi, matches } from "../../../lib/search";
import { useNow } from "../../../lib/use-now";
import { salesApi } from "../_lib/api";
import { useCustomerName } from "../_lib/customers";
import { label, ORDER_STATE } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useResource } from "../_lib/use-resource";
import { useListView, useStatusFilter } from "../_lib/use-status-filter";
import { salesCrumbs } from "../_components/crumbs";
import {
  Assignee,
  ListToolbar,
  listFooter,
  PriorityPanel,
  RowTitle,
  type PriorityItem,
} from "../_components/list-parts";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";
import { OrderStateTag } from "../_components/tags";

type Order = SalesSchemas["OrderSummaryView"];

/** The tabs: states grouped by who the order waits on (CONTEXT.md states). */
const GROUP = {
  open: [
    "received",
    "checked",
    "in_review",
    "prepared",
    "uploaded_to_bravo",
    "cross_checked",
    "change_review",
  ],
  customer: ["correction_requested"],
  done: ["confirmed", "closed"],
} as const;
const TABS = ["open", "customer", "done", "all"] as const;
type Tab = (typeof TABS)[number];
const SORTS = ["newest", "oldest", "flags", "customer"] as const;

const inGroup = (tab: Tab, o: Order) =>
  tab === "all" || (GROUP[tab] as readonly string[]).includes(o.status);

/** Đơn hàng: every order case of the workspace, no amount on the list. */
export default function OrdersPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <Orders />
      </Suspense>
    </ScopeGate>
  );
}

function Orders() {
  const now = useNow();
  const name = usePeople();
  const customerName = useCustomerName();
  const view = useListView(TABS, "open", SORTS, "newest");
  const orders = useResource(
    "sales/orders",
    useCallback(() => salesApi().orders(), []),
  );
  const [status, setStatus] = useStatusFilter();
  const all = useMemo(() => orders.data ?? [], [orders.data]);

  const shown = (() => {
    const rows = all
      .filter((o) => inGroup(view.tab, o))
      .filter((o) => !status.length || status.includes(o.status))
      .filter((o) =>
        matches(view.query, [
          o.po_no,
          o.customer_code,
          customerName(o.customer_code),
          o.assigned_to ? name(o.assigned_to) : null,
        ]),
      );
    const at = (o: Order) => instantMs(o.received_at) ?? 0;
    if (view.sort === "oldest") return [...rows].sort((a, b) => at(a) - at(b));
    if (view.sort === "flags")
      return [...rows].sort(
        (a, b) =>
          b.open_blocking_findings - a.open_blocking_findings ||
          b.open_findings - a.open_findings,
      );
    if (view.sort === "customer")
      return [...rows].sort((a, b) =>
        compareVi(
          customerName(a.customer_code) || a.customer_code,
          customerName(b.customer_code) || b.customer_code,
        ),
      );
    return [...rows].sort((a, b) => at(b) - at(a));
  })();
  const filtered = view.tab !== "all" || view.query !== "" || status.length > 0;
  const clear = () => {
    setStatus([]);
    view.setQuery("");
  };

  const blocked = all.filter(
    (o) => o.open_blocking_findings > 0 && inGroup("open", o),
  );
  const waitingCustomer = all.filter((o) => inGroup("customer", o));
  const unassigned = all.filter((o) => !o.assigned_to && inGroup("open", o));
  const priority: PriorityItem[] = [];
  if (blocked[0])
    priority.push({
      key: "blocked",
      tone: "err",
      lead: `${blocked.length} đơn còn cờ chặn`,
      text: `PO ${blocked[0].po_no} · ${blocked[0].open_blocking_findings} chặn`,
      sub: `nhận ${formatDateTime(blocked[0].received_at)} · ${formatAge(blocked[0].received_at, now)} trước`,
      href: `/sales/orders/${blocked[0].case_id}`,
      extra: (
        <StatusTag tone="err" icon={<StopOutlined aria-hidden />}>
          {blocked.reduce((n, o) => n + o.open_blocking_findings, 0)} chặn
        </StatusTag>
      ),
    });
  if (waitingCustomer.length)
    priority.push({
      key: "customer",
      tone: "pri",
      lead: `${waitingCustomer.length} đơn chờ khách sửa PO`,
      text: waitingCustomer
        .slice(0, 3)
        .map((o) => o.po_no)
        .join(", "),
      href: "/sales/orders?tab=customer",
    });
  if (unassigned.length)
    priority.push({
      key: "unassigned",
      tone: "warn",
      lead: `${unassigned.length} đơn chưa giao`,
      text: "mọi PIC nhận được",
      href: "/sales/orders?sort=oldest",
    });

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Đơn hàng")}
        title="Đơn hàng"
        subtitle={
          orders.data
            ? `${all.filter((o) => inGroup("open", o)).length} đơn đang làm · ${waitingCustomer.length} chờ khách · ${blocked.length} còn cờ chặn. Mỗi số PO là một hồ sơ; bản sửa của khách vào cùng hồ sơ.`
            : "Mỗi số PO của khách là một hồ sơ, từ bản đầu tới khi xác nhận; bản sửa của khách vào cùng hồ sơ."
        }
      />
      {orders.error ? (
        <LoadError error={orders.error} onRetry={orders.reload} />
      ) : (
        <>
          {orders.data ? (
            <PriorityPanel
              items={priority}
              calm="Không có đơn nào còn cờ chặn, chờ khách hay chưa giao."
            />
          ) : null}
          <ListToolbar
            tabs={[
              {
                value: "open",
                label: "Đang làm",
                count: all.filter((o) => inGroup("open", o)).length,
              },
              {
                value: "customer",
                label: "Chờ khách",
                count: waitingCustomer.length,
              },
              {
                value: "done",
                label: "Đã xong",
                count: all.filter((o) => inGroup("done", o)).length,
              },
              { value: "all", label: "Tất cả", count: all.length },
            ]}
            tab={view.tab}
            onTab={view.setTab}
            query={view.query}
            onQuery={view.setQuery}
            placeholder="Số PO, khách hàng, người phụ trách"
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
                options={Object.entries(ORDER_STATE).map(([value, text]) => ({
                  value,
                  label: text,
                }))}
              />
            }
            sorts={[
              { value: "newest", label: "Mới nhận" },
              { value: "oldest", label: "Nhận lâu nhất" },
              { value: "flags", label: "Nhiều cờ chặn" },
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
                  aria-label={`Bỏ lọc trạng thái ${label(ORDER_STATE, s)}`}
                  onClick={() => setStatus(status.filter((x) => x !== s))}
                >
                  {label(ORDER_STATE, s)}
                </Button>
              ))}
              <Button size="small" type="link" onClick={() => setStatus([])}>
                Xóa tất cả
              </Button>
            </Space>
          ) : null}
          <Table<Order>
            rowKey="case_id"
            loading={orders.loading}
            dataSource={shown}
            pagination={false}
            sticky
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: orders.loading ? (
                " "
              ) : filtered && all.length ? (
                <Empty
                  description={
                    status.length
                      ? `Không có đơn ở trạng thái ${status.map((s) => label(ORDER_STATE, s)).join(", ")} trong nhóm này.`
                      : "Không có đơn nào khớp bộ lọc."
                  }
                >
                  <Button onClick={clear}>Xóa bộ lọc</Button>
                </Empty>
              ) : (
                <Empty description="Chưa có đơn hàng. Đơn được tạo khi DW1 xử lý thư có PO trong Hộp thư.">
                  <Link href="/sales/inbox">Mở Hộp thư</Link>
                </Empty>
              ),
            }}
            footer={() =>
              listFooter(
                shown.length,
                all.filter((o) => inGroup(view.tab, o)).length,
                all.length,
                "đơn",
                view.query !== "" || status.length > 0,
              )
            }
            columns={[
              {
                title: "Đơn hàng",
                key: "po",
                render: (_, o) => (
                  <RowTitle
                    href={`/sales/orders/${o.case_id}`}
                    title={
                      customerName(o.customer_code)
                        ? `${customerName(o.customer_code)} · ${o.lines} dòng`
                        : `Khách ${o.customer_code} · ${o.lines} dòng`
                    }
                    code={`PO ${o.po_no}${o.revision ? ` · Rev.${o.revision}` : ""}`}
                    sub={o.customer_code}
                  />
                ),
              },
              {
                title: "Trạng thái",
                key: "status",
                render: (_, o) => <OrderStateTag status={o.status} />,
              },
              {
                title: "Cờ chưa quyết định",
                key: "flags",
                render: (_, o) =>
                  o.open_findings === 0 ? (
                    <Typography.Text type="secondary">
                      Không còn cờ
                    </Typography.Text>
                  ) : (
                    <Space size={6} wrap>
                      {o.open_blocking_findings ? (
                        <StatusTag
                          tone="err"
                          icon={<StopOutlined aria-hidden />}
                        >
                          {o.open_blocking_findings} chặn
                        </StatusTag>
                      ) : null}
                      <Typography.Text type="secondary">
                        {o.open_findings} cờ
                      </Typography.Text>
                    </Space>
                  ),
              },
              {
                title: `Nhận lúc (${TIME_ZONE_LABEL})`,
                key: "received",
                align: "right",
                render: (_, o) => (
                  <span className="flex flex-col items-end">
                    <span>{formatAge(o.received_at, now)} trước</span>
                    <Typography.Text type="secondary">
                      {formatDateTime(o.received_at, { zoneLabel: false })}
                    </Typography.Text>
                  </span>
                ),
              },
              {
                title: "Phụ trách",
                key: "assigned",
                align: "center",
                render: (_, o) => (
                  <Assignee
                    name={o.assigned_to ? name(o.assigned_to) : null}
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
