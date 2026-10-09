"use client";

import { useCallback } from "react";
import Link from "next/link";
import { Alert, Table, Typography } from "antd";
import { PageHeader } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { salesApi } from "../../_lib/api";
import { useResource } from "../../_lib/use-resource";
import { SCOPE } from "../../_components/sales-frame";
import { salesCrumbs } from "../../_components/crumbs";
import { ScopeGate } from "../../_components/scope-gate";

/**
 * Rà soát báo giá năm (WIV-03-023 step 12, on mock data): every item quoted to
 * a customer with no order of it in the window, for Sales to decide whether
 * the quotation stays. DW1 lists; Sales decides, outside this page.
 */
export default function ScreeningPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Screening />
    </ScopeGate>
  );
}

function Screening() {
  const report = useResource(
    "sales/screening",
    useCallback(() => salesApi().screening(), []),
  );
  const rows = report.data ?? [];
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs(
          { title: "Báo giá", href: "/sales/quotes" },
          "Rà soát báo giá năm",
        )}
        title="Rà soát báo giá năm"
        subtitle="Mã đã báo cho khách nhưng 12 tháng không có đơn nào, trên dữ liệu giả lập. Sales quyết định giữ hay bỏ từng báo giá."
        actions={<Link href="/sales/quotes">Về danh sách báo giá</Link>}
      />
      <Alert
        type="info"
        showIcon
        title="Báo cáo chỉ liệt kê; không xóa hay đổi báo giá nào."
      />
      {report.error ? (
        <LoadError error={report.error} onRetry={report.reload} />
      ) : (
        <Table
          rowKey={(r) => `${r.customer_code}:${r.prv_code}`}
          loading={report.loading}
          dataSource={rows}
          pagination={false}
          sticky
          scroll={{ x: "max-content" }}
          locale={{
            emptyText: report.loading
              ? " "
              : "Mọi mã đã báo đều có đơn trong 12 tháng.",
          }}
          footer={() => `${rows.length} cặp khách và mã`}
          columns={[
            { title: "Khách", dataIndex: "customer_code" },
            {
              title: "Mã PRV",
              dataIndex: "prv_code",
              render: (c: string) => (
                <Typography.Text code>{c}</Typography.Text>
              ),
            },
            {
              title: "Báo giá liên quan",
              dataIndex: "quote_nos",
              render: (nos: string[]) => nos.join(", "),
            },
          ]}
        />
      )}
    </div>
  );
}
