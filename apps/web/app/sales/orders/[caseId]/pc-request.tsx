"use client";

import { useCallback, useState } from "react";
import {
  Alert,
  App,
  Button,
  Card,
  DatePicker,
  Form,
  InputNumber,
  Modal,
  Space,
  Table,
  Typography,
} from "antd";
import {
  CopyOutlined,
  MinusCircleOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { RegionState, StatusTag } from "@dw/ui";
import {
  formatDate,
  formatDateTime,
  fromPickerDay,
  toPickerDay,
} from "../../../../lib/dates";
import { LoadError } from "../../../../components/load-error";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import type { Viewer } from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import { GuardedButton } from "../../_components/guarded-button";
import { Quantity } from "../../_components/money";

type Order = SalesSchemas["OrderCaseView"];
type Line = Order["lines"][number];
type PickerDay = Parameters<typeof fromPickerDay>[0];

const PREPARE = "sales.order.prepare";
// Where PC's answer is taken (`OrderCase.ask_pc`, `pc_answered`): before the
// order is in Bravo. In Bravo, PC's dates are the update loop's (ticket 29).
const ASKABLE: readonly string[] = ["in_review", "prepared"];

/** Why PC cannot be asked or answered from DW1 now; null when it can. */
function pcReason(order: Order, viewer: Viewer): string | null {
  if (!viewer.hasScope(PREPARE))
    return "Bạn không có quyền ghi trên đơn hàng (cần vai Sales phụ trách).";
  if (!ASKABLE.includes(order.status))
    return "Chỉ hỏi và ghi ngày PC khi đơn đang xem xét, trước khi nhập Bravo.";
  return null;
}

/**
 * "Hỏi PC" (ticket 07): the request to PC DW1 drafts from the order, which
 * the person copies into Teams or a mail and sends from their own account
 * (DW1 sends nothing); "Ghi đã hỏi PC" starts the wait DW1 reminds on; and
 * per line, PC's answer, a date or several dates splitting the line, each
 * with its first and current date.
 */
export function PcRequestPanel({
  order,
  viewer,
  onChanged,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
}) {
  const name = usePeople();
  const { message } = App.useApp();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [answering, setAnswering] = useState<Line | null>(null);
  const reason = pcReason(order, viewer);
  const answered = order.lines.some((l) => l.pc_answer);
  const draft = useResource(
    `sales/orders/${order.case_id}/pc-request@${order.case_version}`,
    useCallback(() => salesApi().pcRequest(order.case_id), [order.case_id]),
    { enabled: viewer.hasScope(PREPARE) },
  );
  if (!ASKABLE.includes(order.status) && !answered) return null;

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success("Đã chép: dán vào Teams hoặc thư gửi PC");
    } catch {
      message.error("Trình duyệt không cho chép: chọn và chép tay nội dung.");
    }
  };

  const asked = async () => {
    const result = await run(
      "pc/asked",
      { version: order.case_version },
      (key) => salesApi().recordPcAsked(order.case_id, order.case_version, key),
      "Đã ghi đã hỏi PC",
    );
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };

  const request = draft.data;
  return (
    <Card size="small" title="Hỏi PC ngày giao">
      <Space orientation="vertical" className="w-full">
        {order.pc_request ? (
          <Space wrap role="status">
            <StatusTag tone="warn">Chờ PC trả ngày</StatusTag>
            <Typography.Text>
              {name(order.pc_request.by)} đã hỏi lúc{" "}
              {formatDateTime(order.pc_request.at)} · dòng{" "}
              {order.pc_request.lines.join(", ")}
            </Typography.Text>
            {request ? (
              <Typography.Text>
                {request.reminder_at
                  ? `DW1 nhắc lúc ${formatDateTime(request.reminder_at)} nếu PC chưa trả lời`
                  : "Nhắc chờ PC đang tắt trong quy tắc"}
              </Typography.Text>
            ) : null}
          </Space>
        ) : null}
        {viewer.hasScope(PREPARE) && ASKABLE.includes(order.status) ? (
          draft.loading ? (
            <RegionState kind="loading" compact />
          ) : draft.error ? (
            <LoadError error={draft.error} onRetry={draft.reload} />
          ) : request ? (
            <Alert
              type="info"
              title={request.subject}
              description={
                <Typography.Paragraph className="mb-0! whitespace-pre-wrap">
                  {request.body}
                </Typography.Paragraph>
              }
            />
          ) : null
        ) : null}
        <Space wrap>
          <GuardedButton
            icon={<CopyOutlined aria-hidden />}
            reason={
              viewer.hasScope(PREPARE)
                ? request
                  ? null
                  : "Bản hỏi PC chưa tải được."
                : "Bạn không có quyền soạn trên đơn hàng (cần vai Sales phụ trách)."
            }
            inlineReason={false}
            onClick={() =>
              request
                ? void copy(`${request.subject}\n\n${request.body}`)
                : null
            }
          >
            Chép bản hỏi PC
          </GuardedButton>
          <GuardedButton
            reason={reason}
            loading={pending === "pc/asked"}
            onClick={() => void asked()}
          >
            Ghi đã hỏi PC
          </GuardedButton>
        </Space>
        <ActionError error={error} />
        <Table<Line>
          size="small"
          rowKey="line_no"
          pagination={false}
          dataSource={order.lines}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Dòng", dataIndex: "line_no", width: 64 },
            {
              title: "Số lượng",
              key: "quantity",
              render: (_, l) => <Quantity value={l.quantity} uom={l.uom} />,
            },
            {
              title: "Ngày khách cần",
              key: "requested",
              render: (_, l) =>
                l.requested_date ? formatDate(l.requested_date) : "Báo sau",
            },
            {
              title: "PC trả lời (lần đầu → hiện tại)",
              key: "pc",
              render: (_, l) =>
                l.pc_answer ? (
                  <Space orientation="vertical" size={0}>
                    {l.pc_answer.deliveries.map((d, index) => (
                      <Typography.Text key={index}>
                        <Quantity value={d.quantity} uom={l.uom} /> ·{" "}
                        {d.first_date === d.date
                          ? formatDate(d.date)
                          : `${formatDate(d.first_date)} → ${formatDate(d.date)}`}
                      </Typography.Text>
                    ))}
                    <Typography.Text>
                      Ghi bởi {name(l.pc_answer.by)} ·{" "}
                      {formatDateTime(l.pc_answer.at)}
                    </Typography.Text>
                  </Space>
                ) : (
                  <Typography.Text>Chưa có</Typography.Text>
                ),
            },
            {
              title: "",
              key: "action",
              fixed: "right",
              render: (_, l) => (
                <GuardedButton
                  size="small"
                  inlineReason={false}
                  reason={reason}
                  onClick={() => setAnswering(l)}
                  aria-label={`Ghi ngày PC trả lời cho dòng ${l.line_no}`}
                >
                  Ghi ngày PC
                </GuardedButton>
              ),
            },
          ]}
        />
      </Space>
      {answering ? (
        <PcAnswerDialog
          order={order}
          line={answering}
          onClose={() => setAnswering(null)}
          onDone={() => {
            setAnswering(null);
            draft.reload();
            onChanged();
          }}
        />
      ) : null}
    </Card>
  );
}

type DeliveryForm = { quantity?: number | null; date?: PickerDay };

/**
 * PC's answer for one line: one date, or several splitting the line, whose
 * quantities add up to the line's. The server refuses a split that does not
 * add up; it is never adjusted. Confirmed again, the date PC gave first is
 * kept beside the new one.
 */
function PcAnswerDialog({
  order,
  line,
  onClose,
  onDone,
}: {
  order: Order;
  line: Line;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form] = Form.useForm<{ deliveries: DeliveryForm[] }>();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [failed, setFailed] = useState(0);
  const typed = Form.useWatch("deliveries", form) ?? [];
  const total = typed.reduce((sum, d) => sum + Number(d?.quantity ?? 0), 0);
  const whole = Number(line.quantity);
  const id = `pc/answer/${line.line_no}`;
  const initial: DeliveryForm[] = line.pc_answer
    ? line.pc_answer.deliveries.map((d) => ({
        quantity: Number(d.quantity),
        date: toPickerDay(d.date),
      }))
    : [{ quantity: whole, date: toPickerDay(line.suggested_delivery_date) }];

  const submit = async (values: { deliveries: DeliveryForm[] }) => {
    const body = {
      case_version: order.case_version,
      deliveries: values.deliveries.map((d) => ({
        quantity: String(d.quantity ?? ""),
        date: fromPickerDay(d.date) ?? "",
      })),
    };
    const result = await run(
      id,
      body,
      (key) =>
        salesApi().recordPcAnswer(order.case_id, line.line_no, body, key),
      `Đã ghi ngày PC cho dòng ${line.line_no}`,
    );
    if (result.ok) onDone();
    else setError(result.error);
  };

  return (
    <Modal
      open
      width={640}
      title={`Ngày PC trả lời cho dòng ${line.line_no}`}
      okText="Ghi ngày PC"
      cancelText="Huỷ"
      confirmLoading={pending === id}
      onOk={() => form.submit()}
      onCancel={onClose}
    >
      <Typography.Paragraph>
        Dòng {line.line_no}: <Quantity value={line.quantity} uom={line.uom} />.
        PC chia dòng thành nhiều đợt thì nhập từng đợt; tổng các đợt phải bằng
        số lượng của dòng.
      </Typography.Paragraph>
      {failed ? (
        <Alert type="error" showIcon title={`Còn ${failed} trường cần sửa`} />
      ) : null}
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        scrollToFirstError={{ focus: true }}
        initialValues={{ deliveries: initial }}
        onFinishFailed={({ errorFields }) => setFailed(errorFields.length)}
        onFinish={(values) => {
          setFailed(0);
          void submit(values);
        }}
      >
        <Form.List name="deliveries">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field, index) => (
                <Space key={field.key} align="start" wrap>
                  <Form.Item
                    name={[field.name, "quantity"]}
                    label={`Số lượng đợt ${index + 1}`}
                    rules={[{ required: true, message: "Cần số lượng" }]}
                  >
                    <InputNumber min={0} decimalSeparator="," />
                  </Form.Item>
                  <Form.Item
                    name={[field.name, "date"]}
                    label={`Ngày PC đợt ${index + 1}`}
                    rules={[{ required: true, message: "Cần ngày PC trả lời" }]}
                  >
                    <DatePicker format="DD/MM/YYYY" />
                  </Form.Item>
                  {fields.length > 1 ? (
                    <Button
                      className="mt-7"
                      icon={<MinusCircleOutlined aria-hidden />}
                      aria-label={`Bỏ đợt ${index + 1}`}
                      onClick={() => remove(field.name)}
                    />
                  ) : null}
                </Space>
              ))}
              <Button icon={<PlusOutlined aria-hidden />} onClick={() => add()}>
                Thêm một đợt
              </Button>
            </>
          )}
        </Form.List>
      </Form>
      <Typography.Paragraph className="mt-3" role="status">
        Tổng các đợt: <Quantity value={total} uom={line.uom} /> /{" "}
        <Quantity value={line.quantity} uom={line.uom} />
        {total !== whole ? " (chưa bằng số lượng của dòng)" : ""}
      </Typography.Paragraph>
      <ActionError error={error} />
    </Modal>
  );
}
