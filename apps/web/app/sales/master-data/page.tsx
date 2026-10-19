"use client";

import { Suspense, useCallback, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Alert,
  Skeleton,
  Table,
  Tabs,
  Typography,
  type TableColumnsType,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
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
import { salesCrumbs } from "../_components/crumbs";
import { ScopeGate } from "../_components/scope-gate";
import type { CatalogList } from "../_lib/catalog";
import type { Resource } from "../_lib/use-resource";
import { ImportPanel } from "./import-panel";

type S = SalesSchemas;

/**
 * Dữ liệu chủ (V3Library/V3Vault re-cut; ticket 41): the master data DW1
 * reads through its ports, each table with the snapshot date it came from.
 * The five lists Sales maintains by hand (customers, items, convert list,
 * quotations, LME) are imported from a file per list: a template, the
 * upload (read by the worker in the reader sandbox), a preview against the
 * list in force with the rows it rejects, and a submission the head decides
 * on `/approvals`. Each says whether it is still the sample data or an
 * approved import, when and by whom. Bravo's orders and open YCBG come from
 * the ERP and are not imported. Prices show only with the price scopes;
 * another customer's quotation needs the other-customers scope as well, and
 * the API leaves the figure out otherwise.
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
  const imports = useResource(
    "sales/master-data/imports",
    useCallback(() => salesApi().catalogState(), []),
  );
  const imported = (list: CatalogList, table: ReactNode) => (
    <div className="space-y-4">
      <ListImport list={list} imports={imports} />
      {table}
    </div>
  );
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Dữ liệu chủ")}
        title="Dữ liệu chủ"
        subtitle="Dữ liệu chủ DW1 đọc: mỗi danh mục dùng dữ liệu mẫu (hư cấu) cho tới khi Sales nhập tệp thật và Trưởng bộ phận Sales duyệt. Đơn Bravo và YCBG lấy từ ERP."
      />
      <Tabs
        activeKey={tab}
        onChange={(key) =>
          router.replace(`${pathname}?tab=${key}`, { scroll: false })
        }
        items={[
          {
            key: "customers",
            label: "Khách hàng",
            children: imported("customers", <Customers />),
          },
          {
            key: "items",
            label: "Mã hàng",
            children: imported("items", <Items />),
          },
          {
            key: "convert-list",
            label: "Bảng quy đổi mã",
            children: imported("convert_list", <ConvertList />),
          },
          {
            key: "quotations",
            label: "Báo giá",
            children: imported("quotations", <Quotations />),
          },
          { key: "lme", label: "LME", children: imported("lme", <Lme />) },
          {
            key: "bravo-orders",
            label: "Đơn Bravo 12 tháng",
            children: (
              <FromErp>
                <BravoOrders />
              </FromErp>
            ),
          },
          {
            key: "open-ycbg",
            label: "YCBG đang mở",
            children: (
              <FromErp>
                <OpenYcbg />
              </FromErp>
            ),
          },
        ]}
      />
    </div>
  );
}

/** One list's import panel, from the one read of every list's state. */
function ListImport({
  list,
  imports,
}: {
  list: CatalogList;
  imports: Resource<SalesSchemas["CatalogStateView"]>;
}) {
  if (imports.error)
    return <LoadError error={imports.error} onRetry={imports.reload} compact />;
  const state = imports.data?.lists.find((s) => s.catalog_list === list);
  if (!state) return <Skeleton active paragraph={{ rows: 2 }} />;
  return <ImportPanel state={state} onChanged={imports.reload} />;
}

/** The ERP's own records: not imported from a file. */
function FromErp({ children }: { children: ReactNode }) {
  return (
    <div className="space-y-4">
      <Alert
        type="info"
        showIcon
        title="Dữ liệu mẫu (hư cấu): danh sách này lấy từ Bravo (ERP), không nhập từ tệp. Khi kết nối Bravo, dữ liệu thật thay cho bản mẫu."
      />
      {children}
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
  if (data.error) return <LoadError error={data.error} onRetry={data.reload} />;
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
      empty="Không gian làm việc này chưa có khách hàng: tải mẫu và nhập tệp danh mục khách hàng."
      columns={[
        { title: "Mã", dataIndex: "code" },
        { title: "Tên", dataIndex: "name" },
        {
          title: "Trạng thái",
          dataIndex: "status",
          render: (s: string) =>
            s === "temporary" ? (
              <StatusTag tone="warn">Mã tạm thời</StatusTag>
            ) : (
              s
            ),
        },
        { title: "Ngôn ngữ", dataIndex: "language" },
        { title: "Kênh xác nhận", dataIndex: "confirmation_channel" },
        {
          title: "NOC",
          dataIndex: "noc_confirmed",
          render: (v: boolean) =>
            v ? "Có" : <StatusTag tone="warn">Chưa có</StatusTag>,
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
