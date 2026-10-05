"use client";

import { useState } from "react";
import {
  Card,
  DatePicker,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { formatDateTime, fromPickerDay } from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { DECLINE_REASON, FINDING_CODE, label } from "../../_lib/labels";
import type { Offer, Viewer } from "../../_lib/order-actions";
import { usePeople } from "../../_lib/people";
import { quoteOffers, type QuoteAction } from "../../_lib/quote-actions";
import { useAction } from "../../_lib/use-action";
import { AmountInput } from "../../_components/amount-input";
import { GuardedButton } from "../../_components/guarded-button";

type Quote = SalesSchemas["QuoteCaseView"];
type Finding = SalesSchemas["QuoteFindingView"];

const DOCUMENT_NO = /^[A-Z0-9][A-Z0-9/-]{1,31}$/;
const DOCUMENT_NO_HELP =
  "Số phiếu gồm chữ in hoa, số, '-' hoặc '/' (2–32 ký tự).";
const CUSTOMER_CODE = /^[A-Z][A-Z0-9]{1,15}$/;

/** The buttons this section draws; approve, return and price have their own panels. */
const BUTTON: Partial<Record<QuoteAction, string>> = {
  draftYcbg: "Soạn YCBG",
  recordYcbg: "Đã lập YCBG",
  designSent: "Gửi Design",
  specStart: "Gửi KH thảo luận spec",
  specSettle: "Khách đã đồng ý spec",
  specAskDesign: "Hỏi lại Design",
  submit: "Trình duyệt",
  sent: "Đã gửi KH",
  masterList: "Xác nhận master list",
  decline: "Từ chối báo giá",
};

type Dialog = "recordYcbg" | "submit" | "decline" | null;

export function QuoteActions({
  quote,
  viewer,
  onDone,
}: {
  quote: Quote;
  viewer: Viewer;
  onDone: () => void;
}) {
  const offers = quoteOffers(quote, viewer);
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const shown = (Object.entries(offers) as [QuoteAction, Offer][]).filter(
    ([action]) => BUTTON[action],
  );
  const v = quote.case_version;

  const finish = (result: { ok: boolean; error?: unknown }) => {
    if (result.ok) {
      setError(null);
      setDialog(null);
      onDone();
    } else setError(result.error);
  };

  const direct: Partial<Record<QuoteAction, () => Promise<void>>> = {
    draftYcbg: async () =>
      finish(
        await run(
          "draftYcbg",
          { v },
          (key) => salesApi().ycbg(quote.case_id, { case_version: v }, key),
          "DW1 đã soạn YCBG",
        ),
      ),
    designSent: async () =>
      finish(
        await run(
          "designSent",
          { v },
          (key) => salesApi().designSent(quote.case_id, v, key),
          "Đã ghi gửi Design",
        ),
      ),
    specStart: async () =>
      finish(
        await run(
          "specStart",
          { v },
          (key) =>
            salesApi().specDiscussion(
              quote.case_id,
              { case_version: v, step: "start" },
              key,
            ),
          "Đã chuyển sang thảo luận spec với khách",
        ),
      ),
    specSettle: async () =>
      finish(
        await run(
          "specSettle",
          { v },
          (key) =>
            salesApi().specDiscussion(
              quote.case_id,
              { case_version: v, step: "settle" },
              key,
            ),
          "Đã ghi khách đồng ý spec",
        ),
      ),
    specAskDesign: async () =>
      finish(
        await run(
          "specAskDesign",
          { v },
          (key) =>
            salesApi().specDiscussion(
              quote.case_id,
              { case_version: v, step: "ask_design_again" },
              key,
            ),
          "Đã chuyển lại cho Design",
        ),
      ),
    sent: async () =>
      finish(
        await run(
          "sent",
          { v },
          (key) => salesApi().sent(quote.case_id, v, key),
          "Đã ghi gửi báo giá cho khách",
        ),
      ),
    masterList: async () =>
      finish(
        await run(
          "masterList",
          { v },
          (key) => salesApi().masterList(quote.case_id, v, key),
          "Đã xác nhận dòng master list",
        ),
      ),
  };

  return (
    <div className="space-y-3">
      <IntakeFindings quote={quote} viewer={viewer} onDone={onDone} />
      {shown.length ? (
        <Space wrap align="start" size="middle">
          {shown.map(([action, offer]) => (
            <GuardedButton
              key={action}
              type={action === "decline" ? "default" : "primary"}
              danger={action === "decline"}
              reason={offer.reason}
              loading={pending === action}
              onClick={() =>
                direct[action] ? direct[action]!() : setDialog(action as Dialog)
              }
            >
              {BUTTON[action]}
            </GuardedButton>
          ))}
        </Space>
      ) : null}
      <ActionError error={error} />
      <NumberDialog
        open={dialog === "recordYcbg"}
        title="Ghi số YCBG Bravo đã cấp"
        field="Số YCBG trên Bravo"
        ok="Ghi số YCBG"
        loading={pending === "recordYcbg"}
        onCancel={() => setDialog(null)}
        onSubmit={async (no) =>
          finish(
            await run(
              "recordYcbg",
              { v, no },
              (key) =>
                salesApi().ycbg(
                  quote.case_id,
                  { case_version: v, ycbg_no: no },
                  key,
                ),
              `Đã ghi YCBG ${no}`,
            ),
          )
        }
        note="Phản hồi của Design được ghép với hồ sơ bằng đúng số YCBG này."
      />
      <NumberDialog
        open={dialog === "submit"}
        title="Trình duyệt báo giá"
        field="Số báo giá"
        ok="Trình duyệt"
        loading={pending === "submit"}
        onCancel={() => setDialog(null)}
        onSubmit={async (no) =>
          finish(
            await run(
              "submit",
              { v, no },
              (key) =>
                salesApi().submit(
                  quote.case_id,
                  { case_version: v, quote_no: no },
                  key,
                ),
              `Đã trình duyệt báo giá ${no}`,
            ),
          )
        }
        note="DW1 điền tài liệu báo giá (xlsx + PDF) từ giá đã quyết định và đóng dấu mã băm; người duyệt duyệt đúng tài liệu đó."
      />
      <DeclineDialog
        open={dialog === "decline"}
        quote={quote}
        loading={pending === "decline"}
        onCancel={() => setDialog(null)}
        onSubmit={async (reason, note) => {
          const body = { case_version: v, reason, note };
          finish(
            await run(
              "decline",
              body,
              (key) => salesApi().decline(quote.case_id, body, key),
              "Đã ghi từ chối báo giá",
            ),
          );
        }}
      />
    </div>
  );
}

function NumberDialog({
  open,
  title,
  field,
  ok,
  note,
  loading,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  title: string;
  field: string;
  ok: string;
  note: string;
  loading: boolean;
  onCancel: () => void;
  onSubmit: (value: string) => void;
}) {
  const [form] = Form.useForm<{ no: string }>();
  return (
    <Modal
      open={open}
      title={title}
      okText={ok}
      cancelText="Hủy"
      okButtonProps={{ loading }}
      onCancel={onCancel}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      <Typography.Paragraph>{note}</Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        onFinish={({ no }) => onSubmit(no.trim().toUpperCase())}
      >
        <Form.Item
          name="no"
          label={field}
          rules={[
            {
              required: true,
              message: `${field} là bắt buộc`,
              validateTrigger: "onSubmit",
            },
            {
              pattern: DOCUMENT_NO,
              message: DOCUMENT_NO_HELP,
              transform: (v: string) => v?.trim().toUpperCase(),
            },
          ]}
        >
          <Input maxLength={32} autoComplete="off" />
        </Form.Item>
      </Form>
    </Modal>
  );
}

function DeclineDialog({
  open,
  quote,
  loading,
  onCancel,
  onSubmit,
}: {
  open: boolean;
  quote: Quote;
  loading: boolean;
  onCancel: () => void;
  onSubmit: (reason: keyof typeof DECLINE_REASON, note: string | null) => void;
}) {
  const [form] = Form.useForm<{
    reason: keyof typeof DECLINE_REASON;
    note?: string;
  }>();
  return (
    <Modal
      open={open}
      title={`Từ chối báo giá RFQ ${quote.rfq_no}`}
      okText="Từ chối báo giá"
      cancelText="Hủy"
      okButtonProps={{ danger: true, loading }}
      onCancel={onCancel}
      onOk={() => form.submit()}
      destroyOnHidden
    >
      <Typography.Paragraph>
        Hồ sơ dừng ở trạng thái từ chối và không mở lại được. DW1 soạn thư từ
        chối kèm lý do; bạn gửi thư đó cho khách.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        onFinish={({ reason, note }) => onSubmit(reason, note?.trim() || null)}
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
            options={Object.entries(DECLINE_REASON).map(([value, text]) => ({
              value,
              label: text,
            }))}
          />
        </Form.Item>
        <Form.Item name="note" label="Ghi chú">
          <Input.TextArea rows={3} maxLength={1000} showCount />
        </Form.Item>
      </Form>
    </Modal>
  );
}

/**
 * What the request lacked (`rfq_incomplete`) or whose customer is not known
 * yet (`customer_unknown`): Sales types the customer's answer, one finding at
 * a time, before the YCBG is drafted.
 */
function IntakeFindings({
  quote,
  viewer,
  onDone,
}: {
  quote: Quote;
  viewer: Viewer;
  onDone: () => void;
}) {
  const name = usePeople();
  const intake = quote.findings.filter((f) =>
    ["rfq_incomplete", "customer_unknown"].includes(f.code),
  );
  if (!intake.length) return null;
  return (
    <div className="space-y-2">
      {intake.map((f) => (
        <IntakeFinding
          key={f.key}
          quote={quote}
          finding={f}
          viewer={viewer}
          onDone={onDone}
          name={name}
        />
      ))}
    </div>
  );
}

function IntakeFinding({
  quote,
  finding,
  viewer,
  onDone,
  name,
}: {
  quote: Quote;
  finding: Finding;
  viewer: Viewer;
  onDone: () => void;
  name: (id: string | null | undefined) => string;
}) {
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [form] = Form.useForm<{
    quantity?: string;
    needed_by?: Parameters<typeof fromPickerDay>[0];
    customer_code?: string;
    note?: string;
  }>();
  const open = finding.disposition.kind === "open";
  const reason =
    quote.status !== "received"
      ? null
      : viewer.hasScope("sales.quote.prepare")
        ? null
        : "Bạn không có quyền bổ sung yêu cầu báo giá.";
  return (
    <Card
      size="small"
      type="inner"
      title={`${label(FINDING_CODE, finding.code)}${finding.line_no ? ` · dòng ${finding.line_no}` : ""}`}
    >
      {finding.missing.length ? (
        <Typography.Paragraph>
          Thiếu: {finding.missing.join(", ")}.
        </Typography.Paragraph>
      ) : null}
      {!open ? (
        <Typography.Text>
          Đã bổ sung
          {finding.disposition.by ? ` · ${name(finding.disposition.by)}` : ""}
          {finding.disposition.at
            ? ` · ${formatDateTime(finding.disposition.at)}`
            : ""}
          {finding.disposition.customer_code
            ? ` · khách ${finding.disposition.customer_code}`
            : ""}
          {finding.disposition.quantity
            ? ` · số lượng ${finding.disposition.quantity}`
            : ""}
          {finding.disposition.needed_by
            ? ` · cần hàng ${finding.disposition.needed_by}`
            : ""}
        </Typography.Text>
      ) : quote.status === "received" ? (
        <Form
          form={form}
          layout="inline"
          validateTrigger="onBlur"
          onFinish={async (values) => {
            const body = {
              case_version: quote.case_version,
              quantity: values.quantity || null,
              needed_by: fromPickerDay(values.needed_by) ?? null,
              customer_code: values.customer_code?.trim().toUpperCase() || null,
              note: values.note?.trim() || null,
            };
            const result = await run(
              `answer/${finding.key}`,
              body,
              (key) =>
                salesApi().answerFinding(quote.case_id, finding.key, body, key),
              "Đã bổ sung thông tin yêu cầu báo giá",
            );
            if (result.ok) {
              setError(null);
              onDone();
            } else setError(result.error);
          }}
        >
          {finding.code === "customer_unknown" ? (
            <Form.Item
              name="customer_code"
              label="Mã khách hàng"
              rules={[
                {
                  required: true,
                  message: "Cần mã khách",
                  validateTrigger: "onSubmit",
                },
                {
                  pattern: CUSTOMER_CODE,
                  message: "Mã khách gồm chữ in hoa và số",
                  transform: (v: string) => v?.trim().toUpperCase(),
                },
              ]}
            >
              <Input maxLength={16} />
            </Form.Item>
          ) : (
            <>
              <Form.Item name="quantity" label="Số lượng">
                <AmountInput aria-label="Số lượng khách trả lời" />
              </Form.Item>
              <Form.Item name="needed_by" label="Ngày cần hàng">
                <DatePicker format="DD/MM/YYYY" />
              </Form.Item>
              <Form.Item name="note" label="Ghi chú">
                <Input maxLength={1000} />
              </Form.Item>
            </>
          )}
          <Form.Item>
            <GuardedButton
              htmlType="submit"
              type="primary"
              reason={reason}
              loading={pending === `answer/${finding.key}`}
            >
              Ghi câu trả lời của khách
            </GuardedButton>
          </Form.Item>
        </Form>
      ) : null}
      <ActionError error={error} />
    </Card>
  );
}
