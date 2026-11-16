"use client";

import { Alert, Table, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { formatDateTime } from "../../../../lib/dates";

type Check = SalesSchemas["DesignCheck"];

/**
 * Design's result as Bravo holds it (ticket 16): read from the YCBG export
 * Sales uploaded, never written back. It moves nothing: a "Từ chối" is
 * Sales' to answer the customer about, a "Báo giá" still waits on Design's
 * specification.
 */
export function DesignCheckPanel({
  check,
  readBy,
}: {
  check: Check;
  readBy: (id: string) => string;
}) {
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
            title: "Lý do",
            dataIndex: "reason",
            render: (r: string | null) => r ?? "—",
          },
        ]}
      />
    </div>
  );
}
