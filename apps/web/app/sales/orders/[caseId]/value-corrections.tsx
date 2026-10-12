"use client";

import { useState, type ReactNode } from "react";
import {
  Button,
  DatePicker,
  Input,
  Select,
  Space,
  Table,
  Typography,
} from "antd";
import type { SalesSchemas, Words } from "@dw/api-client";
import {
  formatDate,
  formatDateTime,
  fromPickerDay,
  toPickerDay,
} from "../../../../lib/dates";
import { CURRENCIES } from "../../../../lib/money";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { FIELD, label } from "../../_lib/labels";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { AmountInput } from "../../_components/amount-input";
import { GuardedButton } from "../../_components/guarded-button";
import {
  Money,
  PRICE_SENTENCE,
  Quantity,
  isHidden,
} from "../../_components/money";
import { ValueStateTag } from "../../_components/tags";

type Order = SalesSchemas["OrderCaseView"];
type Finding = SalesSchemas["OrderFindingView"];
type Correction = SalesSchemas["ValueCorrectionView"];

// How each value is typed: a display choice. What each field holds, and who
// may type an amount, is the case's to decide (`OrderCase.corrected`, 422 or
// 403 otherwise); this only picks the antd control.
const AMOUNTS = ["unit_price", "amount", "total"];
const DATES = ["requested_date", "po_date"];
/** A line's number and the PO's number and revision are confirmed as read. */
const IDENTITY = ["line_no", "po_no", "revision"];

interface Row {
  field: string;
  read: Words | number | null | undefined;
  correction: Correction | undefined;
}

/** The finding's flagged values, each as read and as Sales typed it. */
function rows(order: Order, finding: Finding): Row[] {
  const line = order.lines.find((l) => l.line_no === finding.line_no);
  const corrections = line ? line.corrections : order.header_corrections;
  // The line's values, or the header's and the total, keyed by field.
  const values = new Map<string, unknown>(Object.entries(line ?? order));
  return finding.fields.map((field) => ({
    field,
    read: values.get(field) as Row["read"],
    correction: corrections.find((c) => c.field === field),
  }));
}

function Shown({
  field,
  value,
  order,
}: {
  field: string;
  value: Words | number | null | undefined;
  order: Order;
}) {
  if (AMOUNTS.includes(field))
    return <Money value={value as Words} currency={order.currency} />;
  if (field === "quantity" && !isHidden(value))
    return <Quantity value={value} />;
  if (DATES.includes(field) && typeof value === "string")
    return <span>{formatDate(value)}</span>;
  if (value === null || value === undefined || value === "")
    return <span>Không có</span>;
  return <span>{String(value)}</span>;
}

/**
 * Ticket 15: a value DW1 could not be sure of is typed by Sales one field at a
 * time, beside the value as read (which stays as the evidence). The finding
 * is resolved once every flagged value has one; each one names who typed it,
 * and that person cannot cross-check the order.
 */
export function ValueCorrections({
  order,
  finding,
  canEdit,
  canTypeAmounts,
  onCorrected,
}: {
  order: Order;
  finding: Finding;
  /** The viewer may decide this finding now (the case's state and their role). */
  canEdit: boolean;
  /** The viewer holds `sales.price.read`: only they read, and type, an amount. */
  canTypeAmounts: boolean;
  onCorrected: () => void;
}) {
  const name = usePeople();
  const { run, pending } = useAction();
  const [typed, setTyped] = useState<Record<string, string>>({});
  const [error, setError] = useState<unknown>(null);
  const data = rows(order, finding);
  const left = data.filter((r) => !r.correction).length;

  const send = async (field: string, value: string) => {
    const body = { case_version: order.case_version, field, value };
    const result = await run(
      `correct/${finding.key}/${field}`,
      body,
      (key) => salesApi().correctValue(order.case_id, finding.key, body, key),
      `Đã ghi giá trị Sales sửa: ${label(FIELD, field)}`,
    );
    if (result.ok) {
      setError(null);
      setTyped((now) => ({ ...now, [field]: "" }));
      onCorrected();
    } else setError(result.error);
  };

  const control = (row: Row): ReactNode => {
    const { field } = row;
    const where = `${label(FIELD, field)}${finding.line_no ? `, dòng ${finding.line_no}` : ""}`;
    if (!canEdit) return null;
    if (AMOUNTS.includes(field) && !canTypeAmounts)
      return <Typography.Text>{PRICE_SENTENCE}</Typography.Text>;
    const busy = pending === `correct/${finding.key}/${field}`;
    if (IDENTITY.includes(field))
      return (
        <Button
          size="small"
          loading={busy}
          onClick={() => send(field, String(row.read))}
        >
          Xác nhận đúng như đọc
        </Button>
      );
    const value = typed[field] ?? "";
    const set = (next: string) =>
      setTyped((now) => ({ ...now, [field]: next }));
    let input: ReactNode;
    if (AMOUNTS.includes(field) || field === "quantity")
      input = (
        <AmountInput
          size="small"
          aria-label={`Giá trị đúng: ${where}`}
          value={value}
          onChange={set}
          currency={AMOUNTS.includes(field) ? order.currency : undefined}
        />
      );
    else if (DATES.includes(field))
      input = (
        <DatePicker
          size="small"
          format="DD/MM/YYYY"
          aria-label={`Giá trị đúng: ${where}`}
          value={toPickerDay(value)}
          onChange={(day) => set(fromPickerDay(day) ?? "")}
        />
      );
    else if (field === "currency")
      input = (
        <Select
          size="small"
          aria-label={`Giá trị đúng: ${where}`}
          className="min-w-24"
          value={value || undefined}
          onChange={set}
          options={CURRENCIES.map((c) => ({ value: c, label: c }))}
        />
      );
    else
      input = (
        <Input
          size="small"
          aria-label={`Giá trị đúng: ${where}`}
          maxLength={200}
          value={value}
          onChange={(event) => set(event.target.value)}
        />
      );
    return (
      <Space.Compact>
        {input}
        <GuardedButton
          size="small"
          type="primary"
          inlineReason={false}
          reason={value.trim() ? null : "Nhập giá trị đúng trước khi ghi."}
          loading={busy}
          onClick={() => send(field, value.trim())}
        >
          Ghi
        </GuardedButton>
      </Space.Compact>
    );
  };

  return (
    <div className="space-y-2">
      <Typography.Text role="status">
        {left
          ? `Còn ${left}/${data.length} giá trị chưa nhập lại. Cờ được giải quyết khi mọi giá trị bị gắn cờ đã có giá trị Sales nhập.`
          : "Mọi giá trị bị gắn cờ đã có giá trị Sales nhập."}
      </Typography.Text>
      <Table<Row>
        rowKey="field"
        size="small"
        pagination={false}
        dataSource={data}
        scroll={{ x: "max-content" }}
        columns={[
          {
            title: "Giá trị",
            key: "field",
            render: (_, row) => label(FIELD, row.field),
          },
          {
            title: "Đọc được",
            key: "read",
            render: (_, row) => (
              <Shown field={row.field} value={row.read} order={order} />
            ),
          },
          {
            title: "Sales nhập",
            key: "corrected",
            render: (_, row) =>
              row.correction ? (
                <Space orientation="vertical" size={0}>
                  <Shown
                    field={row.field}
                    value={row.correction.value}
                    order={order}
                  />
                  <Typography.Text>
                    {name(row.correction.by)} ·{" "}
                    {formatDateTime(row.correction.at)}
                  </Typography.Text>
                </Space>
              ) : (
                <ValueStateTag state="uncertain" />
              ),
          },
          ...(canEdit
            ? [
                {
                  title: "Giá trị đúng",
                  key: "input",
                  render: (_: unknown, row: Row) => control(row),
                },
              ]
            : []),
        ]}
      />
      {canEdit ? (
        <Typography.Paragraph className="!mb-0">
          Giá trị nhập tay ghi tên bạn; người kiểm chéo phải là người khác.
        </Typography.Paragraph>
      ) : null}
      <ActionError error={error} />
    </div>
  );
}
