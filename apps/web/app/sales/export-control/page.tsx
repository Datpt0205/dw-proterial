"use client";

import { Suspense, useCallback } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Alert, Space, Table, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDate } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { useResource } from "../_lib/use-resource";
import { CUSTOMER_STATUS, EXPORT_NEED, label } from "../_lib/labels";
import { SCOPE } from "../_components/sales-frame";
import { salesCrumbs } from "../_components/crumbs";
import { ScopeGate } from "../_components/scope-gate";
import { CustomerDrawer } from "./customer-drawer";

type Row = SalesSchemas["CustomerScreeningView"];

/**
 * Kiểm soát xuất khẩu, WIV-03-032 (ticket 45): every customer with what is
 * done and what is still owed, oldest debt first as the API lists it. A
 * customer opens in a drawer with its own URL (`?customer=`), where the
 * export-control PIC records each step's result; DW1 decides nothing, and an
 * order of a customer that owes a step is held by its own check.
 */
export default function ExportControlPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <ExportControl />
      </Suspense>
    </ScopeGate>
  );
}

function ExportControl() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const open = params.get("customer");
  const overview = useResource(
    "sales/export-control",
    useCallback(() => salesApi().exportControl(), []),
  );
  const data = overview.data;
  const owing = data?.customers.filter((c) => c.needs.length).length ?? 0;

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Kiểm soát xuất khẩu")}
        title="Kiểm soát xuất khẩu"
        subtitle={
          data
            ? `Năm tài chính ${data.fiscal_year}: ${owing} khách còn bước phải làm. Danh sách cấm kiểm lại sau ${data.denial_list_max_age_days} ngày. Đơn của khách còn thiếu bước bị giữ lại ở bước kiểm tra.`
            : "Từng khách: sàng lọc sản phẩm, danh sách cấm, red flag, NOEC/NOC, ESF và gia hạn hằng năm."
        }
      />
      {data?.sample ? (
        <Alert
          type="info"
          showIcon
          title={`Câu hỏi red flag, người duyệt ESF và thư NOEC đang là bản mẫu (${data.policy_ref}) cho tới khi có quy trình WIV-03-032 của Proterial; sửa ở Quản lý › Quy tắc.`}
        />
      ) : null}
      {overview.error ? (
        <LoadError error={overview.error} onRetry={overview.reload} />
      ) : (
        <Table<Row>
          size="small"
          rowKey="customer_code"
          loading={overview.loading && !data}
          dataSource={data?.customers ?? []}
          pagination={false}
          sticky
          scroll={{ x: "max-content" }}
          locale={{ emptyText: "Chưa có khách hàng trong dữ liệu chủ." }}
          footer={() =>
            data ? `${data.customers.length} khách hàng, đủ danh sách.` : null
          }
          columns={[
            {
              title: "Khách hàng",
              key: "customer",
              render: (_, row) => (
                <Space orientation="vertical" size={0}>
                  <Link
                    href={`${pathname}?customer=${encodeURIComponent(row.customer_code)}`}
                    scroll={false}
                  >
                    {row.customer_code}
                  </Link>
                  <Typography.Text>{row.customer_name}</Typography.Text>
                </Space>
              ),
            },
            {
              title: "Mã khách",
              key: "status",
              render: (_, row) => label(CUSTOMER_STATUS, row.status),
            },
            {
              title: "Danh sách cấm",
              key: "denial",
              render: (_, row) =>
                row.denial_list_match ? (
                  <StatusTag tone="err">Trùng danh sách cấm</StatusTag>
                ) : row.denial_list_checked_on ? (
                  `Kiểm ${formatDate(row.denial_list_checked_on)}`
                ) : (
                  <StatusTag tone="unk">Chưa kiểm</StatusTag>
                ),
            },
            {
              title: "NOC",
              key: "noc",
              render: (_, row) =>
                row.noc_confirmed ? (
                  <StatusTag tone="ok">Đã có</StatusTag>
                ) : (
                  <StatusTag tone="warn">Chưa có</StatusTag>
                ),
            },
            {
              title: "ESF",
              key: "esf",
              render: (_, row) =>
                row.esf_fiscal_year === data?.fiscal_year ? (
                  <StatusTag tone="ok">Năm {row.esf_fiscal_year}</StatusTag>
                ) : (
                  <Space orientation="vertical" size={0}>
                    <StatusTag tone="warn">
                      {row.esf_fiscal_year
                        ? `Mới có năm ${row.esf_fiscal_year}`
                        : "Chưa có"}
                    </StatusTag>
                    {row.traded_recently ? (
                      <Typography.Text>Có mua trong 12 tháng</Typography.Text>
                    ) : null}
                  </Space>
                ),
            },
            {
              title: "Còn phải làm",
              key: "needs",
              render: (_, row) =>
                row.needs.length ? (
                  <Space wrap size={4}>
                    {row.needs.map((need) => (
                      <StatusTag
                        key={need}
                        tone={
                          need === "denial_match" ||
                          need === "red_flag_escalated"
                            ? "err"
                            : "warn"
                        }
                      >
                        {label(EXPORT_NEED, need)}
                      </StatusTag>
                    ))}
                  </Space>
                ) : (
                  <StatusTag tone="ok">Đủ các bước</StatusTag>
                ),
            },
          ]}
        />
      )}
      {open && data ? (
        <CustomerDrawer
          code={open}
          fiscalYear={data.fiscal_year}
          onClose={() => router.replace(pathname, { scroll: false })}
          onChanged={overview.reload}
        />
      ) : null}
    </div>
  );
}
