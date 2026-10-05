"use client";

import { useState } from "react";
import { Button, Descriptions, Space, Table, Tag, Typography } from "antd";
import {
  CalendarOutlined,
  CheckCircleOutlined,
  EyeOutlined,
} from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { formatDate, formatDateTime } from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { FIELD, label, REGION_FLAG } from "../../_lib/labels";
import {
  EDITABLE,
  shortLeadTimeWaiting,
  type Viewer,
} from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { basisStatement } from "../../_lib/statements";
import { useAction } from "../../_lib/use-action";
import { GuardedButton } from "../../_components/guarded-button";
import { Money, Quantity } from "../../_components/money";
import { MappingTag, ValueStateTag } from "../../_components/tags";

type Order = SalesSchemas["OrderCaseView"];
type Line = SalesSchemas["OrderLineView"];

/** The least sure state among a line's values: what the row shows. */
const STATE_ORDER = [
  "uncertain",
  "hand_entered",
  "dw",
  "superseded",
  "confirmed",
];
function weakest(states: Record<string, string>): string {
  const values = Object.values(states);
  return STATE_ORDER.find((s) => values.includes(s)) ?? "dw";
}

/** Past this many lines the table renders only the rows in view (G23). */
const VIRTUAL_FROM = 200;

/**
 * The lines DW1 read, each value beside the source it came from (V3BidMatrix
 * re-cut). Every value carries its state; the delivery date keeps DW1's
 * suggestion ("gợi ý") apart from the date Sales confirmed (G8). The row
 * opens to what the line was checked against, stamped when the check ran.
 */
export function LinesTable({
  order,
  viewer,
  onChanged,
  onOpenSource,
  onPickCode,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
  onOpenSource: (field: string, lineNo: number | null) => void;
  onPickCode: (lineNo: number) => void;
}) {
  const name = usePeople();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const waiting = new Set(shortLeadTimeWaiting(order));
  const shortLines = new Set(
    order.findings
      .filter((f) => f.code === "requested_date_short_lt")
      .map((f) => f.line_no),
  );
  const editable = EDITABLE.includes(order.status);
  const canPrepare = viewer.hasScope("sales.order.prepare");
  const many = order.lines.length > VIRTUAL_FROM;

  const recordPc = async (line: Line) => {
    const result = await run(
      `pc/${line.line_no}`,
      { line: line.line_no, version: order.case_version },
      (key) =>
        salesApi().recordPcDate(
          order.case_id,
          line.line_no,
          order.case_version,
          key,
        ),
      `Đã ghi PC đồng ý ngày cho dòng ${line.line_no}`,
    );
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };

  return (
    <div className="space-y-2">
      <ActionError error={error} />
      <Table<Line>
        rowKey="line_no"
        dataSource={order.lines}
        pagination={false}
        sticky
        size="small"
        virtual={many}
        scroll={many ? { x: 1600, y: 640 } : { x: "max-content" }}
        footer={() => `${order.lines.length} dòng`}
        expandable={{
          expandedRowRender: (line) => (
            <LineDetail
              order={order}
              line={line}
              onOpenSource={onOpenSource}
              name={name}
            />
          ),
        }}
        columns={[
          { title: "Dòng", dataIndex: "line_no", width: 64, fixed: "left" },
          { title: "Mã của khách", dataIndex: "customer_item_code" },
          {
            title: "Mô tả",
            dataIndex: "description",
            width: 280,
            render: (text: string) => (
              <Typography.Text
                ellipsis={{ tooltip: text }}
                className="max-w-[17rem]"
              >
                {text}
              </Typography.Text>
            ),
          },
          {
            title: "Mã PRV",
            key: "prv",
            render: (_, line) => (
              <Space orientation="vertical" size={2}>
                {line.mapping.prv_code ? (
                  <Typography.Text code>
                    {line.mapping.prv_code}
                  </Typography.Text>
                ) : null}
                <MappingTag status={line.mapping.status} />
                {line.mapping.confirmed_by ? (
                  <Typography.Text>
                    {name(line.mapping.confirmed_by)}
                  </Typography.Text>
                ) : null}
                {!["exact", "candidate_confirmed"].includes(
                  line.mapping.status,
                ) && editable ? (
                  <GuardedButton
                    size="small"
                    inlineReason={false}
                    reason={
                      canPrepare ? null : "Bạn không có quyền xác nhận mã PRV."
                    }
                    onClick={() => onPickCode(line.line_no)}
                  >
                    Chọn mã
                  </GuardedButton>
                ) : null}
              </Space>
            ),
          },
          {
            title: "Số lượng",
            key: "qty",
            align: "right",
            render: (_, line) => (
              <Quantity value={line.quantity} uom={line.uom} />
            ),
          },
          {
            title: "Đơn giá",
            key: "price",
            align: "right",
            render: (_, line) => (
              <Money value={line.unit_price} currency={order.currency} />
            ),
          },
          {
            title: "Thành tiền",
            key: "amount",
            align: "right",
            render: (_, line) => (
              <Money value={line.amount} currency={order.currency} />
            ),
          },
          {
            title: "Ngày yêu cầu",
            dataIndex: "requested_date",
            render: (d: string) => formatDate(d),
          },
          {
            title: "Ngày giao",
            key: "delivery",
            render: (_, line) => (
              <Space orientation="vertical" size={2}>
                {line.confirmed_delivery_date ? (
                  <Tag
                    color="success"
                    icon={<CheckCircleOutlined aria-hidden />}
                  >
                    Đã xác nhận {formatDate(line.confirmed_delivery_date)}
                  </Tag>
                ) : null}
                {line.suggested_delivery_date ? (
                  <Tag icon={<CalendarOutlined aria-hidden />}>
                    Gợi ý {formatDate(line.suggested_delivery_date)}
                  </Tag>
                ) : (
                  <Typography.Text>Chưa có gợi ý</Typography.Text>
                )}
                {shortLines.has(line.line_no) ? (
                  line.pc_confirmed_by ? (
                    <Typography.Text>
                      PC đồng ý · {name(line.pc_confirmed_by)} ·{" "}
                      {formatDateTime(line.pc_confirmed_at)}
                    </Typography.Text>
                  ) : waiting.has(line.line_no) &&
                    !["closed", "confirmed", "received", "checked"].includes(
                      order.status,
                    ) ? (
                    <GuardedButton
                      size="small"
                      inlineReason={false}
                      reason={
                        canPrepare
                          ? null
                          : "Bạn không có quyền ghi ngày PC đồng ý."
                      }
                      loading={pending === `pc/${line.line_no}`}
                      onClick={() => recordPc(line)}
                    >
                      Ghi PC đã đồng ý
                    </GuardedButton>
                  ) : null
                ) : null}
              </Space>
            ),
          },
          {
            title: "Độ chắc",
            key: "state",
            render: (_, line) => (
              <ValueStateTag state={weakest(line.value_states)} />
            ),
          },
          {
            title: "Nguồn",
            key: "source",
            fixed: "right",
            render: (_, line) => (
              <Button
                size="small"
                icon={<EyeOutlined aria-hidden />}
                onClick={() => onOpenSource("description", line.line_no)}
                aria-label={`Xem nguồn dòng ${line.line_no}`}
              >
                Xem
              </Button>
            ),
          },
        ]}
      />
    </div>
  );
}

function LineDetail({
  order,
  line,
  onOpenSource,
  name,
}: {
  order: Order;
  line: Line;
  onOpenSource: (field: string, lineNo: number | null) => void;
  name: (id: string | null | undefined) => string;
}) {
  const fields = Object.entries(line.value_states);
  return (
    <div className="space-y-2">
      <Typography.Paragraph className="!mb-0">
        <Typography.Text strong>Căn cứ: </Typography.Text>
        {basisStatement(line.basis, order.catalog_as_of)}.
      </Typography.Paragraph>
      {line.basis.quotation ? (
        <Descriptions
          size="small"
          column={{ xs: 1, md: 3 }}
          items={[
            {
              key: "price",
              label: "Đơn giá báo",
              children: (
                <Money
                  value={line.basis.quotation.unit_price}
                  currency={line.basis.quotation.currency}
                />
              ),
            },
            {
              key: "moq",
              label: "MOQ",
              children: (
                <Quantity
                  value={line.basis.quotation.moq}
                  uom={line.basis.quotation.uom}
                />
              ),
            },
            {
              key: "pack",
              label: "Quy cách đóng gói",
              children: line.basis.item ? (
                <Quantity
                  value={line.basis.item.pack_multiple}
                  uom={line.basis.item.uom}
                />
              ) : (
                "Không rõ"
              ),
            },
          ]}
        />
      ) : null}
      {line.flags.length ? (
        <Space wrap>
          {line.flags.map((flag) => (
            <Tag key={`${flag.field}:${flag.flag}`} color="purple">
              {label(FIELD, flag.field)}: {label(REGION_FLAG, flag.flag)}
            </Tag>
          ))}
        </Space>
      ) : null}
      <Space wrap size={[8, 4]}>
        {fields.map(([field, state]) => (
          <Button
            key={field}
            size="small"
            type="text"
            onClick={() => onOpenSource(field, line.line_no)}
          >
            {label(FIELD, field)} <ValueStateTag state={state} />
          </Button>
        ))}
      </Space>
      {line.mapping.hand_entered ? (
        <Typography.Text>
          Mã PRV nhập tay bởi {name(line.mapping.confirmed_by)}: người kiểm chéo
          phải là người khác.
        </Typography.Text>
      ) : null}
    </div>
  );
}
