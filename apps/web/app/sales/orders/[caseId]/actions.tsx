"use client";

import { useCallback, useState } from "react";
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
  Tag,
  Typography,
} from "antd";
import { CalendarOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import {
  formatDate,
  formatDateTime,
  fromPickerDay,
  toPickerDay,
} from "../../../../lib/dates";
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
  bravo: "Đã nhập Bravo",
  applyChange: "Đã áp dụng thay đổi trên Bravo",
  crossCheck: "Kiểm chéo đạt",
  returnOrder: "Trả lại",
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

  const prepare = async () =>
    done(
      await run(
        "prepare",
        { v: order.case_version },
        (key) => salesApi().prepare(order.case_id, order.case_version, key),
        "Đã chuẩn bị xong: tệp nhập Bravo sẵn sàng",
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
          <GuardedButton
            key={action}
            type={
              action === "close" || action === "returnOrder"
                ? "default"
                : "primary"
            }
            danger={action === "close"}
            reason={offer.reason}
            loading={pending === action}
            onClick={() =>
              action === "prepare" ? prepare() : setDialog(action)
            }
          >
            {BUTTON[action]}
          </GuardedButton>
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
  const [form] = Form.useForm<{ reason?: string }>();
  const id = decision === "accept" ? "crossCheck" : "returnOrder";
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
          const body = {
            case_version: order.case_version,
            decision,
            reason: values.reason?.trim() || null,
          };
          done(
            await run(
              id,
              body,
              (key) => salesApi().crossCheck(order.case_id, body, key),
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
        ) : (
          <Form.Item
            name="reason"
            label="Lý do trả lại"
            rules={[
              {
                required: true,
                message: "Lý do là bắt buộc",
                validateTrigger: "onSubmit",
              },
            ]}
          >
            <Input.TextArea rows={3} maxLength={500} showCount />
          </Form.Item>
        )}
      </Form>
    </Modal>
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
        Nhập ngày giao Sales xác nhận cho từng dòng. Ngày DW1 gợi ý (ngày nhận
        PO cộng lead time chuẩn) được điền sẵn và vẫn là gợi ý cho tới khi bạn
        ghi.
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
        initialValues={Object.fromEntries(
          order.lines.map((l) => [
            `d${l.line_no}`,
            toPickerDay(l.confirmed_delivery_date ?? l.suggested_delivery_date),
          ]),
        )}
        onFinishFailed={({ errorFields }) => setFailed(errorFields.length)}
        onFinish={async (values) => {
          setFailed(0);
          const body = {
            case_version: order.case_version,
            delivery_dates: order.lines.map((l) => ({
              line_no: l.line_no,
              confirmed_date:
                fromPickerDay(
                  values[`d${l.line_no}`] as Parameters<
                    typeof fromPickerDay
                  >[0],
                ) ?? "",
            })),
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
              render: (_, l) => formatDate(l.requested_date),
            },
            {
              title: "DW1 gợi ý",
              key: "sug",
              render: (_, l) =>
                l.suggested_delivery_date ? (
                  <Tag icon={<CalendarOutlined aria-hidden />}>
                    Gợi ý {formatDate(l.suggested_delivery_date)}
                  </Tag>
                ) : (
                  "Chưa có gợi ý"
                ),
            },
            {
              title: "Ngày xác nhận",
              key: "date",
              render: (_, l) => (
                <Form.Item
                  name={`d${l.line_no}`}
                  className="!mb-0"
                  rules={[{ required: true, message: "Cần ngày xác nhận" }]}
                >
                  <DatePicker
                    format="DD/MM/YYYY"
                    aria-label={`Ngày xác nhận dòng ${l.line_no}`}
                  />
                </Form.Item>
              ),
            },
          ]}
        />
      </Form>
    </Drawer>
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
