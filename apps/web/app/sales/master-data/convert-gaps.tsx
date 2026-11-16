"use client";

import { useCallback } from "react";
import { Alert, Card, Table, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { useResource } from "../_lib/use-resource";

type Gap = SalesSchemas["ConvertGap"];

const STATE: Record<Gap["state"], { text: string; color: string }> = {
  not_in_bravo: { text: "Chưa có trong Bravo", color: "warning" },
  waiting_in_bravo: { text: "Chờ duyệt trong Bravo", color: "processing" },
};

/**
 * The codes Sales confirmed in DW1 that Bravo's convert list does not answer
 * yet (ticket 04), and Bravo's own rows still waiting: to enter and approve
 * in Bravo, after which Bravo's row answers first and the code leaves here.
 */
export function ConvertGaps() {
  const gaps = useResource(
    "sales/master-data/convert-gaps",
    useCallback(() => salesApi().convertGaps(), []),
  );
  if (gaps.error) return <LoadError error={gaps.error} onRetry={gaps.reload} />;
  const data = gaps.data;
  return (
    <Card size="small" title="Chưa có trong Bravo">
      {data && !data.bravo_read ? (
        <Typography.Text role="note">
          Chưa có bảng quy đổi nào của Bravo được duyệt: chưa so được mã nào còn
          thiếu trong Bravo.
        </Typography.Text>
      ) : (
        <div className="space-y-2">
          {data?.as_of ? (
            <Alert
              type="info"
              showIcon
              title={`So với bảng quy đổi Bravo đọc ngày ${formatDateTime(data.as_of)}`}
            />
          ) : null}
          <Table
            size="small"
            rowKey={(g) => `${g.customer_code}·${g.customer_item_code}`}
            loading={gaps.loading && !data}
            pagination={false}
            dataSource={data?.gaps ?? []}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: "Bravo đã có mọi mã Sales xác nhận trong DW1.",
            }}
            columns={[
              { title: "Mã khách", dataIndex: "customer_code" },
              { title: "Mã hàng của khách", dataIndex: "customer_item_code" },
              {
                title: "Trạng thái",
                dataIndex: "state",
                render: (s: Gap["state"]) => (
                  <Tag color={STATE[s].color}>{STATE[s].text}</Tag>
                ),
              },
              {
                title: "Mã PRV Sales xác nhận",
                dataIndex: "prv_code",
                render: (c: string | null) => c ?? "—",
              },
              {
                title: "Mã PRV trong Bravo",
                dataIndex: "bravo_prv_code",
                render: (c: string | null) => c ?? "—",
              },
              {
                title: "Xác nhận lúc",
                dataIndex: "recorded_at",
                render: (at: string | null) => (at ? formatDateTime(at) : "—"),
              },
            ]}
          />
        </div>
      )}
    </Card>
  );
}
