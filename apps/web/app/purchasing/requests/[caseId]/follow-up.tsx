"use client";

import { useCallback, useState } from "react";
import {
  Alert,
  App,
  Button,
  DatePicker,
  Flex,
  Form,
  Input,
  Select,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { CheckOutlined, MailOutlined, PlusOutlined } from "@ant-design/icons";
import type {
  PurchaseCase,
  PurchaseConfirmationMail,
  PurchasingSchemas,
} from "@dw/api-client";
import { InfoTip } from "@dw/ui";
import {
  formatDate,
  formatDateTime,
  fromPickerDay,
} from "../../../../lib/dates";
import { errorMessage } from "../../../../lib/error-message";
import { useIdempotencyKeys } from "../../../../lib/idempotency";
import { formatQuantity, parseAmountInput } from "../../../../lib/money";
import { useAuth } from "../../../../lib/auth/auth-context";
import { useCachedResource } from "../../../../lib/use-cached-resource";
import { purchasingApi } from "../../_lib/api";
import { money } from "../../_lib/format";
import { DIFFERENCE } from "../../_lib/labels";
import { SCOPE } from "../../_lib/scopes";

type Order = PurchasingSchemas["PoDraft"];
type Tracking = PurchasingSchemas["OrderTracking"];
type Difference = PurchasingSchemas["Difference"];

/**
 * The mails that confirm one of the case's orders, read once per case
 * version: which order a mail is about is the server's (code matches the
 * verified supplier and the order's number), never the page's guess.
 */
export function useConfirmationMails(c: PurchaseCase) {
  const { hasScope } = useAuth();
  return useCachedResource<PurchaseConfirmationMail[]>(
    `purchasing/confirmations/${c.case_id}/${c.case_version}`,
    useCallback(
      () =>
        hasScope(SCOPE.po)
          ? purchasingApi().confirmationMails(c.case_id)
          : Promise.resolve([]),
      [c.case_id, hasScope],
    ),
  );
}

/**
 * After an order is drafted (DW02 function 5): the number Bravo gave it,
 * the supplier's confirmation held to it line by line, and what arrived.
 * Every action is the buyer's and the server's to refuse; a disabled button
 * says why.
 */
export function OrderFollowUp({
  c,
  order,
  mails,
  onChanged,
}: {
  c: PurchaseCase;
  order: Order;
  mails: PurchaseConfirmationMail[];
  onChanged: () => void;
}) {
  const { hasScope } = useAuth();
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [pending, setPending] = useState<string | null>(null);
  const [refused, setRefused] = useState<string | null>(null);
  const [bravoNo, setBravoNo] = useState("");
  const tracking: Tracking | undefined = c.tracking?.find(
    (t) => t.po_ref === order.po_ref,
  );
  const why = hasScope(SCOPE.po)
    ? null
    : "Vai của bạn không gồm việc theo dõi đơn đặt hàng.";

  async function act(
    id: string,
    payload: unknown,
    run: (key: string) => Promise<unknown>,
    done: string,
  ) {
    const action = `${id}:${order.po_ref}:${c.case_id}:${c.case_version}`;
    setPending(id);
    setRefused(null);
    try {
      await run(keys.keyFor(action, payload));
      keys.settle(action);
      message.success(done);
      onChanged();
    } catch (error) {
      setRefused(errorMessage(error));
      onChanged();
    } finally {
      setPending(null);
    }
  }

  const api = purchasingApi();
  const confirmation = tracking?.confirmation ?? null;
  const mine = mails.filter((m) => m.po_ref === order.po_ref);

  return (
    <Flex vertical gap={8}>
      <Flex gap={8} align="center" wrap>
        <Typography.Text>Số PO Bravo:</Typography.Text>
        {tracking?.bravo_no ? (
          <Typography.Text strong copyable>
            {tracking.bravo_no}
          </Typography.Text>
        ) : (
          <>
            <Input
              aria-label={`Số PO Bravo của ${order.po_ref}`}
              className="max-w-48"
              placeholder="PO-26110007"
              value={bravoNo}
              disabled={why !== null}
              onChange={(e) => setBravoNo(e.target.value.trim())}
            />
            <Tooltip
              title={why ?? (bravoNo ? null : "Nhập số PO Bravo đã cấp")}
            >
              <Button
                loading={pending === "bravo"}
                disabled={why !== null || !bravoNo}
                onClick={() =>
                  void act(
                    "bravo",
                    bravoNo,
                    (key) =>
                      api.recordBravoNo(
                        c.case_id,
                        order.po_ref,
                        bravoNo,
                        c.case_version,
                        key,
                      ),
                    "Đã lưu số PO Bravo.",
                  )
                }
              >
                Lưu số PO Bravo
              </Button>
            </Tooltip>
            <InfoTip label="Vì sao phải ghi số PO Bravo">
              Bravo không nối với DW2: sau khi nhập file vào Bravo, ghi số PO
              Bravo cấp để DW2 nhận ra thư xác nhận của nhà cung cấp.
            </InfoTip>
          </>
        )}
      </Flex>

      <Flex gap={8} align="center" wrap>
        <Typography.Text>Xác nhận của nhà cung cấp:</Typography.Text>
        <ConfirmationTag tracking={tracking} />
        {confirmation && !confirmation.accepted_by ? (
          <Tooltip title={why}>
            <Button
              icon={<CheckOutlined aria-hidden />}
              loading={pending === "accept"}
              disabled={why !== null}
              onClick={() =>
                void act(
                  "accept",
                  null,
                  (key) =>
                    api.acceptConfirmation(
                      c.case_id,
                      order.po_ref,
                      c.case_version,
                      key,
                    ),
                  "Đã chấp nhận xác nhận.",
                )
              }
            >
              {confirmation.differences.length
                ? "Chấp nhận với chỗ khác"
                : "Chấp nhận"}
            </Button>
          </Tooltip>
        ) : null}
      </Flex>
      {confirmation?.differences.length ? (
        <Alert
          type="warning"
          showIcon
          title={`Nhà cung cấp xác nhận khác đơn ở ${confirmation.differences.length} chỗ`}
          description={
            <ul className="m-0 pl-4">
              {confirmation.differences.map((d) => (
                <li key={`${d.line_no}-${d.field}`}>
                  {differenceText(d, order)}
                </li>
              ))}
            </ul>
          }
        />
      ) : null}
      {mine.map((mail) => (
        <Flex key={mail.message_id} gap={8} align="center" wrap>
          <MailOutlined aria-hidden />
          <Typography.Text>
            {mail.sender} · {mail.subject} · {formatDateTime(mail.received_at)}
          </Typography.Text>
          <Tooltip title={why}>
            <Button
              loading={pending === mail.message_id}
              disabled={why !== null}
              onClick={() =>
                void act(
                  mail.message_id,
                  null,
                  (key) =>
                    api.readConfirmation(
                      c.case_id,
                      mail.message_id,
                      c.case_version,
                      key,
                    ),
                  "DW2 đã đọc thư xác nhận.",
                )
              }
            >
              DW2 đọc xác nhận
            </Button>
          </Tooltip>
        </Flex>
      ))}

      <Receipts
        order={order}
        tracking={tracking}
        why={why}
        pending={pending}
        onRecord={(line_no, quantity, received_on) =>
          void act(
            "receipt",
            { line_no, quantity, received_on },
            (key) =>
              api.recordReceipt(
                c.case_id,
                order.po_ref,
                { line_no, quantity, received_on },
                c.case_version,
                key,
              ),
            "Đã ghi nhận hàng.",
          )
        }
      />
      {refused ? <Alert type="error" showIcon title={refused} /> : null}
    </Flex>
  );
}

function ConfirmationTag({ tracking }: { tracking: Tracking | undefined }) {
  const confirmation = tracking?.confirmation;
  if (!confirmation) return <Tag>Chưa có</Tag>;
  if (confirmation.accepted_by)
    return (
      <Tag color="success">
        Đã chấp nhận
        {confirmation.differences.length ? " (có chỗ khác đơn)" : ""}
      </Tag>
    );
  return confirmation.differences.length ? (
    <Tag color="warning">Máy đọc · khác đơn, chờ người mua</Tag>
  ) : (
    <Tag color="processing">Máy đọc · khớp đơn, chờ người mua</Tag>
  );
}

function differenceText(d: Difference, order: Order): string {
  const line = order.lines.find((l) => l.line_no === d.line_no);
  const name = line
    ? `Dòng ${d.line_no} (${line.description})`
    : `Dòng ${d.line_no}`;
  const shown = (value: string | null | undefined) => {
    if (value == null) return "không nêu";
    if (d.field === "delivery_on") return formatDate(value);
    if (d.field === "unit_price") return money(value, order.currency);
    return formatQuantity(value);
  };
  if (d.field === "missing")
    return `${name}: nhà cung cấp không xác nhận dòng này`;
  if (d.field === "not_ordered")
    return `Dòng ${d.line_no}: nhà cung cấp xác nhận một dòng đơn không có`;
  return `${name}: ${DIFFERENCE[d.field]} đặt ${shown(d.ordered)}, xác nhận ${shown(d.confirmed)}`;
}

type ReceiptFields = {
  line_no: number;
  quantity: string;
  received_on?: import("dayjs").Dayjs | null;
};

function Receipts({
  order,
  tracking,
  why,
  pending,
  onRecord,
}: {
  order: Order;
  tracking: Tracking | undefined;
  why: string | null;
  pending: string | null;
  onRecord: (line_no: number, quantity: string, received_on: string) => void;
}) {
  const [form] = Form.useForm<ReceiptFields>();
  const arrived = (lineNo: number) =>
    (tracking?.receipts ?? [])
      .filter((r) => r.line_no === lineNo)
      .reduce((sum, r) => sum + Number(r.quantity), 0);
  return (
    <Flex vertical gap={4}>
      <Typography.Text>
        Đã nhận:{" "}
        {order.lines
          .map(
            (l) =>
              `dòng ${l.line_no} ${formatQuantity(String(arrived(l.line_no)))}/${formatQuantity(l.quantity)} ${l.unit}`,
          )
          .join(" · ")}
      </Typography.Text>
      <Form<ReceiptFields>
        form={form}
        layout="inline"
        validateTrigger="onBlur"
        disabled={why !== null}
        onFinish={(fields) => {
          const on = fromPickerDay(fields.received_on);
          const quantity = parseAmountInput(fields.quantity);
          if (on && quantity !== null)
            onRecord(fields.line_no, String(quantity), on);
        }}
      >
        <Form.Item
          name="line_no"
          label="Dòng"
          rules={[{ required: true, message: "Chọn dòng" }]}
        >
          <Select
            className="min-w-32"
            options={order.lines.map((l) => ({
              value: l.line_no,
              label: `${l.line_no} · ${l.description}`,
            }))}
          />
        </Form.Item>
        <Form.Item
          name="quantity"
          label="Số lượng"
          rules={[
            { required: true, message: "Ghi số lượng" },
            {
              validator: (_, value: string | undefined) =>
                !value || parseAmountInput(value) !== null
                  ? Promise.resolve()
                  : Promise.reject(new Error("Số lượng phải là một số")),
            },
          ]}
        >
          <Input inputMode="decimal" className="max-w-28" />
        </Form.Item>
        <Form.Item
          name="received_on"
          label="Ngày nhận"
          rules={[{ required: true, message: "Chọn ngày nhận" }]}
        >
          <DatePicker format="DD/MM/YYYY" />
        </Form.Item>
        <Tooltip title={why}>
          <Button
            htmlType="submit"
            icon={<PlusOutlined aria-hidden />}
            loading={pending === "receipt"}
            disabled={why !== null}
          >
            Ghi nhận hàng
          </Button>
        </Tooltip>
      </Form>
    </Flex>
  );
}
