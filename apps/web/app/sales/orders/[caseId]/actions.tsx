"use client";

import { useCallback, useState, type ReactNode } from "react";
import {
  Alert,
  Button,
  Checkbox,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import { StatusTag } from "@dw/ui";
import { suggestedStep } from "../../_components/case-replies";
import { CalendarOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import {
  formatDate,
  formatDateTime,
  fromPickerDay,
  toPickerDay,
} from "../../../../lib/dates";
import { approvalClient } from "../../../../lib/approvals/registry";
import { salesApi } from "../../_lib/api";
import { ActionError, findingKeyLabel } from "../../_lib/errors";
import { CLOSE_REASON, label } from "../../_lib/labels";
import {
  orderOffers,
  type Offer,
  type OrderAction,
  type Viewer,
} from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import { GuardedButton } from "../../_components/guarded-button";
import { Quantity } from "../../_components/money";

type Order = SalesSchemas["OrderCaseView"];
type Dialog =
  | "bravo"
  | "applyChange"
  | "crossCheck"
  | "returnOrder"
  | "confirm"
  | "close"
  | "correction"
  | null;

const DOCUMENT_NO = /^[A-Z0-9][A-Z0-9/-]{1,31}$/;
const DOCUMENT_NO_HELP =
  "Số phiếu gồm chữ in hoa, số, '-' hoặc '/' (2–32 ký tự).";

const BUTTON: Record<OrderAction, string> = {
  prepare: "Chuẩn bị xong",
  correction: "Gửi yêu cầu khách sửa",
  resumeReview: "Khách giữ PO: xem xét lại",
  bravo: "Đã nhập Bravo",
  applyChange: "Đã áp dụng thay đổi trên Bravo",
  crossCheck: "Kiểm chéo đạt",
  returnOrder: "Trả lại",
  resendCrossCheck: "Gửi kiểm chéo lại",
  confirm: "Đã gửi xác nhận",
  close: "Đóng hồ sơ",
};

/**
 * The order's steps for its state, each disabled with its reason in words
 * where it cannot be taken now (the reason is also written beside the
 * button). Every press sends the case version it was made on and an
 * idempotency key; the screen reads the case again after the server answers.
 */
export function OrderActions({
  order,
  viewer,
  sourceOpened,
  onChanged,
}: {
  order: Order;
  viewer: Viewer;
  sourceOpened: boolean;
  onChanged: () => void;
}) {
  const offers = orderOffers(order, viewer, { sourceOpened });
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const entries = Object.entries(offers) as [OrderAction, Offer][];

  const done = (result: { ok: boolean; error?: unknown }) => {
    if (result.ok) {
      setError(null);
      setDialog(null);
      onChanged();
    } else setError(result.error);
    return result.ok;
  };

  // The step the newest reply in the case's thread proposes (ticket 32):
  // marked, never pressed for Sales.
  const suggested =
    suggestedStep(order.replies) === "resume_review" ? "resumeReview" : null;

  const resumeReview = async () =>
    done(
      await run(
        "resumeReview",
        { v: order.case_version },
        (key) =>
          salesApi().resumeReview(order.case_id, order.case_version, key),
        "Đã mở lại xem xét: quyết lại từng cờ đã gửi khách",
      ),
    );

  const prepare = async () =>
    done(
      await run(
        "prepare",
        { v: order.case_version },
        (key) => salesApi().prepare(order.case_id, order.case_version, key),
        "Đã chuẩn bị xong: tệp nhập Bravo sẵn sàng",
      ),
    );

  const resendCrossCheck = async () =>
    done(
      await run(
        "resendCrossCheck",
        { v: order.case_version },
        (key) =>
          salesApi().resendCrossCheck(order.case_id, order.case_version, key),
        "Đã gửi kiểm chéo lại: yêu cầu kiểm chéo mới đang chờ",
      ),
    );

  if (entries.length === 0)
    return (
      <Typography.Text>
        Không có bước nào của Sales ở trạng thái này.
      </Typography.Text>
    );

  return (
    <div className="space-y-3">
      <Space wrap align="start" size="middle">
        {entries.map(([action, offer]) => (
          <Space key={action} size="small" align="center">
            <GuardedButton
              type={
                action === "close" || action === "returnOrder"
                  ? "default"
                  : "primary"
              }
              danger={action === "close"}
              reason={offer.reason}
              loading={pending === action}
              onClick={() =>
                action === "prepare"
                  ? prepare()
                  : action === "resendCrossCheck"
                    ? resendCrossCheck()
                    : action === "resumeReview"
                      ? resumeReview()
                      : setDialog(action as Dialog)
              }
            >
              {BUTTON[action]}
            </GuardedButton>
            {suggested === action ? (
              <StatusTag tone="warn">Đề xuất từ thư khách</StatusTag>
            ) : null}
          </Space>
        ))}
      </Space>
      <ActionError error={error} />

      <CorrectionDialog
        open={dialog === "correction"}
        order={order}
        onClose={() => setDialog(null)}
        run={run}
        done={done}
        pending={pending}
      />
      <BravoDialog
        open={dialog === "bravo" || dialog === "applyChange"}
        change={dialog === "applyChange"}
        order={order}
        onClose={() => setDialog(null)}
        run={run}
        done={done}
        pending={pending}
      />
      <CrossCheckDialog
        open={dialog === "crossCheck" || dialog === "returnOrder"}
        decision={dialog === "returnOrder" ? "return" : "accept"}
        order={order}
        onClose={() => setDialog(null)}
        run={run}
        done={done}
        pending={pending}
      />
      <ConfirmDrawer
        open={dialog === "confirm"}
        order={order}
        onClose={() => setDialog(null)}
        run={run}
        done={done}
        pending={pending}
      />
      <CloseDialog
        open={dialog === "close"}
        order={order}
        onClose={() => setDialog(null)}
        run={run}
        done={done}
        pending={pending}
      />
    </div>
  );
}

type Run = ReturnType<typeof useAction>["run"];
interface DialogProps {
  open: boolean;
  order: Order;
  onClose: () => void;
  run: Run;
  done: (result: { ok: boolean; error?: unknown }) => boolean;
  pending: string | null;
}

function CorrectionDialog({
  open,
  order,
  onClose,
  run,
  done,
  pending,
}: DialogProps) {
  const asked = order.findings.filter(
    (f) => f.disposition.kind === "ask_customer",
  );
  return (
    <Modal
      open={open}
      title="Gửi yêu cầu khách sửa PO"
      okText="Gửi yêu cầu sửa"
      cancelText="Hủy"
      okButtonProps={{ loading: pending === "correction" }}
      onCancel={onClose}
      onOk={async () =>
        done(
          await run(
            "correction",
            { v: order.case_version },
            (key) =>
              salesApi().requestCorrection(
                order.case_id,
                order.case_version,
                key,
              ),
            "Đơn chuyển sang chờ khách sửa PO",
          ),
        )
      }
      destroyOnHidden
    >
      <Typography.Paragraph>
        DW1 soạn thư yêu cầu sửa, liệt kê đúng {asked.length} cờ dưới đây. Đơn
        chờ bản sửa của khách; bản sửa vào cùng hồ sơ và mọi kiểm tra chạy lại.
      </Typography.Paragraph>
      <ul>
        {asked.map((f) => (
          <li key={f.key}>{findingKeyLabel(f.key)}</li>
        ))}
      </ul>
    </Modal>
  );
}

function BravoDialog({
  open,
  change,
  order,
  onClose,
  run,
  done,
  pending,
}: DialogProps & { change: boolean }) {
  const [form] = Form.useForm<{ so_no?: string; compared: boolean }>();
  const id = change ? "applyChange" : "bravo";
  return (
    <Modal
      open={open}
      title={change ? "Đã áp dụng thay đổi PO trên Bravo" : "Ghi số đơn Bravo"}
      okText={change ? "Ghi đã áp dụng" : "Ghi số đơn Bravo"}
      cancelText="Hủy"
      okButtonProps={{ loading: pending === id }}
      onCancel={onClose}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        initialValues={{ compared: false }}
        onFinish={async (values) => {
          const body = {
            case_version: order.case_version,
            so_no: change ? null : (values.so_no?.trim() ?? null),
            entry_compared: values.compared,
          };
          done(
            await run(
              id,
              body,
              (key) => salesApi().bravoEntry(order.case_id, body, key),
              change ? "Đã ghi thay đổi trên Bravo" : "Đã ghi số đơn Bravo",
            ),
          );
        }}
      >
        {change ? (
          <Typography.Paragraph>
            Bản sửa của PO đã được áp dụng vào đơn {order.bravo_so_no ?? ""}{" "}
            trên Bravo. Đơn sẽ được kiểm chéo lại.
          </Typography.Paragraph>
        ) : (
          <Form.Item
            name="so_no"
            label="Số đơn bán hàng trên Bravo"
            rules={[
              {
                required: true,
                message: "Số đơn là bắt buộc",
                validateTrigger: "onSubmit",
              },
              { pattern: DOCUMENT_NO, message: DOCUMENT_NO_HELP },
            ]}
          >
            <Input maxLength={32} autoComplete="off" />
          </Form.Item>
        )}
        <Form.Item
          name="compared"
          valuePropName="checked"
          rules={[
            {
              validator: (_, value) =>
                value
                  ? Promise.resolve()
                  : Promise.reject(
                      new Error("Cần xác nhận đã đối chiếu với PO"),
                    ),
              validateTrigger: "onSubmit",
            },
          ]}
        >
          <Checkbox>
            Tôi đã đối chiếu các dòng đơn trên Bravo với PO (WIV-03-012 bước 7).
          </Checkbox>
        </Form.Item>
      </Form>
    </Modal>
  );
}

/**
 * The cross-check (WIV-03-012 step 9) is decided on the platform approval
 * DW1's run paused on when the Bravo entry was recorded: approve is "đạt",
 * reject is "trả lại". Either way the server wants a written comment (the
 * approval is strict) and the case version the checker was shown.
 */
function CrossCheckDialog({
  open,
  decision,
  order,
  onClose,
  run,
  done,
  pending,
}: DialogProps & { decision: "accept" | "return" }) {
  const name = usePeople();
  const [form] = Form.useForm<{ comment?: string }>();
  const id = decision === "accept" ? "crossCheck" : "returnOrder";
  const waiting = order.decision;
  return (
    <Modal
      open={open}
      title={
        decision === "accept" ? "Kiểm chéo đạt" : "Trả lại cho người chuẩn bị"
      }
      okText={decision === "accept" ? "Ghi kiểm chéo đạt" : "Trả lại"}
      cancelText="Hủy"
      okButtonProps={{ loading: pending === id, danger: decision === "return" }}
      onCancel={onClose}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      <Descriptions
        size="small"
        column={1}
        items={[
          {
            key: "po",
            label: "PO",
            children: `${order.po_no}${order.revision ? ` · Rev.${order.revision}` : ""}`,
          },
          {
            key: "so",
            label: "Số đơn Bravo",
            children: order.bravo_so_no ?? "Chưa có",
          },
          {
            key: "prep",
            label: "Người chuẩn bị",
            children: name(order.prepared_by),
          },
          {
            key: "rec",
            label: "Người nhập Bravo",
            children: name(order.bravo_recorded_by),
          },
          {
            key: "version",
            label: "Phiên bản hồ sơ",
            children: order.case_version,
          },
        ]}
      />
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        onFinish={async (values) => {
          if (!waiting) return;
          const body = {
            approve: decision === "accept",
            comment: values.comment?.trim() ?? "",
            subject_version: order.case_version,
          };
          done(
            await run(
              id,
              body,
              (key) =>
                approvalClient(waiting.approval_type).decideApproval(
                  waiting.approval_id,
                  body,
                  key,
                ),
              decision === "accept" ? "Đã ghi kiểm chéo đạt" : "Đã trả lại đơn",
            ),
          );
        }}
      >
        {decision === "accept" ? (
          <Typography.Paragraph>
            Bạn đã đối chiếu đơn trên Bravo với PO và với các quyết định trên hồ
            sơ này (WIV-03-012 bước 9).
          </Typography.Paragraph>
        ) : null}
        <Form.Item
          name="comment"
          label={decision === "accept" ? "Ghi chú kiểm chéo" : "Lý do trả lại"}
          rules={[
            {
              required: true,
              whitespace: true,
              message:
                decision === "accept"
                  ? "Ghi chú là bắt buộc: bạn đã đối chiếu những gì"
                  : "Lý do là bắt buộc",
              validateTrigger: "onSubmit",
            },
          ]}
        >
          <Input.TextArea rows={3} maxLength={500} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}

type OrderLine = Order["lines"][number];
type PickerDay = Parameters<typeof fromPickerDay>[0];

/** The form field of one confirmed date: a line's, or one schedule's of a
 * line the PO splits (ticket 35). */
function dateField(line: OrderLine, schedule?: number): string {
  return schedule === undefined
    ? `d${line.line_no}`
    : `d${line.line_no}_${schedule}`;
}

/** The lines a submitted form still lacks a date for. */
function linesWithout(names: (string | number)[][]): number {
  return new Set(names.map((name) => String(name[0]).split("_")[0])).size;
}

/** One cell per line, or a value per schedule of a split line. */
function perSchedule(
  line: OrderLine,
  each: (s: OrderLine["schedules"][number], index: number) => ReactNode,
  whole: () => ReactNode,
): ReactNode {
  if (!line.printed_schedules) return whole();
  return (
    <Space orientation="vertical" size={4}>
      {line.schedules.map((s, index) => (
        <span key={`${index}:${s.requested_date}`}>{each(s, index)}</span>
      ))}
    </Space>
  );
}

function ConfirmDrawer({
  open,
  order,
  onClose,
  run,
  done,
  pending,
}: DialogProps) {
  const [form] = Form.useForm<Record<string, unknown>>();
  const [failed, setFailed] = useState(0);
  const initial: Record<string, unknown> = {};
  for (const l of order.lines) {
    if (l.printed_schedules) {
      l.schedules.forEach((s, index) => {
        initial[dateField(l, index)] = toPickerDay(
          s.confirmed_delivery_date ?? s.suggested_delivery_date,
        );
      });
    } else {
      initial[dateField(l)] = toPickerDay(
        l.confirmed_delivery_date ?? l.suggested_delivery_date,
      );
    }
  }
  const picker = (name: string, ariaLabel: string) => (
    <Form.Item
      name={name}
      className="!mb-0"
      rules={[{ required: true, message: "Cần ngày xác nhận" }]}
    >
      <DatePicker format="DD/MM/YYYY" aria-label={ariaLabel} />
    </Form.Item>
  );
  return (
    <Drawer
      open={open}
      onClose={onClose}
      size="min(720px, 100vw)"
      title="Xác nhận đơn với khách"
      destroyOnHidden
      footer={
        <Space>
          <Button
            type="primary"
            loading={pending === "confirm"}
            onClick={() => form.submit()}
          >
            Ghi đã gửi xác nhận
          </Button>
          <Button onClick={onClose}>Hủy</Button>
        </Space>
      }
    >
      <Typography.Paragraph>
        Nhập ngày giao Sales xác nhận cho từng dòng; dòng PO chia nhiều đợt giao
        được xác nhận từng đợt. Ngày DW1 gợi ý (ngày nhận PO cộng lead time
        chuẩn) được điền sẵn và vẫn là gợi ý cho tới khi bạn ghi.
      </Typography.Paragraph>
      {failed ? (
        <Alert
          type="error"
          showIcon
          title={`Còn ${failed} dòng chưa có ngày xác nhận.`}
        />
      ) : null}
      <Form
        form={form}
        layout="vertical"
        scrollToFirstError={{ focus: true }}
        initialValues={initial}
        onFinishFailed={({ errorFields }) =>
          setFailed(linesWithout(errorFields.map((f) => f.name)))
        }
        onFinish={async (values) => {
          setFailed(0);
          const day = (name: string) =>
            fromPickerDay(values[name] as PickerDay) ?? "";
          const body = {
            case_version: order.case_version,
            delivery_dates: order.lines.map((l) =>
              l.printed_schedules
                ? {
                    line_no: l.line_no,
                    schedule_dates: l.schedules.map((_, index) =>
                      day(dateField(l, index)),
                    ),
                  }
                : { line_no: l.line_no, confirmed_date: day(dateField(l)) },
            ),
          };
          done(
            await run(
              "confirm",
              body,
              (key) => salesApi().confirm(order.case_id, body, key),
              "Đã ghi xác nhận đơn",
            ),
          );
        }}
      >
        <Table
          size="small"
          rowKey="line_no"
          pagination={false}
          dataSource={order.lines}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Dòng", dataIndex: "line_no" },
            {
              title: "Mã PRV",
              key: "prv",
              render: (_, l) => l.mapping.prv_code ?? "Chưa có",
            },
            {
              title: "Ngày yêu cầu",
              key: "req",
              render: (_, l) =>
                perSchedule(
                  l,
                  (s) => (
                    <>
                      {formatDate(s.requested_date)} ·{" "}
                      <Quantity value={s.quantity} uom={l.uom} />
                    </>
                  ),
                  () => formatDate(l.requested_date),
                ),
            },
            {
              title: "DW1 gợi ý",
              key: "sug",
              render: (_, l) =>
                perSchedule(
                  l,
                  (s) =>
                    s.suggested_delivery_date ? (
                      <SuggestedTag day={s.suggested_delivery_date} />
                    ) : (
                      "Chưa có gợi ý"
                    ),
                  () =>
                    l.suggested_delivery_date ? (
                      <SuggestedTag day={l.suggested_delivery_date} />
                    ) : (
                      "Chưa có gợi ý"
                    ),
                ),
            },
            {
              title: "Ngày xác nhận",
              key: "date",
              render: (_, l) =>
                perSchedule(
                  l,
                  (_s, index) =>
                    picker(
                      dateField(l, index),
                      `Ngày xác nhận dòng ${l.line_no} đợt ${index + 1}`,
                    ),
                  () => picker(dateField(l), `Ngày xác nhận dòng ${l.line_no}`),
                ),
            },
          ]}
        />
      </Form>
    </Drawer>
  );
}

function SuggestedTag({ day }: { day: string }) {
  return (
    <StatusTag tone="gray" icon={<CalendarOutlined aria-hidden />}>
      Gợi ý {formatDate(day)}
    </StatusTag>
  );
}

function CloseDialog({
  open,
  order,
  onClose,
  run,
  done,
  pending,
}: DialogProps) {
  const [form] = Form.useForm<{ reason?: string; superseded_by?: string }>();
  const reason = Form.useWatch("reason", form);
  const others = useResource(
    "sales/orders",
    useCallback(() => salesApi().orders(), []),
    { enabled: open },
  );
  const duplicate = order.findings.some((f) => f.code === "duplicate_po");
  const reasons = Object.entries(CLOSE_REASON).filter(([key]) =>
    duplicate ? key === "duplicate" : key !== "duplicate",
  );
  const successors = (others.data ?? []).filter(
    (o) =>
      o.case_id !== order.case_id && o.customer_code === order.customer_code,
  );
  return (
    <Modal
      open={open}
      title={`Đóng hồ sơ PO ${order.po_no}`}
      okText="Đóng hồ sơ"
      cancelText="Hủy"
      okButtonProps={{ danger: true, loading: pending === "close" }}
      onCancel={onClose}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      <Typography.Paragraph>
        Hồ sơ đã đóng không mở lại được và không bao giờ bị xóa. Đơn chưa vào
        Bravo mới đóng được.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        initialValues={{ reason: duplicate ? "duplicate" : undefined }}
        onFinish={async (values) => {
          const body = {
            case_version: order.case_version,
            reason: values.reason as keyof typeof CLOSE_REASON,
            superseded_by:
              values.reason === "superseded"
                ? (values.superseded_by ?? null)
                : null,
          };
          done(
            await run(
              "close",
              body,
              (key) => salesApi().close(order.case_id, body, key),
              "Đã đóng hồ sơ",
            ),
          );
        }}
      >
        <Form.Item
          name="reason"
          label="Lý do"
          rules={[
            {
              required: true,
              message: "Lý do là bắt buộc",
              validateTrigger: "onSubmit",
            },
          ]}
        >
          <Select
            options={reasons.map(([value, text]) => ({ value, label: text }))}
          />
        </Form.Item>
        {reason === "superseded" ? (
          <Form.Item
            name="superseded_by"
            label="Hồ sơ thay thế"
            rules={[
              {
                required: true,
                message: "Cần chọn hồ sơ thay thế",
                validateTrigger: "onSubmit",
              },
            ]}
          >
            <Select
              loading={others.loading}
              options={successors.map((o) => ({
                value: o.case_id,
                label: `PO ${o.po_no}${o.revision ? ` · Rev.${o.revision}` : ""} · ${formatDateTime(o.received_at)}`,
              }))}
            />
          </Form.Item>
        ) : null}
        {reason === "cannot_supply" ? (
          <Typography.Paragraph>
            DW1 soạn thư báo không cung cấp được; bạn gửi thư đó cho khách.
          </Typography.Paragraph>
        ) : null}
        {reason ? (
          <Typography.Text>
            Lý do: {label(CLOSE_REASON, reason)}
          </Typography.Text>
        ) : null}
      </Form>
    </Modal>
  );
}
