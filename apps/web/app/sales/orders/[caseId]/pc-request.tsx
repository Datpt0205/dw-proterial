"use client";

import { useCallback, useEffect, useState } from "react";
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
import { ARTIFACT_KIND, label } from "../../_lib/labels";
import type { Viewer } from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import { GuardedButton } from "../../_components/guarded-button";
import { Quantity } from "../../_components/money";
import { ValueStateTag } from "../../_components/tags";

type Order = SalesSchemas["OrderCaseView"];
type Line = Order["lines"][number];
type PickerDay = Parameters<typeof fromPickerDay>[0];

const PREPARE = "sales.order.prepare";
// Where PC's answer is taken (`OrderCase.ask_pc`, `pc_answered`): before the
// order is in Bravo. In Bravo, PC's dates are the update loop's (ticket 29).
const ASKABLE: readonly string[] = ["in_review", "prepared"];
const NO_PREPARE =
  "Bạn không có quyền ghi trên đơn hàng (cần vai Sales phụ trách).";

/** Why PC cannot be asked or answered from DW1 now; null when it can. */
function pcReason(order: Order, viewer: Viewer): string | null {
  if (!viewer.hasScope(PREPARE)) return NO_PREPARE;
  if (!ASKABLE.includes(order.status))
    return "Chỉ hỏi và ghi ngày PC khi đơn đang xem xét, trước khi nhập Bravo.";
  return null;
}

/**
 * "Hỏi PC" (ticket 07): the request to PC DW1 drafts from the order, which
 * the person copies into Teams or a mail from their own account, or sends as
 * the order's PC draft from the files panel (ticket 77: to the tenant's PC
 * mailboxes only, recorded asked on its receipt); "Ghi đã hỏi PC" starts the
 * wait DW1 reminds on; and
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
  // "Sửa" on DW1's reading of PC's mail opens the answer form with its dates.
  const [prefill, setPrefill] = useState<
    { quantity: string; date: string | null }[] | null
  >(null);
  // PC's mail open in its dialog, and each mail this person opened, by the
  // case version it was served at: "Đúng" needs it at the current one.
  const [reading, setReading] = useState<string | null>(null);
  const [opened, setOpened] = useState<Record<string, number>>({});
  const reason = pcReason(order, viewer);
  const proposals = order.pc_reply?.dates ?? [];
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

  const proposedFor = (line: Line) =>
    proposals
      .filter((d) => d.line_no === line.line_no)
      .sort((a, b) => a.delivery - b.delivery);
  const mailsOf = (line: Line) => [
    ...new Set(proposedFor(line).map((d) => d.message_id)),
  ];

  const accept = async (line: Line) => {
    const id = `pc/accept/${line.line_no}`;
    const result = await run(
      id,
      { line: line.line_no, version: order.case_version },
      (key) =>
        salesApi().acceptPcReply(
          order.case_id,
          line.line_no,
          order.case_version,
          key,
        ),
      `Đã ghi ngày PC cho dòng ${line.line_no}`,
    );
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };

  const proposalColumn = {
    title: "DW1 đọc thư PC",
    key: "proposal",
    render: (_: unknown, l: Line) => {
      const proposed = proposedFor(l);
      if (!proposed.length) return null;
      const mails = mailsOf(l);
      const unopened = mails.some((m) => opened[m] !== order.case_version);
      return (
        <Space orientation="vertical" size={4}>
          <ValueStateTag state="dw" />
          {proposed.map((d) => (
            <Typography.Text key={d.delivery}>
              {proposed.length > 1 ? `Đợt ${d.delivery}: ` : ""}
              {formatDate(d.date)} · trong thư: “{d.quote}”
            </Typography.Text>
          ))}
          <Space wrap size="small">
            {mails.map((m) => (
              // PC's mail is served to `sales.order.prepare` only.
              <GuardedButton
                key={m}
                size="small"
                type="link"
                inlineReason={false}
                reason={viewer.hasScope(PREPARE) ? null : NO_PREPARE}
                onClick={() => setReading(m)}
                aria-label={`Xem thư PC cho dòng ${l.line_no}`}
              >
                Xem thư
              </GuardedButton>
            ))}
            <GuardedButton
              size="small"
              type="primary"
              reason={
                reason ?? (unopened ? "Mở thư PC trước khi bấm Đúng." : null)
              }
              loading={pending === `pc/accept/${l.line_no}`}
              onClick={() => void accept(l)}
              aria-label={`Đúng ngày PC cho dòng ${l.line_no}`}
            >
              Đúng
            </GuardedButton>
            <GuardedButton
              size="small"
              inlineReason={false}
              reason={reason}
              onClick={() => {
                setPrefill(
                  proposed.map((d, index) => ({
                    quantity:
                      l.pc_answer?.deliveries[index]?.quantity ??
                      (proposed.length === 1 ? l.quantity : ""),
                    date: d.date,
                  })),
                );
                setAnswering(l);
              }}
              aria-label={`Sửa ngày PC cho dòng ${l.line_no}`}
            >
              Sửa
            </GuardedButton>
          </Space>
        </Space>
      );
    },
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
            {proposals.length ? (
              <Typography.Text>
                DW1 đã đọc thư PC: bấm Đúng hoặc Sửa từng dòng bên dưới.
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
        {reason === null ? (
          <Typography.Text type="secondary">
            Hoặc soạn và gửi “{label(ARTIFACT_KIND, "pc_request_draft")}” ở mục
            tệp và thư nháp: thư đi rồi DW1 tự ghi đã hỏi PC.
          </Typography.Text>
        ) : null}
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
            ...(proposals.length ? [proposalColumn] : []),
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
          lineNo={answering.line_no}
          quantity={answering.quantity}
          uom={answering.uom}
          initial={
            prefill ??
            (answering.pc_answer
              ? answering.pc_answer.deliveries
              : [
                  {
                    quantity: answering.quantity,
                    date: answering.suggested_delivery_date ?? null,
                  },
                ])
          }
          send={(body, key) =>
            salesApi().recordPcAnswer(
              order.case_id,
              answering.line_no,
              body,
              key,
            )
          }
          onClose={() => {
            setAnswering(null);
            setPrefill(null);
          }}
          onDone={() => {
            setAnswering(null);
            setPrefill(null);
            draft.reload();
            onChanged();
          }}
        />
      ) : null}
      {reading ? (
        <PcMailDialog
          order={order}
          messageId={reading}
          onLoaded={() =>
            setOpened((was) => ({ ...was, [reading]: order.case_version }))
          }
          onClose={() => setReading(null)}
        />
      ) : null}
    </Card>
  );
}

/**
 * PC's mail a proposal was read from (ticket 77), as DW1 read it: opening it
 * records it served to this person at the case's version, which "Đúng" on
 * the line asks for (ui-quality §7).
 */
function PcMailDialog({
  order,
  messageId,
  onLoaded,
  onClose,
}: {
  order: Order;
  messageId: string;
  onLoaded: () => void;
  onClose: () => void;
}) {
  const mail = useResource(
    `sales/orders/${order.case_id}/pc-reply/${messageId}@${order.case_version}`,
    useCallback(
      () => salesApi().pcReplyMail(order.case_id, messageId),
      [order.case_id, messageId],
    ),
  );
  const loaded = mail.data !== undefined && mail.data !== null;
  useEffect(() => {
    if (loaded) onLoaded();
    // Once per load: the parent's callback changes identity every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loaded]);
  return (
    <Modal
      open
      width={640}
      title={mail.data ? `Thư PC: ${mail.data.subject}` : "Thư PC"}
      onCancel={onClose}
      footer={<Button onClick={onClose}>Đóng</Button>}
    >
      {mail.loading ? (
        <RegionState kind="loading" compact />
      ) : mail.error ? (
        <LoadError error={mail.error} onRetry={mail.reload} />
      ) : mail.data ? (
        <Space orientation="vertical" className="w-full">
          <Typography.Text>
            Từ {mail.data.sender} · {formatDateTime(mail.data.received_at)}
          </Typography.Text>
          <Typography.Paragraph className="mb-0! whitespace-pre-wrap">
            {mail.data.text}
          </Typography.Paragraph>
        </Space>
      ) : null}
    </Modal>
  );
}

type DeliveryForm = { quantity?: number | null; date?: PickerDay };
/** PC's answer as the API takes it (`PcAnswerBody`). */
export type PcAnswerBody = {
  case_version: number;
  deliveries: { quantity: string; date: string }[];
};

/**
 * PC's answer for one line: one date, or several splitting the line, whose
 * quantities add up to ``quantity`` (the line's, or in the update loop the
 * quantity the customer asks, ticket 29). The server refuses a split that
 * does not add up; it is never adjusted. Confirmed again, the date PC gave
 * first is kept beside the new one.
 */
export function PcAnswerDialog({
  order,
  lineNo,
  quantity,
  uom,
  initial: given,
  send,
  onClose,
  onDone,
}: {
  order: Order;
  lineNo: number;
  quantity: string;
  uom: string;
  /** What the form opens with: PC's answer so far, or one delivery. */
  initial: { quantity: string; date: string | null }[];
  send: (body: PcAnswerBody, key: string) => Promise<unknown>;
  onClose: () => void;
  onDone: () => void;
}) {
  const [form] = Form.useForm<{ deliveries: DeliveryForm[] }>();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [failed, setFailed] = useState(0);
  const typed = Form.useWatch("deliveries", form) ?? [];
  const total = typed.reduce((sum, d) => sum + Number(d?.quantity ?? 0), 0);
  const whole = Number(quantity);
  const id = `pc/answer/${lineNo}`;
  const initial: DeliveryForm[] = given.map((d) => ({
    quantity: Number(d.quantity),
    date: toPickerDay(d.date),
  }));

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
      (key) => send(body, key),
      `Đã ghi ngày PC cho dòng ${lineNo}`,
    );
    if (result.ok) onDone();
    else setError(result.error);
  };

  return (
    <Modal
      open
      width={640}
      title={`Ngày PC trả lời cho dòng ${lineNo}`}
      okText="Ghi ngày PC"
      cancelText="Huỷ"
      confirmLoading={pending === id}
      onOk={() => form.submit()}
      onCancel={onClose}
    >
      <Typography.Paragraph>
        Dòng {lineNo}: <Quantity value={quantity} uom={uom} />. PC chia dòng
        thành nhiều đợt thì nhập từng đợt; tổng các đợt phải bằng số lượng này.
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
        Tổng các đợt: <Quantity value={total} uom={uom} /> /{" "}
        <Quantity value={quantity} uom={uom} />
        {total !== whole ? " (chưa bằng số lượng của dòng)" : ""}
      </Typography.Paragraph>
      <ActionError error={error} />
    </Modal>
  );
}
