"use client";

import { Alert, Table, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { ReadByTag } from "../../_components/tags";
import { label, READ_ATTRIBUTE, READING_REASON } from "../../_lib/labels";

type Reading = NonNullable<
  SalesSchemas["OrderLineView"]["basis"]["description_reading"]
>;
type Span = Reading["spans"][number];

/**
 * What a local model read from a line's description, beside the text it read
 * each attribute from (ticket 28, dw_sales ADR 0005). A label the model chose
 * is marked as the model's, so Sales checks it against the words before
 * confirming the code; a number is always DW1's own, parsed from the words.
 * When DW1 did not take the reading, it says so and why: the line is Sales'
 * to map, as without a model. Nothing here confirms anything.
 */
export function DescriptionReadingPanel({
  reading,
}: {
  reading: Reading | null | undefined;
}) {
  if (!reading) return null;
  if (reading.outcome === "unavailable") {
    return (
      <Alert
        type="warning"
        showIcon
        title="DW1 không đọc được mô tả"
        description="Mô hình cục bộ không trả lời được lúc xử lý. Hãy tra mã như mọi dòng chưa có mã."
      />
    );
  }
  if (reading.outcome === "not_understood") {
    return (
      <Alert
        type="warning"
        showIcon
        title="DW1 không dùng cách đọc của mô hình"
        description={`Lý do: ${label(READING_REASON, reading.reason)}. Hãy tra mã như mọi dòng chưa có mã.`}
      />
    );
  }
  return (
    <section aria-label="Mô hình đọc mô tả">
      <Typography.Paragraph className="!mb-2">
        Mã ứng viên được DW1 tìm từ các thuộc tính dưới đây. Nhãn do mô hình
        chọn cần bạn đối chiếu với chữ trên PO; con số do DW1 tự đọc từ chữ.
      </Typography.Paragraph>
      <Table<Span>
        size="small"
        rowKey={(span) => `${span.attribute}:${span.start}`}
        pagination={false}
        scroll={{ x: "max-content" }}
        dataSource={reading.spans}
        columns={[
          {
            title: "Thuộc tính",
            key: "attribute",
            render: (_, span) => label(READ_ATTRIBUTE, span.attribute),
          },
          {
            title: "Chữ trên PO",
            key: "span",
            render: (_, span) => (
              <Typography.Text mark>{span.span}</Typography.Text>
            ),
          },
          {
            title: "Giá trị",
            key: "value",
            render: (_, span) => (
              <Typography.Text code>{span.value}</Typography.Text>
            ),
          },
          {
            title: "Ai đọc",
            key: "by",
            render: (_, span) => <ReadByTag by={span.read_by} />,
          },
        ]}
      />
    </section>
  );
}
