"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import {
  Alert,
  Card,
  DatePicker,
  Form,
  Input,
  Modal,
  Segmented,
  Space,
  Table,
  Typography,
} from "antd";
import type { Dayjs } from "dayjs";
import { ApiError, type SalesSchemas } from "@dw/api-client";
import { InfoTip, StatusTag, type StatusTone } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { fromPickerDay, toPickerDay } from "../../../../lib/dates";
import { errorCode } from "../../../../lib/error-message";
import { formatQuantity, parseAmountInput } from "../../../../lib/money";
import { salesApi } from "../../_lib/api";
import { bravoWriteValue } from "../../_lib/bravo-write";
import { ActionError } from "../../_lib/errors";
import {
  BRAVO_WRITE_CHECK,
  BRAVO_WRITE_FIELD,
  BRAVO_WRITE_STATUS,
  label,
} from "../../_lib/labels";
import type { Viewer } from "../../_lib/order-actions";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import { Quantity } from "../../_components/money";
import { GuardedButton } from "../../_components/guarded-button";
import { SCOPE } from "../../_components/sales-frame";

type Order = SalesSchemas["OrderCaseView"];
type Line = Order["lines"][number];
type Write = SalesSchemas["BravoLineWriteView"];
type Field = Write["field"];
type Change = SalesSchemas["BravoWriteBody"]["change"];

/**
 * A cancel's reason as the server takes it (`CANCEL_REASON_CHARS`: Bravo's
 * `CancelRemark`, nvarchar(192); `maxLength` counts UTF-16 units, as SQL
 * Server does), and a quantity's decimals (`QuantityChange`): the test holds
 * both to the contract.
 */
export const CANCEL_REASON_CHARS = 192;
export const QUANTITY_DECIMALS = 4;

export const NO_SCOPE =
  "Bạn không có quyền đề xuất ghi vào Bravo (cần quyền ghi Bravo).";
export const OPEN_PROPOSAL = "Đề xuất trước của dòng này đang chờ duyệt.";

const TONE: Record<Write["status"], StatusTone> = {
  proposed: "warn",
  rejected: "gray",
  written: "ok",
  written_with_differences: "warn",
  refused: "err",
  in_doubt: "unk",
};

/** The line's open proposal, if any: the store refuses a second one. */
export function openFor(writes: readonly Write[], lineNo: number): boolean {
  return writes.some((w) => w.line_no === lineNo && w.status === "proposed");
}

/** Where the gateway stopped a write that did not go through. */
const STOPPED = new Set<Write["status"]>(["refused", "in_doubt"]);

/**
 * A line's latest proposal: its state, what it changes, the approval it
 * opened, and, once the gateway answered, where it stopped and what it said.
 */
function LatestWrite({ write: w }: { write: Write }) {
  const stoppedAt =
    STOPPED.has(w.status) && w.check
      ? `Ở bước: ${label(BRAVO_WRITE_CHECK, w.check)}`
      : null;
  return (
    <Space orientation="vertical" size={0}>
      <Space wrap size={4}>
        <StatusTag tone={TONE[w.status]}>
          {label(BRAVO_WRITE_STATUS, w.status)}
        </StatusTag>
        <span>
          {`${label(BRAVO_WRITE_FIELD, w.field)}: ${bravoWriteValue(w.field, w.before)} → ${bravoWriteValue(w.field, w.after)}`}
        </span>
        <Link href={`/approvals/${w.approval_id}`}>Phiếu duyệt</Link>
      </Space>
      {stoppedAt || w.reason || w.warnings.length > 0 ? (
        <Space wrap size={4}>
          {stoppedAt ? <Typography.Text>{stoppedAt}</Typography.Text> : null}
          {w.reason || w.warnings.length > 0 ? (
            <InfoTip label={`Bravo trả lời về dòng ${w.line_no}`}>
              {w.reason ? <div>Bravo trả lời: {w.reason}</div> : null}
              {w.warnings.length > 0 ? (
                <div>Cảnh báo, khác biệt: {w.warnings.join("; ")}</div>
              ) : null}
            </InfoTip>
          ) : null}
        </Space>
      ) : null}
    </Space>
  );
}

/**
 * "Ghi vào Bravo" (tickets 53, 71): one SO line's confirmed date, quantity
 * or cancel, proposed for Bravo one line at a time. Nothing changes in Bravo
 * before the approver decides, and the write is theirs, under their own
 * Bravo user; the kind's switch stays off until UAT, so for now a decided
 * write settles as "Bravo từ chối". The history is shown to every reader of
 * the case; proposing needs `sales.bravo.write`, which the server checks.
 */
export function BravoWritesPanel({
  order,
  viewer,
  onChanged,
}: {
  order: Order;
  viewer: Viewer;
  onChanged: () => void;
}) {
  if (!order.bravo_so_no) return null;
  return (
    <BravoWrites
      order={order}
      soNo={order.bravo_so_no}
      viewer={viewer}
      onChanged={onChanged}
    />
  );
}

function BravoWrites({
  order,
  soNo,
  viewer,
  onChanged,
}: {
  order: Order;
  soNo: string;
  viewer: Viewer;
  onChanged: () => void;
}) {
  const caseId = order.case_id;
  const writes = useResource(
    `sales/order/${caseId}/bravo-writes`,
    useCallback(() => salesApi().bravoWrites(caseId), [caseId]),
  );
  const [line, setLine] = useState<Line | null>(null);
  const may = viewer.hasScope(SCOPE.bravoWrite);
  const listed = writes.data ?? [];
  const latest = (lineNo: number) => listed.find((w) => w.line_no === lineNo);

  return (
    <Card
      size="small"
      title={`Ghi vào Bravo · SO ${soNo}`}
      extra={
        <InfoTip label="Ghi vào Bravo">
          Đề xuất đổi ngày XN giao hàng, số lượng hoặc hủy một dòng SO. Bravo
          không đổi gì trước khi duyệt; người duyệt ghi dưới user Bravo của
          chính mình. Việc ghi vào Bravo mở sau khi chạy thử UAT: đến lúc đó,
          lần ghi đã duyệt hiện “Bravo từ chối”.
        </InfoTip>
      }
    >
      {writes.error ? (
        <LoadError error={writes.error} onRetry={writes.reload} />
      ) : (
        <Space orientation="vertical" className="w-full">
          {may ? null : (
            <Typography.Text role="note">{NO_SCOPE}</Typography.Text>
          )}
          <Table<Line>
            size="small"
            rowKey="line_no"
            pagination={false}
            loading={!writes.data}
            dataSource={order.lines}
            scroll={{ x: "max-content" }}
            columns={[
              { title: "Dòng", dataIndex: "line_no" },
              { title: "Mã hàng khách", dataIndex: "customer_item_code" },
              {
                title: "Số lượng",
                key: "quantity",
                align: "right",
                render: (_: unknown, l: Line) => (
                  <Quantity value={l.quantity} uom={l.uom} />
                ),
              },
              {
                title: "Đề xuất gần nhất",
                key: "latest",
                render: (_: unknown, l: Line) => {
                  const w = latest(l.line_no);
                  return w ? <LatestWrite write={w} /> : "Chưa có";
                },
              },
              {
                title: "Thao tác",
                key: "action",
                fixed: "right",
                render: (_: unknown, l: Line) => {
                  const open = openFor(listed, l.line_no);
                  return (
                    <GuardedButton
                      reason={!may ? NO_SCOPE : open ? OPEN_PROPOSAL : null}
                      inlineReason={may}
                      aria-label={`Đề xuất ghi dòng ${l.line_no} vào Bravo`}
                      onClick={() => setLine(l)}
                    >
                      Đề xuất…
                    </GuardedButton>
                  );
                },
              },
            ]}
          />
        </Space>
      )}
      {line ? (
        <BravoWriteModal
          order={order}
          line={line}
          onClose={() => setLine(null)}
          onStale={onChanged}
          onDone={() => {
            setLine(null);
            writes.reload();
          }}
        />
      ) : null}
    </Card>
  );
}

interface Values {
  field: Field;
  date: Dayjs | null;
  quantity: string;
  reason: string;
}

/** What a person typed into the quantity field, or null when it is not one. */
export function quantityOf(text: string | undefined): string | null {
  const value = parseAmountInput(text);
  if (value === null || value.startsWith("-") || Number(value) <= 0) {
    return null;
  }
  const decimals = value.split(".")[1]?.length ?? 0;
  return decimals > QUANTITY_DECIMALS ? null : value;
}

function changeOf(values: Values): Change {
  if (values.field === "cancel") {
    return { field: "cancel", reason: values.reason.trim() };
  }
  if (values.field === "quantity") {
    return { field: "quantity", value: quantityOf(values.quantity)! };
  }
  return { field: "confirmed_date", value: fromPickerDay(values.date)! };
}

/** Refused because the case changed since the page read it. */
function isStale(error: unknown): boolean {
  return (
    errorCode(error) === "conflict" &&
    error instanceof ApiError &&
    error.body.details?.rule === "stale_case_version"
  );
}

function BravoWriteModal({
  order,
  line,
  onClose,
  onStale,
  onDone,
}: {
  order: Order;
  line: Line;
  onClose: () => void;
  onStale: () => void;
  onDone: () => void;
}) {
  const [form] = Form.useForm<Values>();
  const field = Form.useWatch("field", form) ?? "confirmed_date";
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [failed, setFailed] = useState(0);
  const id = `bravo/${order.case_id}/${line.line_no}`;

  const submit = async (values: Values) => {
    const body = { case_version: order.case_version, change: changeOf(values) };
    const result = await run(
      id,
      body,
      (key) =>
        salesApi().proposeBravoWrite(order.case_id, line.line_no, body, key),
      "Đã gửi đề xuất ghi vào Bravo, chờ duyệt",
    );
    if (result.ok) {
      onDone();
      return;
    }
    setError(result.error);
    if (isStale(result.error)) onStale();
  };

  return (
    <Modal
      open
      title={`Đề xuất ghi vào Bravo · dòng ${line.line_no}`}
      okText={field === "cancel" ? "Đề xuất hủy dòng" : "Gửi đề xuất"}
      okButtonProps={{ danger: field === "cancel", loading: pending === id }}
      cancelText="Đóng"
      onOk={() => form.submit()}
      onCancel={onClose}
    >
      <Space orientation="vertical" className="w-full">
        {failed ? (
          <Alert type="error" showIcon title={`Còn ${failed} trường cần sửa`} />
        ) : null}
        <Form<Values>
          form={form}
          layout="vertical"
          validateTrigger="onBlur"
          scrollToFirstError={{ focus: true }}
          initialValues={{
            field: "confirmed_date",
            date: toPickerDay(line.confirmed_delivery_date),
            quantity: "",
            reason: "",
          }}
          onFinishFailed={({ errorFields }) => setFailed(errorFields.length)}
          onFinish={(values) => {
            setFailed(0);
            void submit(values);
          }}
        >
          <Form.Item name="field" label="Đổi gì">
            <Segmented<Field>
              options={(Object.keys(BRAVO_WRITE_FIELD) as Field[]).map(
                (value) => ({ value, label: BRAVO_WRITE_FIELD[value] }),
              )}
            />
          </Form.Item>
          {field === "confirmed_date" ? (
            <Form.Item
              name="date"
              label="Ngày XN giao hàng mới"
              rules={[{ required: true, message: "Chọn ngày" }]}
            >
              <DatePicker format="DD/MM/YYYY" />
            </Form.Item>
          ) : field === "quantity" ? (
            <Form.Item
              name="quantity"
              label={`Số lượng mới (${line.uom})`}
              extra={`Hiện tại trên đơn: ${formatQuantity(line.quantity)} ${line.uom}`}
              rules={[
                { required: true, message: "Ghi số lượng" },
                {
                  validator: (_, value: string | undefined) =>
                    !value || quantityOf(value) !== null
                      ? Promise.resolve()
                      : Promise.reject(
                          new Error(
                            "Số lượng phải là số lớn hơn 0, tối đa 4 chữ số thập phân",
                          ),
                        ),
                },
              ]}
            >
              <Input inputMode="decimal" className="max-w-40" />
            </Form.Item>
          ) : (
            <Form.Item
              name="reason"
              label="Lý do hủy"
              extra="Ghi vào Bravo ở cột lý do hủy của dòng."
              rules={[
                { required: true, whitespace: true, message: "Ghi lý do hủy" },
              ]}
            >
              <Input maxLength={CANCEL_REASON_CHARS} showCount />
            </Form.Item>
          )}
        </Form>
        <ActionError error={error} />
      </Space>
    </Modal>
  );
}
