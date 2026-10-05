"use client";

import { Suspense, useCallback, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Alert,
  Table,
  Tabs,
  Tag,
  Typography,
  type TableColumnsType,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { RegionState } from "../../../components/region-state";
import { formatDate, formatDateTime, formatMonth } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { useResource } from "../_lib/use-resource";
import {
  Money,
  OTHER_CUSTOMERS_SENTENCE,
  Quantity,
  UsdPerTonne,
} from "../_components/money";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";

type S = SalesSchemas;

/**
 * Dữ liệu giả lập (V3Library/V3Vault re-cut): a read-only view of the mock
 * master data DW1 reads through its ports, each table with the snapshot date
 * it came from. Prices show only with the price scopes; another customer's
 * quotation needs the other-customers scope as well, and the API leaves the
 * figure out otherwise.
 */
export default function MasterDataPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <MasterData />
      </Suspense>
    </ScopeGate>
  );
}

const TABS = [
  "customers",
  "items",
  "convert-list",
  "quotations",
  "lme",
  "bravo-orders",
  "open-ycbg",
] as const;
type Tab = (typeof TABS)[number];

function MasterData() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = (TABS as readonly string[]).includes(params.get("tab") ?? "")
    ? (params.get("tab") as Tab)
    : "customers";
  return (
    <div className="space-y-4">
      <PageHeader
        title="Dữ liệu giả lập"
        description="Dữ liệu chủ mà DW1 đọc qua cổng kết nối giả lập: hư cấu, chỉ đọc. Khi có Bravo và SharePoint thật, cổng được thay mà quy trình không đổi."
      />
      <Alert
        type="info"
        showIcon
        title="Mọi khách hàng, mã hàng và con số ở đây là hư cấu."
      />
      <Tabs
        activeKey={tab}
        onChange={(key) =>
          router.replace(`${pathname}?tab=${key}`, { scroll: false })
        }
        items={[
          { key: "customers", label: "Khách hàng", children: <Customers /> },
          { key: "items", label: "Mã hàng", children: <Items /> },
          {
            key: "convert-list",
            label: "Bảng quy đổi mã",
            children: <ConvertList />,
          },
          { key: "quotations", label: "Báo giá", children: <Quotations /> },
          { key: "lme", label: "LME", children: <Lme /> },
          {
            key: "bravo-orders",
            label: "Đơn Bravo 12 tháng",
            children: <BravoOrders />,
          },
          { key: "open-ycbg", label: "YCBG đang mở", children: <OpenYcbg /> },
        ]}
      />
    </div>
  );
}

function Snapshot<T extends object>({
  load,
  cacheKey,
  rowKey,
  columns,
  empty,
}: {
  load: () => Promise<{ as_of: string; items: T[] }>;
  cacheKey: string;
  rowKey: (row: T) => string;
  columns: TableColumnsType<T>;
  empty: ReactNode;
}) {
  const data = useResource(cacheKey, load);
  if (data.error)
    return <RegionState error={data.error} onRetry={data.reload} />;
  return (
    <Table<T>
      rowKey={rowKey}
      size="small"
      loading={data.loading}
      dataSource={data.data?.items ?? []}
      pagination={false}
      sticky
      scroll={{ x: "max-content" }}
      locale={{ emptyText: data.loading ? " " : empty }}
      footer={() =>
        data.data
          ? `${data.data.items.length} dòng · dữ liệu đến ${formatDateTime(data.data.as_of)}`
          : ""
      }
      columns={columns}
    />
  );
}

function Customers() {
  return (
    <Snapshot<S["CustomerView"]>
      cacheKey="sales/master-data/customers"
      load={useCallback(() => salesApi().customers(), [])}
      rowKey={(c) => c.code}
      empty="Không có khách hàng trong dữ liệu giả lập của không gian làm việc này."
      columns={[
        { title: "Mã", dataIndex: "code" },
        { title: "Tên", dataIndex: "name" },
        {
          title: "Trạng thái",
          dataIndex: "status",
          render: (s: string) =>
            s === "temporary" ? <Tag color="warning">Mã tạm thời</Tag> : s,
        },
        { title: "Ngôn ngữ", dataIndex: "language" },
        { title: "Kênh xác nhận", dataIndex: "confirmation_channel" },
        {
          title: "NOC",
          dataIndex: "noc_confirmed",
          render: (v: boolean) =>
            v ? "Có" : <Tag color="warning">Chưa có</Tag>,
        },
        {
          title: "ESF (năm tài chính)",
          dataIndex: "esf_fiscal_year",
          render: (v: number | null) => v ?? "Chưa có",
        },
        {
          title: "Kiểm tra danh sách cấm",
          dataIndex: "denial_list_checked_on",
          render: (d: string | null) => (d ? formatDate(d) : "Chưa kiểm"),
        },
        {
          title: "Cùng tập đoàn",
          dataIndex: "intra_group",
          render: (v: boolean) => (v ? "Có" : "Không"),
        },
        {
          title: "Sales phụ trách",
          dataIndex: "sales_pic",
          render: (v: string | null) => v ?? "Chưa giao",
        },
      ]}
    />
  );
}

function Items() {
  return (
    <Snapshot<S["ItemView"]>
      cacheKey="sales/master-data/items"
      load={useCallback(() => salesApi().items(), [])}
      rowKey={(i) => i.prv_code}
      empty="Không có mã hàng."
      columns={[
        {
          title: "Mã PRV",
          dataIndex: "prv_code",
          render: (c: string) => <Typography.Text code>{c}</Typography.Text>,
        },
        { title: "Số spec", dataIndex: "spec_no" },
        {
          title: "Họ cáp",
          dataIndex: "family",
          render: (f: string | null) => f ?? "Không rõ",
        },
        { title: "Số lõi", dataIndex: "cores", align: "right" },
        { title: "Tiết diện", dataIndex: "gauge" },
        {
          title: "ĐVT",
          dataIndex: "uom",
          render: (u: string | null) => u ?? "Không rõ",
        },
        {
          title: "MOQ",
          dataIndex: "moq",
          align: "right",
          render: (v: string) => <Quantity value={v} />,
        },
        {
          title: "Quy cách",
          dataIndex: "pack_multiple",
          align: "right",
          render: (v: string) => <Quantity value={v} />,
        },
        {
          title: "Lead time chuẩn",
          dataIndex: "standard_lead_time_days",
          render: (d: number) => `${d} ngày`,
        },
      ]}
    />
  );
}

function ConvertList() {
  return (
    <Snapshot<S["ConvertEntryView"]>
      cacheKey="sales/master-data/convert-list"
      load={useCallback(() => salesApi().convertList(), [])}
      rowKey={(e) => `${e.customer_code}:${e.customer_item_code}`}
      empty="Bảng quy đổi mã trống."
      columns={[
        { title: "Khách", dataIndex: "customer_code" },
        { title: "Mã của khách", dataIndex: "customer_item_code" },
        {
          title: "Mã PRV",
          dataIndex: "prv_code",
          render: (c: string) => <Typography.Text code>{c}</Typography.Text>,
        },
      ]}
    />
  );
}

function Quotations() {
  return (
    <Snapshot<S["QuotationRowView"]>
      cacheKey="sales/master-data/quotations"
      load={useCallback(() => salesApi().quotations(), [])}
      rowKey={(q) => `${q.quote_no}:${q.prv_code}:${q.customer_code}`}
      empty="Không có báo giá."
      columns={[
        { title: "Báo giá", dataIndex: "quote_no" },
        { title: "Khách", dataIndex: "customer_code" },
        { title: "Mã PRV", dataIndex: "prv_code" },
        {
          title: "Đơn giá",
          key: "p",
          align: "right",
          render: (_, q) => (
            <Money
              value={q.unit_price}
              currency={q.currency}
              sentence={OTHER_CUSTOMERS_SENTENCE}
            />
          ),
        },
        {
          title: "MOQ",
          key: "m",
          align: "right",
          render: (_, q) => <Quantity value={q.moq} uom={q.uom} />,
        },
        {
          title: "Lead time",
          dataIndex: "lead_time_days",
          render: (d: number) => `${d} ngày`,
        },
        {
          title: "Căn cứ đồng",
          key: "cu",
          render: (_, q) =>
            q.copper_basis.kind === "fixed" ? (
              "Cố định"
            ) : (
              <span>
                <UsdPerTonne value={q.copper_basis.low_usd_per_tonne} /> –{" "}
                <UsdPerTonne value={q.copper_basis.high_usd_per_tonne} />
              </span>
            ),
        },
        {
          title: "Hiệu lực",
          key: "v",
          render: (_, q) =>
            `${formatDate(q.valid_from)} – ${formatDate(q.valid_to)}`,
        },
      ]}
    />
  );
}

function Lme() {
  return (
    <Snapshot<S["LmeView"]>
      cacheKey="sales/master-data/lme"
      load={useCallback(() => salesApi().lme(), [])}
      rowKey={(m) => m.month}
      empty="Không có số LME."
      columns={[
        {
          title: "Tháng",
          dataIndex: "month",
          render: (m: string) => formatMonth(m),
        },
        {
          title: "Giá đồng LME",
          key: "v",
          align: "right",
          render: (_, m) => <UsdPerTonne value={m.usd_per_tonne} />,
        },
      ]}
    />
  );
}

function BravoOrders() {
  return (
    <Snapshot<S["BravoOrderView"]>
      cacheKey="sales/master-data/bravo-orders"
      load={useCallback(() => salesApi().bravoOrders(), [])}
      rowKey={(o) => o.so_no}
      empty="Không có đơn Bravo trong 12 tháng."
      columns={[
        { title: "Số đơn", dataIndex: "so_no" },
        { title: "Khách", dataIndex: "customer_code" },
        {
          title: "PO",
          key: "po",
          render: (_, o) =>
            `${o.po_no}${o.po_revision ? ` · Rev.${o.po_revision}` : ""}`,
        },
        {
          title: "Ngày đặt",
          dataIndex: "order_date",
          render: (d: string) => formatDate(d),
        },
        {
          title: "Số dòng",
          key: "n",
          align: "right",
          render: (_, o) => o.lines.length,
        },
        {
          title: "Dòng",
          key: "lines",
          render: (_, o) => (
            <ul className="m-0 list-none p-0">
              {o.lines.map((l) => (
                <li key={l.line_no}>
                  {l.line_no}. {l.prv_code} · <Quantity value={l.quantity} /> ·{" "}
                  <Money value={l.unit_price} currency={o.currency} /> · giao{" "}
                  {formatDate(l.delivery_date)}
                </li>
              ))}
            </ul>
          ),
        },
      ]}
    />
  );
}

function OpenYcbg() {
  return (
    <Snapshot<S["OpenYcbgView"]>
      cacheKey="sales/open-ycbg"
      load={useCallback(() => salesApi().openYcbg(), [])}
      rowKey={(y) => y.ycbg_no}
      empty="Không có YCBG đang mở."
      columns={[
        { title: "Số YCBG", dataIndex: "ycbg_no" },
        { title: "Số RFQ", dataIndex: "rfq_no" },
        { title: "Khách", dataIndex: "customer_code" },
        {
          title: "Ngày lập",
          dataIndex: "issued_on",
          render: (d: string) => formatDate(d),
        },
      ]}
    />
  );
}
