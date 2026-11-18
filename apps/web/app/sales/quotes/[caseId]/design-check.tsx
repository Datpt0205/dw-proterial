"use client";

import { Alert, Table, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { MaskedValue } from "@dw/ui";
import { formatDateTime } from "../../../../lib/dates";
import { formatMoney, formatQuantity } from "../../../../lib/money";

type Check = SalesSchemas["DesignCheck"];
type BasePrice = SalesSchemas["DesignBasePriceView"];

// Who sees a base price: said once, beside the column (ui-quality §6).
const PRICES_HIDDEN = "Chỉ người được xem giá thấy giá cơ bản của Design.";

/**
 * Design's result as Bravo holds it (ticket 16): read from the YCBG export
 * Sales uploaded, never written back. It moves nothing: a "Từ chối" is
 * Sales' to answer the customer about, a "Báo giá" still waits on Design's
 * specification.
 */
export function DesignCheckPanel({
  check,
  readBy,
  prices,
}: {
  check: Check;
  readBy: (id: string) => string;
  /** Each QUOTE line's BP in Bravo's base-price list (ticket 11); null for
   * a caller who may not read prices. */
  prices: BasePrice[] | null | undefined;
}) {
  const byLine = new Map((prices ?? []).map((p) => [p.line_no, p]));
  return (
    <div className="space-y-2">
      {check.lines.some((l) => l.verdict === "decline") ? (
        <Alert
          type="warning"
          showIcon
          title="Design từ chối trên Bravo: Sales quyết định trả lời khách."
        />
      ) : null}
      <Typography.Text>
        Kết quả trên Bravo, YCBG {check.ycbg_no} · đọc từ tệp xuất{" "}
        {formatDateTime(check.read_at)} · {readBy(check.read_by)} tải lên
      </Typography.Text>
      <Table
        size="small"
        rowKey="line_no"
        pagination={false}
        dataSource={check.lines}
        scroll={{ x: "max-content" }}
        columns={[
          { title: "Dòng", dataIndex: "line_no" },
          {
            title: "Design Check",
            dataIndex: "verdict",
            render: (v: Check["lines"][number]["verdict"]) =>
              v === "quote" ? (
                <Tag color="success">Báo giá</Tag>
              ) : (
                <Tag color="error">Từ chối</Tag>
              ),
          },
          {
            title: "Mã BP",
            dataIndex: "bp_code",
            render: (c: string | null) => c ?? "—",
          },
          {
            // Design's spec number and copper on the same export row (ticket 11).
            title: "Bản vẽ · Cu (Design)",
            key: "spec",
            render: (_: unknown, line: Check["lines"][number]) => {
              if (line.verdict !== "quote") return "—";
              const cu =
                line.copper_kg_per_bp_unit == null
                  ? null
                  : `Cu ${formatQuantity(line.copper_kg_per_bp_unit)} kg/${line.bp_unit ?? "?"}`;
              return (
                <div>
                  <div>{line.spec_no ?? "Tệp xuất không ghi bản vẽ"}</div>
                  {cu ? <div>{cu}</div> : null}
                </div>
              );
            },
          },
          {
            title: "Giá cơ bản (Bravo)",
            key: "base_price",
            render: (_: unknown, line: Check["lines"][number]) => {
              if (line.verdict !== "quote") return "—";
              if (!prices) return <MaskedValue sentence={PRICES_HIDDEN} />;
              const bp = byLine.get(line.line_no);
              if (!bp?.found || bp.base_price == null)
                return (
                  <Tag color="warning">
                    Không có trong danh mục Base price đã đọc
                  </Tag>
                );
              const cu =
                bp.copper_kg == null
                  ? ""
                  : ` · Cu ${formatQuantity(bp.copper_kg)} kg/${bp.bp_unit ?? ""}`;
              return `${formatMoney(bp.base_price, "USD")}/${bp.bp_unit ?? ""}${cu}`;
            },
          },
          {
            title: "Lý do",
            dataIndex: "reason",
            render: (r: string | null) => r ?? "—",
          },
        ]}
      />
    </div>
  );
}
