"use client";

import { Suspense, useCallback } from "react";
import Link from "next/link";
import { Button, Empty, Select, Space, Table, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { RegionState } from "../../../components/region-state";
import { formatAge, formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { useNow } from "../../../lib/use-now";
import { salesApi } from "../_lib/api";
import { label, ORDER_STATE } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useResource } from "../_lib/use-resource";
import { useStatusFilter } from "../_lib/use-status-filter";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";
import { OrderStateTag } from "../_components/tags";

type Order = SalesSchemas["OrderSummaryView"];

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
  const orders = useResource(
    "sales/orders",
    useCallback(() => salesApi().orders(), []),
  );
  const [status, setStatus] = useStatusFilter();
  const all = orders.data ?? [];
  const shown = status.length
    ? all.filter((o) => status.includes(o.status))
    : all;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Đơn hàng"
        description="Mỗi số PO của khách là một hồ sơ, từ bản đầu tới khi xác nhận; bản sửa của khách vào cùng hồ sơ."
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
          options={Object.entries(ORDER_STATE).map(([value, text]) => ({
            value,
            label: text,
          }))}
        />
        {status.length ? (
          <Button onClick={() => setStatus([])}>Xóa bộ lọc</Button>
        ) : null}
      </Space>
      {orders.error ? (
        <RegionState error={orders.error} onRetry={orders.reload} />
      ) : (
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
            ) : status.length ? (
              <Empty
                description={`Không có đơn ở trạng thái ${status.map((s) => label(ORDER_STATE, s)).join(", ")}.`}
              >
                <Button onClick={() => setStatus([])}>Xóa bộ lọc</Button>
              </Empty>
            ) : (
              <Empty description="Chưa có đơn hàng. Đơn được tạo khi DW1 xử lý thư có PO trong Hộp thư.">
                <Link href="/sales/inbox">Mở Hộp thư</Link>
              </Empty>
            ),
          }}
          footer={() =>
            `${shown.length}/${all.length} đơn${status.length ? " (đang lọc)" : ""}`
          }
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
              key: "status",
              render: (_, o) => <OrderStateTag status={o.status} />,
            },
            { title: "Số dòng", dataIndex: "lines", align: "right" },
            {
              title: "Cờ chưa quyết định",
              key: "flags",
              render: (_, o) =>
                o.open_findings === 0 ? (
                  "0"
                ) : (
                  <Space size={4}>
                    <span>{o.open_findings}</span>
                    {o.open_blocking_findings ? (
                      <Tag color="error">{o.open_blocking_findings} chặn</Tag>
                    ) : null}
                  </Space>
                ),
            },
            {
              title: `Nhận lúc (${TIME_ZONE_LABEL})`,
              key: "received",
              render: (_, o) => (
                <Space orientation="vertical" size={0}>
                  <span>
                    {formatDateTime(o.received_at, { zoneLabel: false })}
                  </span>
                  <Typography.Text>
                    {formatAge(o.received_at, now)} trước
                  </Typography.Text>
                </Space>
              ),
            },
            {
              title: "Phụ trách",
              key: "assigned",
              render: (_, o) =>
                o.assigned_to
                  ? name(o.assigned_to)
                  : "Chưa giao, mọi PIC nhận được",
            },
          ]}
        />
      )}
    </div>
  );
}
