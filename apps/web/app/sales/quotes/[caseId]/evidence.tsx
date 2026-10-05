"use client";

import { Card, Descriptions, Empty, Table, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { MaskedRegion } from "@dw/ui";
import { formatDate, formatMonth } from "../../../../lib/dates";
import type { Currency } from "../../../../lib/money";
import {
  isHidden,
  Money,
  OTHER_CUSTOMERS_SENTENCE,
  PRICE_SENTENCE,
  Quantity,
  UsdPerTonne,
} from "../../_components/money";

type Quote = SalesSchemas["QuoteCaseView"];
type Evidence = SalesSchemas["EvidenceView"];
type Row = SalesSchemas["QuotationRowView"];

function copper(row: Row["copper_basis"]) {
  if (row.kind === "fixed") return "Giá cố định";
  return (
    <span>
      Theo LME: <UsdPerTonne value={row.low_usd_per_tonne} /> –{" "}
      <UsdPerTonne value={row.high_usd_per_tonne} />
    </span>
  );
}

function QuotationRows({ rows, empty }: { rows: Row[]; empty: string }) {
  return (
    <Table<Row>
      size="small"
      rowKey={(r) => `${r.quote_no}:${r.prv_code}:${r.customer_code}`}
      pagination={false}
      dataSource={rows}
      scroll={{ x: "max-content" }}
      locale={{ emptyText: empty }}
      columns={[
        { title: "Báo giá", dataIndex: "quote_no" },
        { title: "Khách", dataIndex: "customer_code" },
        { title: "Mã PRV", dataIndex: "prv_code" },
        {
          title: "Đơn giá",
          key: "price",
          align: "right",
          render: (_, r) => (
            <Money
              value={r.unit_price}
              currency={r.currency}
              sentence={OTHER_CUSTOMERS_SENTENCE}
            />
          ),
        },
        {
          title: "MOQ",
          key: "moq",
          align: "right",
          render: (_, r) => <Quantity value={r.moq} uom={r.uom} />,
        },
        {
          title: "Lead time",
          key: "lt",
          render: (_, r) => `${r.lead_time_days} ngày`,
        },
        {
          title: "Căn cứ đồng",
          key: "cu",
          render: (_, r) => copper(r.copper_basis),
        },
        {
          title: "Hiệu lực",
          key: "valid",
          render: (_, r) =>
            `${formatDate(r.valid_from)} – ${formatDate(r.valid_to)}`,
        },
      ]}
    />
  );
}

/**
 * The price evidence for each line (Q7, V3BidPricing re-cut): the customer's
 * own quotation history and orders, LME, copper, freight, the floor and the
 * target, and other customers' prices. A viewer without the price scope sees
 * the whole region locked; other customers' rows are locked unless the viewer
 * also holds the other-customers scope. The API leaves the figures out; this
 * only says so, once per region (ui-quality §6).
 */
export function EvidencePanel({ quote }: { quote: Quote }) {
  const evidence = quote.evidence;
  const currency = quote.currency as Currency;
  if (isHidden(evidence)) return <MaskedRegion sentence={PRICE_SENTENCE} />;
  if (!evidence || evidence.length === 0)
    return (
      <Empty description="Chưa có căn cứ giá: căn cứ có khi Design đã phản hồi mã cho từng dòng." />
    );
  return (
    <div className="space-y-3">
      {evidence.map((line: Evidence) => (
        <Card
          key={line.line_no}
          size="small"
          type="inner"
          title={`Dòng ${line.line_no}${line.prv_code ? ` · ${line.prv_code}` : ""}`}
        >
          <Descriptions
            size="small"
            column={{ xs: 1, md: 2, xl: 3 }}
            items={[
              {
                key: "target",
                label: "Giá khách mong muốn",
                children: (
                  <Money value={line.target_price} currency={currency} />
                ),
              },
              {
                key: "floor",
                label: "Giá sàn theo chính sách",
                children: <Money value={line.floor} currency={currency} />,
              },
              {
                key: "ref",
                label: "Giá tham chiếu nội bộ",
                children: isHidden(line.reference_price) ? (
                  <Money
                    value={line.reference_price}
                    currency={currency}
                    sentence={OTHER_CUSTOMERS_SENTENCE}
                  />
                ) : line.reference_price === null ? (
                  "Chính sách không đặt"
                ) : (
                  <Money value={line.reference_price} currency={currency} />
                ),
              },
              {
                key: "lme",
                label: line.lme
                  ? `LME tháng ${formatMonth(line.lme.month)}`
                  : "LME",
                children: line.lme ? (
                  <UsdPerTonne value={line.lme.usd_per_tonne} />
                ) : (
                  "Không áp dụng"
                ),
              },
              {
                key: "cu",
                label: "Phần đồng (USD/đơn vị)",
                children: (
                  <Money value={line.copper_usd_per_uom} currency="USD" />
                ),
              },
              {
                key: "freight",
                label: "Cước vận chuyển (USD/km)",
                children: (
                  <Money value={line.freight_usd_per_km} currency="USD" />
                ),
              },
              {
                key: "policy",
                label: "Chính sách giá",
                children: (
                  <Typography.Text code>{line.pricing_policy}</Typography.Text>
                ),
              },
              {
                key: "asof",
                label: "Dữ liệu đến ngày",
                children: formatDate(line.as_of),
              },
            ]}
          />
          <Typography.Title level={5}>
            Lịch sử báo giá cho khách này
          </Typography.Title>
          <QuotationRows
            rows={line.own_history}
            empty="Chưa báo giá mã này cho khách."
          />
          <Typography.Title level={5}>
            Lịch sử đặt hàng của khách
          </Typography.Title>
          <Table
            size="small"
            rowKey={(o) => `${o.so_no}:${o.order_date}`}
            pagination={false}
            dataSource={line.orders}
            scroll={{ x: "max-content" }}
            locale={{ emptyText: "Khách chưa đặt mã này trong 12 tháng." }}
            columns={[
              { title: "Số đơn", dataIndex: "so_no" },
              {
                title: "Ngày",
                dataIndex: "order_date",
                render: (d: string) => formatDate(d),
              },
              {
                title: "Số lượng",
                dataIndex: "quantity",
                align: "right",
                render: (q: string) => <Quantity value={q} />,
              },
              {
                title: "Đơn giá",
                key: "p",
                align: "right",
                render: (_, o) => (
                  <Money value={o.unit_price} currency={o.currency} />
                ),
              },
            ]}
          />
          <Typography.Title level={5}>
            Giá đã báo cho khách khác
          </Typography.Title>
          {isHidden(line.other_customers) ? (
            <MaskedRegion sentence={OTHER_CUSTOMERS_SENTENCE} />
          ) : (
            <QuotationRows
              rows={line.other_customers}
              empty="Không có khách khác được báo mã này."
            />
          )}
        </Card>
      ))}
    </div>
  );
}
