"use client";

import { useCallback, useState } from "react";
import { Button, DatePicker, Form, Input, Typography } from "antd";
import { EyeOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";
import {
  formatDate,
  formatDateTime,
  fromPickerDay,
  toPickerDay,
} from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { FIELD, FINDING_CODE, label, REGION_FLAG } from "../../_lib/labels";
import type { Viewer } from "../../_lib/order-actions";
import { useAction } from "../../_lib/use-action";
import { AmountInput } from "../../_components/amount-input";
import { GuardedButton } from "../../_components/guarded-button";
import {
  MailTextDrawer,
  type MailTarget,
} from "../../_components/mail-text-drawer";

type Quote = SalesSchemas["QuoteCaseView"];
type Finding = SalesSchemas["QuoteFindingView"];

/** Where a value was read, opened by the page: a file region or the mail. */
export type OpenSource = (field: string, lineNo: number | null) => void;

const DATES = new Set(["quote_due", "needed_by"]);

/**
 * Why "Xác nhận" waits on a value whose source this person has not opened at
 * this case version (`QuoteFindingView.source_not_served`, audit gap 2): the
 * server refuses it (409 `source_not_served`) whatever the button shows.
 */
export const SOURCE_FIRST_REASON =
  "Mở nguồn trước khi xác nhận: bấm “Nguồn” để xem chỗ giá trị này được đọc.";

/** A value of the request as the case holds it now, as text for the field. */
export function currentValue(
  quote: Quote,
  field: string,
  lineNo: number | null,
): string | null {
  if (lineNo === null) {
    const header: Record<string, string | null> = {
      rfq_no: quote.rfq_no,
      quote_due: quote.quote_due,
      currency: quote.currency,
    };
    return header[field] ?? null;
  }
  const line = quote.lines.find((l) => l.line_no === lineNo);
  if (!line) return null;
  const values: Record<string, string | null> = {
    customer_item_code: line.customer_item_code,
    description: line.description,
    quantity: line.quantity,
    uom: line.uom,
    needed_by: line.needed_by,
  };
  return values[field] ?? null;
}

function shown(field: string, value: string | null): string {
  if (value === null) return "Không có";
  return DATES.has(field) ? formatDate(value) : value;
}

/**
 * A `value_uncertain` a model reading raised (ticket 29): every value the
 * model read, beside the place it was read from, for Sales to confirm one by
 * one, typing it as it should be, or all of the line's still waiting as read
 * with one press (Đạt, 2026-11-04). The YCBG waits until each is confirmed.
 */
export function ModelReadFinding({
  quote,
  finding,
  viewer,
  onDone,
  onSource,
  name,
}: {
  quote: Quote;
  finding: Finding;
  viewer: Viewer;
  onDone: () => void;
  onSource?: OpenSource;
  name: (id: string | null | undefined) => string;
}) {
  const confirmed = new Map(finding.confirmed.map((c) => [c.field, c]));
  const reason =
    quote.status !== "received"
      ? "Chỉ xác nhận khi hồ sơ còn ở bước tiếp nhận."
      : viewer.hasScope("sales.quote.prepare")
        ? null
        : "Bạn không có quyền xác nhận giá trị của yêu cầu báo giá.";
  const unserved = new Set(finding.source_not_served);
  const waiting = finding.flagged.filter((field) => !confirmed.has(field));
  const where = finding.line_no ? `dòng ${finding.line_no}` : "thông tin chung";
  return (
    <div
      className="space-y-2"
      role="group"
      aria-label={`${label(FINDING_CODE, finding.code)}${finding.line_no ? ` dòng ${finding.line_no}` : ""}`}
    >
      <Typography.Text strong>
        {finding.line_no
          ? `Dòng ${finding.line_no}`
          : "Thông tin chung của yêu cầu"}{" "}
        <StatusTag tone="warn">{label(REGION_FLAG, "model_read")}</StatusTag>
      </Typography.Text>
      {finding.flagged.map((field) => {
        const done = confirmed.get(field);
        return (
          <div
            key={field}
            role="group"
            aria-label={`${label(FIELD, field)}${finding.line_no ? ` dòng ${finding.line_no}` : ""}`}
            className="flex flex-wrap items-center gap-2"
          >
            <Typography.Text className="min-w-[9rem]">
              {label(FIELD, field)}
            </Typography.Text>
            {done ? (
              <Typography.Text>
                Đã xác nhận: {shown(field, done.value)}
                {done.read !== done.value
                  ? ` (mô hình đọc: ${shown(field, done.read || null)})`
                  : ""}{" "}
                · {name(done.by)} · {formatDateTime(done.at)}
              </Typography.Text>
            ) : (
              <ConfirmValue
                quote={quote}
                finding={finding}
                field={field}
                reason={
                  reason ?? (unserved.has(field) ? SOURCE_FIRST_REASON : null)
                }
                onDone={onDone}
              />
            )}
            {onSource ? (
              <Button
                size="small"
                icon={<EyeOutlined aria-hidden />}
                onClick={() => onSource(field, finding.line_no)}
                aria-label={`Xem nguồn ${label(FIELD, field)}${finding.line_no ? ` dòng ${finding.line_no}` : ""}`}
              >
                Nguồn
              </Button>
            ) : null}
          </div>
        );
      })}
      {waiting.length > 1 ? (
        <ConfirmAsRead
          quote={quote}
          finding={finding}
          where={where}
          reason={
            reason ??
            (waiting.some((field) => unserved.has(field))
              ? SOURCE_FIRST_REASON
              : null)
          }
          onDone={onDone}
        />
      ) : null}
    </div>
  );
}

/** Every value of the finding still waiting, confirmed as read, one press. */
function ConfirmAsRead({
  quote,
  finding,
  where,
  reason,
  onDone,
}: {
  quote: Quote;
  finding: Finding;
  where: string;
  reason: string | null;
  onDone: () => void;
}) {
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const key = `confirm/${finding.key}/as-read`;
  const text = finding.line_no
    ? "Xác nhận cả dòng như đã đọc"
    : "Xác nhận cả phần như đã đọc";
  return (
    <>
      <GuardedButton
        reason={reason}
        loading={pending === key}
        aria-label={`${text} (${where})`}
        onClick={async () => {
          const body = { case_version: quote.case_version, as_read: true };
          const result = await run(
            key,
            body,
            (idem) =>
              salesApi().answerFinding(quote.case_id, finding.key, body, idem),
            `Đã xác nhận ${where}`,
          );
          if (result.ok) {
            setError(null);
            onDone();
          } else setError(result.error);
        }}
      >
        {text}
      </GuardedButton>
      <ActionError error={error} />
    </>
  );
}

function ConfirmValue({
  quote,
  finding,
  field,
  reason,
  onDone,
}: {
  quote: Quote;
  finding: Finding;
  field: string;
  reason: string | null;
  onDone: () => void;
}) {
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const read = currentValue(quote, field, finding.line_no);
  const [form] = Form.useForm<{
    value?: string;
    day?: ReturnType<typeof toPickerDay>;
  }>();
  const key = `confirm/${finding.key}/${field}`;
  return (
    <>
      <Form
        form={form}
        layout="inline"
        initialValues={{
          value: DATES.has(field) ? undefined : (read ?? undefined),
          day: DATES.has(field) ? toPickerDay(read) : undefined,
        }}
        onFinish={async (values) => {
          const value = DATES.has(field)
            ? fromPickerDay(values.day)
            : values.value?.trim();
          if (!value) return;
          const body = {
            case_version: quote.case_version,
            field,
            value,
            as_read: false,
          };
          const result = await run(
            key,
            body,
            (idem) =>
              salesApi().answerFinding(quote.case_id, finding.key, body, idem),
            `Đã xác nhận ${label(FIELD, field).toLowerCase()}`,
          );
          if (result.ok) {
            setError(null);
            onDone();
          } else setError(result.error);
        }}
      >
        {DATES.has(field) ? (
          <Form.Item
            name="day"
            rules={[{ required: true, message: "Cần ngày" }]}
          >
            <DatePicker
              format="DD/MM/YYYY"
              aria-label={`${label(FIELD, field)} xác nhận`}
            />
          </Form.Item>
        ) : field === "quantity" ? (
          <Form.Item
            name="value"
            rules={[{ required: true, message: "Cần số lượng" }]}
          >
            <AmountInput aria-label={`${label(FIELD, field)} xác nhận`} />
          </Form.Item>
        ) : (
          <Form.Item
            name="value"
            rules={[{ required: true, message: "Cần giá trị" }]}
          >
            <Input
              maxLength={500}
              aria-label={`${label(FIELD, field)} xác nhận`}
              className="min-w-[14rem]"
            />
          </Form.Item>
        )}
        <Form.Item>
          <GuardedButton
            htmlType="submit"
            reason={reason}
            loading={pending === key}
          >
            Xác nhận
          </GuardedButton>
        </Form.Item>
      </Form>
      <ActionError error={error} />
    </>
  );
}

/**
 * The newest part of the mail a model read the request from (ticket 29):
 * `MailTextDrawer` over the quote's own route, whose serving confirming a
 * value read from it requires.
 */
export function MessageTextDrawer({
  quote,
  target,
  mayRead,
  onClose,
}: {
  quote: Quote;
  target: MailTarget | null;
  mayRead: boolean;
  onClose: () => void;
}) {
  const load = useCallback(
    () => salesApi().quoteMessageText(quote.case_id),
    [quote.case_id],
  );
  return (
    <MailTextDrawer
      resourceKey={`sales/quote/${quote.case_id}/${quote.case_version}/message-text`}
      load={load}
      target={target}
      mayRead={mayRead}
      onClose={onClose}
    />
  );
}
