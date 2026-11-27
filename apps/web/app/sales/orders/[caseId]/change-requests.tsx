"use client";

import { useState } from "react";
import Link from "next/link";
import {
  Button,
  Card,
  DatePicker,
  Drawer,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import { MinusCircleOutlined, PlusOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";
import {
  formatDate,
  formatDateTime,
  fromPickerDay,
} from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import {
  CHANGE_LINE_STATE,
  CHANGE_READ_BY,
  CHANGE_REQUEST_STATE,
  FIELD,
  label,
} from "../../_lib/labels";
import { messageRef } from "../../_lib/messages";
import type { Viewer } from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { GuardedButton } from "../../_components/guarded-button";
import { Quantity } from "../../_components/money";

type Order = SalesSchemas["OrderCaseView"];
type Request = SalesSchemas["ChangeRequestView"];
type Line = SalesSchemas["ChangeLineView"];
type Field = Line["field"];
type Typed = SalesSchemas["TypedChange"];

const PREPARE = "sales.order.prepare";
// Where a change asked by mail is applied: the PIC decides the order's
// values and it is not in Bravo yet (`OrderCase.changed`; in Bravo it is
// the update loop's, ticket 29). The server refuses anywhere else.
const CHANGEABLE: readonly string[] = ["in_review", "prepared"];

/** Why ``line`` cannot be confirmed now; null when it can. */
export function confirmReason(
  order: Order,
  request: Request,
  line: Line,
  viewer: Viewer,
): string | null {
  if (!viewer.hasScope(PREPARE))
    return "Bạn không có quyền quyết định trên đơn hàng (cần vai Sales phụ trách).";
  if (request.state === "queued")
    return "Yêu cầu này chờ yêu cầu trước của đơn được xử lý xong.";
  if (line.blocked === "no_such_line")
    return `Đơn không có dòng ${line.line_no}: từ chối và hỏi lại khách.`;
  if (line.blocked === "unit_differs") {
    const uom = order.lines.find((l) => l.line_no === line.line_no)?.uom;
    return `Khách ghi đơn vị ${line.unit}, dòng tính bằng ${uom ?? "đơn vị khác"}: DW1 không tự quy đổi. Từ chối và hỏi lại khách.`;
  }
  if (line.blocked === "printed_schedules")
    return "Dòng có nhiều lịch giao: một giá trị không nói lịch nào. Từ chối và hỏi lại khách.";
  if (!CHANGEABLE.includes(order.status))
    return "Chỉ áp dụng thay đổi khi đơn đang xem xét, trước khi nhập Bravo.";
  return null;
}

/** Why a line of ``request`` cannot be rejected now; null when it can. */
function rejectReason(request: Request, viewer: Viewer): string | null {
  if (!viewer.hasScope(PREPARE))
    return "Bạn không có quyền quyết định trên đơn hàng (cần vai Sales phụ trách).";
  if (request.state === "queued")
    return "Yêu cầu này chờ yêu cầu trước của đơn được xử lý xong.";
  return null;
}

/**
 * What the customer asked to change by mail (ticket 27, dw_sales ADR 0010):
 * each request line by line, the value the order holds beside the value
 * asked, where it was read, and a Confirm and a Reject per line. Nothing
 * reaches the order until a person confirms that one line; a disabled
 * button says why. "Ghi yêu cầu thay đổi" records one from a customer's
 * reply on the order: DW1 reads what it can, the person types the rest.
 */
export function ChangeRequestsPanel({
  order,
  viewer,
  onChanged,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
}) {
  const [opening, setOpening] = useState(false);
  const [reading, setReading] = useState<{
    request: Request;
    line: Line;
  } | null>(null);
  const requests = order.change_requests;
  if (!requests.length && !order.replies.length) return null;
  const recorded = new Set(requests.map((r) => r.message_id));
  const replies = order.replies.filter((r) => !recorded.has(r.message_id));
  const openReason = !viewer.hasScope(PREPARE)
    ? "Bạn không có quyền ghi yêu cầu trên đơn hàng (cần vai Sales phụ trách)."
    : replies.length
      ? null
      : "Mọi thư khách trả lời trên đơn đã có yêu cầu.";
  return (
    <Card
      size="small"
      title="Khách xin thay đổi"
      extra={
        <GuardedButton
          reason={openReason}
          inlineReason={false}
          onClick={() => setOpening(true)}
        >
          Ghi yêu cầu thay đổi
        </GuardedButton>
      }
    >
      <Space orientation="vertical" className="w-full" size="middle">
        {requests.length ? null : (
          <Typography.Text type="secondary">
            Chưa ghi yêu cầu nào.
          </Typography.Text>
        )}
        {requests.map((request) => (
          <RequestBlock
            key={request.request_id}
            order={order}
            request={request}
            viewer={viewer}
            onChanged={onChanged}
            onRead={(line) => setReading({ request, line })}
          />
        ))}
      </Space>
      {opening ? (
        <OpenDialog
          order={order}
          replies={replies}
          onClose={() => setOpening(false)}
          onDone={() => {
            setOpening(false);
            onChanged();
          }}
        />
      ) : null}
      <Drawer
        open={reading !== null}
        onClose={() => setReading(null)}
        size="large"
        title={
          reading
            ? `Thư ${messageRef(reading.request.message_id)} · dòng ${reading.line.line_no}`
            : "Thư của khách"
        }
      >
        {reading && reading.request.text !== null && reading.line.anchor ? (
          <Typography.Paragraph className="whitespace-pre-wrap">
            {reading.request.text.slice(0, reading.line.anchor.start)}
            <mark>
              {reading.request.text.slice(
                reading.line.anchor.start,
                reading.line.anchor.end,
              )}
            </mark>
            {reading.request.text.slice(reading.line.anchor.end)}
          </Typography.Paragraph>
        ) : null}
      </Drawer>
    </Card>
  );
}

function shown(
  order: Order,
  line: Line,
  value: string | null,
  unit?: string | null,
) {
  if (value === null) return <span>Không có</span>;
  if (line.field === "requested_date") return <span>{formatDate(value)}</span>;
  const uom = order.lines.find((l) => l.line_no === line.line_no)?.uom;
  return <Quantity value={value} uom={unit ?? uom ?? null} />;
}

function RequestBlock({
  order,
  request,
  viewer,
  onChanged,
  onRead,
}: {
  order: Order;
  request: Request;
  viewer: Viewer;
  onChanged: () => void;
  onRead: (line: Line) => void;
}) {
  const name = usePeople();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [rejecting, setRejecting] = useState<Line | null>(null);
  const [adding, setAdding] = useState(false);
  const api = salesApi();

  const confirm = async (line: Line) => {
    const result = await run(
      `change:${request.request_id}:${line.seq}:confirm`,
      { case_version: order.case_version },
      (key) =>
        api.confirmChangeLine(
          order.case_id,
          request.request_id,
          line.seq,
          order.case_version,
          key,
        ),
      `Đã áp dụng thay đổi dòng ${line.line_no} vào đơn`,
    );
    setError(result.ok ? null : result.error);
    if (result.ok) onChanged();
  };

  const tone = request.state === "open" ? "warn" : "outline";
  return (
    <section aria-label={`Yêu cầu từ thư ${messageRef(request.message_id)}`}>
      <Space wrap size="small" className="mb-2">
        <Link
          href={`/sales/inbox?message=${encodeURIComponent(request.message_id)}`}
        >
          Thư {messageRef(request.message_id)}
        </Link>
        <StatusTag tone={tone}>
          {label(CHANGE_REQUEST_STATE, request.state)}
        </StatusTag>
        <Typography.Text type="secondary">
          {name(request.opened_by)} ghi lúc {formatDateTime(request.opened_at)}
        </Typography.Text>
        {request.unread ? (
          <Typography.Text role="note">
            {request.unread} chỗ DW1 chưa đọc được: xem thư và nhập tay.
          </Typography.Text>
        ) : null}
        {request.state !== "closed" ? (
          <GuardedButton
            size="small"
            icon={<PlusOutlined aria-hidden />}
            reason={rejectReason(request, viewer)}
            inlineReason={false}
            onClick={() => setAdding(true)}
          >
            Thêm dòng
          </GuardedButton>
        ) : null}
      </Space>
      <ActionError error={error} />
      <Table
        size="small"
        pagination={false}
        rowKey={(line) => line.seq}
        dataSource={request.lines}
        scroll={{ x: "max-content" }}
        columns={[
          { title: "Dòng", dataIndex: "line_no" },
          {
            title: "Thay đổi",
            key: "field",
            render: (_, line) => label(FIELD, line.field),
          },
          {
            title: "Đơn đang giữ",
            key: "held",
            render: (_, line) => shown(order, line, line.held),
          },
          {
            title: "Khách xin",
            key: "asked",
            render: (_, line) => shown(order, line, line.asked, line.unit),
          },
          {
            title: "Nguồn",
            key: "source",
            render: (_, line) => (
              <Space size="small" wrap>
                <StatusTag tone={line.read_by === "model" ? "pri" : "outline"}>
                  {label(CHANGE_READ_BY, line.read_by)}
                </StatusTag>
                {line.anchor && request.text !== null ? (
                  <Button size="small" type="link" onClick={() => onRead(line)}>
                    Xem trong thư
                  </Button>
                ) : null}
              </Space>
            ),
          },
          {
            title: "Quyết định",
            key: "decide",
            render: (_, line) =>
              line.state === "open" ? (
                <Space wrap size="small" align="start">
                  <GuardedButton
                    size="small"
                    type="primary"
                    reason={confirmReason(order, request, line, viewer)}
                    loading={
                      pending ===
                      `change:${request.request_id}:${line.seq}:confirm`
                    }
                    onClick={() => void confirm(line)}
                  >
                    Xác nhận
                  </GuardedButton>
                  <GuardedButton
                    size="small"
                    reason={rejectReason(request, viewer)}
                    inlineReason={false}
                    onClick={() => setRejecting(line)}
                  >
                    Từ chối
                  </GuardedButton>
                </Space>
              ) : (
                <Typography.Text
                  ellipsis={line.reason ? { tooltip: line.reason } : false}
                  className="max-w-xs"
                >
                  {label(CHANGE_LINE_STATE, line.state)} ·{" "}
                  {name(line.decided_by)}
                  {line.reason ? ` · ${line.reason}` : ""}
                </Typography.Text>
              ),
          },
        ]}
      />
      {rejecting ? (
        <RejectDialog
          order={order}
          request={request}
          line={rejecting}
          onClose={() => setRejecting(null)}
          onDone={() => {
            setRejecting(null);
            onChanged();
          }}
        />
      ) : null}
      {adding ? (
        <AddLineDialog
          order={order}
          request={request}
          onClose={() => setAdding(false)}
          onDone={() => {
            setAdding(false);
            onChanged();
          }}
        />
      ) : null}
    </section>
  );
}

function RejectDialog({
  order,
  request,
  line,
  onClose,
  onDone,
}: {
  order: Order;
  request: Request;
  line: Line;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form] = Form.useForm<{ reason: string }>();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const id = `change:${request.request_id}:${line.seq}:reject`;
  const submit = async ({ reason }: { reason: string }) => {
    const result = await run(
      id,
      { reason },
      (key) =>
        salesApi().rejectChangeLine(
          order.case_id,
          request.request_id,
          line.seq,
          order.case_version,
          reason.trim(),
          key,
        ),
      `Đã từ chối thay đổi dòng ${line.line_no}`,
    );
    if (result.ok) onDone();
    else setError(result.error);
  };
  return (
    <Modal
      open
      title={`Từ chối thay đổi dòng ${line.line_no}`}
      okText="Từ chối"
      cancelText="Hủy"
      confirmLoading={pending === id}
      onOk={() => form.submit()}
      onCancel={onClose}
    >
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        onFinish={submit}
      >
        <Form.Item
          name="reason"
          label="Lý do"
          rules={[
            { required: true, whitespace: true, message: "Ghi lý do từ chối." },
            { max: 500, message: "Lý do tối đa 500 ký tự." },
          ]}
        >
          <Input.TextArea rows={3} />
        </Form.Item>
      </Form>
      <ActionError error={error} />
    </Modal>
  );
}

type LineForm = {
  line_no?: number;
  field?: Field;
  day?: unknown;
  quantity?: number;
};

function typed(lines: readonly LineForm[] | undefined): Typed[] {
  return (lines ?? []).flatMap((l) => {
    if (l.line_no === undefined || l.field === undefined) return [];
    const value =
      l.field === "requested_date"
        ? fromPickerDay(l.day as Parameters<typeof fromPickerDay>[0])
        : l.quantity !== undefined
          ? String(l.quantity)
          : null;
    return value ? [{ line_no: l.line_no, field: l.field, value }] : [];
  });
}

/** One typed line: which line, which value, the value. */
function LineFields({
  order,
  name,
  remove,
}: {
  order: Order;
  name: number;
  remove?: () => void;
}) {
  return (
    <Space wrap align="start">
      <Form.Item
        name={[name, "line_no"]}
        label="Dòng"
        rules={[{ required: true, message: "Chọn dòng." }]}
      >
        <Select
          className="min-w-40"
          options={order.lines.map((l) => ({
            value: l.line_no,
            label: `${l.line_no} · ${l.customer_item_code}`,
          }))}
        />
      </Form.Item>
      <Form.Item
        name={[name, "field"]}
        label="Thay đổi"
        rules={[{ required: true, message: "Chọn giá trị." }]}
      >
        <Select
          className="min-w-32"
          options={(["requested_date", "quantity"] as const).map((f) => ({
            value: f,
            label: label(FIELD, f),
          }))}
        />
      </Form.Item>
      <Form.Item noStyle dependencies={[[name, "field"]]}>
        {({ getFieldValue }) =>
          getFieldValue(["lines", name, "field"]) === "quantity" ? (
            <Form.Item
              name={[name, "quantity"]}
              label="Số lượng khách xin"
              rules={[{ required: true, message: "Nhập số lượng." }]}
            >
              <InputNumber min={0.001} />
            </Form.Item>
          ) : (
            <Form.Item
              name={[name, "day"]}
              label="Ngày khách xin"
              rules={[{ required: true, message: "Chọn ngày." }]}
            >
              <DatePicker format="DD/MM/YYYY" />
            </Form.Item>
          )
        }
      </Form.Item>
      {remove ? (
        <Button
          type="text"
          aria-label="Bỏ dòng này"
          icon={<MinusCircleOutlined aria-hidden />}
          onClick={remove}
          className="mt-8"
        />
      ) : null}
    </Space>
  );
}

function OpenDialog({
  order,
  replies,
  onClose,
  onDone,
}: {
  order: Order;
  replies: readonly SalesSchemas["CaseReplyView"][];
  onClose: () => void;
  onDone: () => void;
}) {
  const [form] = Form.useForm<{ message_id: string; lines?: LineForm[] }>();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const newest = [...replies].sort(
    (a, b) => Date.parse(b.processed_at) - Date.parse(a.processed_at),
  );
  const submit = async (values: { message_id: string; lines?: LineForm[] }) => {
    const body = {
      case_version: order.case_version,
      message_id: values.message_id,
      lines: typed(values.lines),
    };
    const result = await run(
      `change:${order.case_id}:open`,
      body,
      (key) => salesApi().openChangeRequest(order.case_id, body, key),
      "Đã ghi yêu cầu thay đổi",
    );
    if (result.ok) onDone();
    else setError(result.error);
  };
  return (
    <Modal
      open
      width={720}
      title="Ghi yêu cầu thay đổi"
      okText="Ghi yêu cầu"
      cancelText="Hủy"
      confirmLoading={pending === `change:${order.case_id}:open`}
      onOk={() => form.submit()}
      onCancel={onClose}
    >
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        initialValues={{ message_id: newest[0]?.message_id }}
        onFinish={submit}
      >
        <Form.Item
          name="message_id"
          label="Thư khách trả lời"
          rules={[{ required: true, message: "Chọn thư." }]}
        >
          <Select
            options={newest.map((r) => ({
              value: r.message_id,
              label: `Thư ${messageRef(r.message_id)} · ${formatDateTime(r.processed_at)}`,
            }))}
          />
        </Form.Item>
        <Typography.Paragraph type="secondary">
          DW1 tự tách bảng trong thư. Dòng DW1 không đọc được thì nhập ở dưới.
        </Typography.Paragraph>
        <Form.List name="lines">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <LineFields
                  key={field.key}
                  order={order}
                  name={field.name}
                  remove={() => remove(field.name)}
                />
              ))}
              <Button icon={<PlusOutlined aria-hidden />} onClick={() => add()}>
                Nhập một dòng
              </Button>
            </>
          )}
        </Form.List>
      </Form>
      <div className="mt-3">
        <ActionError error={error} />
      </div>
    </Modal>
  );
}

function AddLineDialog({
  order,
  request,
  onClose,
  onDone,
}: {
  order: Order;
  request: Request;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form] = Form.useForm<{ lines: LineForm[] }>();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const id = `change:${request.request_id}:add`;
  const submit = async (values: { lines: LineForm[] }) => {
    const [line] = typed(values.lines);
    if (!line) return;
    const body = { ...line, case_version: order.case_version };
    const result = await run(
      id,
      body,
      (key) =>
        salesApi().addChangeLine(order.case_id, request.request_id, body, key),
      "Đã thêm dòng thay đổi",
    );
    if (result.ok) onDone();
    else setError(result.error);
  };
  return (
    <Modal
      open
      width={720}
      title="Thêm dòng thay đổi"
      okText="Thêm dòng"
      cancelText="Hủy"
      confirmLoading={pending === id}
      onOk={() => form.submit()}
      onCancel={onClose}
    >
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        initialValues={{ lines: [{}] }}
        onFinish={submit}
      >
        <Form.List name="lines">
          {(fields) =>
            fields.map((field) => (
              <LineFields key={field.key} order={order} name={field.name} />
            ))
          }
        </Form.List>
      </Form>
      <ActionError error={error} />
    </Modal>
  );
}
