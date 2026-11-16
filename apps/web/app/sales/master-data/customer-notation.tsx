"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { Drawer, Flex, Select, Table, Tooltip, Typography } from "antd";
import { InfoTip, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { useAuth } from "../../../lib/auth/auth-context";
import { salesApi } from "../_lib/api";
import {
  caseHref,
  entryOf,
  evidenceLine,
  NOTATION_KIND,
  NOTATION_KINDS,
  notationValue,
  type CustomerNotation,
  type NotationEntry,
  type NotationKind,
} from "../_lib/customer-notation";
import { ActionError } from "../_lib/errors";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { GuardedButton } from "../_components/guarded-button";
import { SCOPE } from "../_components/sales-frame";

const CHANGE_BLOCKED = "Cần quyền chuẩn bị đơn (sales.order.prepare).";

/**
 * How one customer writes numbers, dates and a bare "$" or "¥" (ticket 37),
 * on the customer's row of the master data: each kind as Sales' confirmations
 * settled it, or as a person set it. DW reads by it only where a document
 * itself does not say; the evidence opens on click. A holder of
 * `sales.order.prepare` sets or forgets a kind (the server asks the same).
 */
export function CustomerNotationDrawer({
  customerCode,
  onClose,
}: {
  customerCode: string;
  onClose: () => void;
}) {
  const { hasScope } = useAuth();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const notation = useResource(
    `sales/customer-notation/${customerCode}`,
    useCallback(
      () => salesApi().customerNotation(customerCode),
      [customerCode],
    ),
  );
  const blocked = hasScope(SCOPE.prepare) ? null : CHANGE_BLOCKED;

  const change = async (kind: NotationKind, value: string | null) => {
    setError(null);
    const id = `notation/${customerCode}/${kind}`;
    const result =
      value === null
        ? await run(
            id,
            { kind },
            (key) => salesApi().forgetCustomerNotation(customerCode, kind, key),
            "Đã bỏ: giá trị kiểu này lại để người đọc.",
          )
        : await run(
            id,
            { kind, value },
            (key) =>
              salesApi().setCustomerNotation(
                customerCode,
                { kind, value },
                key,
              ),
            "Đã lưu cách viết của khách.",
          );
    if (result.ok) notation.reload();
    else setError(result.error);
  };

  return (
    <Drawer
      open
      onClose={onClose}
      title={
        <Flex align="center" gap="small">
          <span>Cách viết số và ngày của khách {customerCode}</span>
          <InfoTip label="Cách viết số và ngày là gì">
            DW học từ giá trị Sales xác nhận (“1.200 m” xác nhận là 1200 m), và
            chỉ dùng khi chính chứng từ không nói rõ. Chứng từ viết khác đi thì
            để người đọc.
          </InfoTip>
        </Flex>
      }
      size="large"
    >
      <Flex vertical gap="middle">
        <ActionError error={error} />
        {notation.error ? (
          <LoadError error={notation.error} onRetry={notation.reload} />
        ) : (
          <NotationTable
            notation={notation.data ?? undefined}
            loading={notation.loading}
            blocked={blocked}
            pending={pending}
            customerCode={customerCode}
            onChange={(kind, value) => void change(kind, value)}
          />
        )}
      </Flex>
    </Drawer>
  );
}

/** The four kinds, each with its value, where it came from and its change. */
export function NotationTable({
  notation,
  loading,
  blocked,
  pending,
  customerCode,
  onChange,
}: {
  notation: CustomerNotation | undefined;
  loading: boolean;
  blocked: string | null;
  pending: string | null;
  customerCode: string;
  onChange: (kind: NotationKind, value: string | null) => void;
}) {
  const name = usePeople();
  const rows = NOTATION_KINDS.map((kind) => ({
    kind,
    entry: entryOf(notation, kind),
  }));
  return (
    <Table
      rowKey="kind"
      size="small"
      loading={loading}
      pagination={false}
      dataSource={notation ? rows : []}
      locale={{ emptyText: loading ? " " : "Chưa đọc được." }}
      expandable={{
        rowExpandable: (row) => row.entry !== undefined,
        expandedRowRender: (row) =>
          row.entry ? <Evidence entry={row.entry} name={name} /> : null,
      }}
      columns={[
        {
          title: "Kiểu",
          dataIndex: "kind",
          render: (kind: NotationKind) => NOTATION_KIND[kind],
        },
        {
          title: "Khách viết",
          key: "value",
          render: (_, row) =>
            row.entry ? (
              <Flex vertical gap={2}>
                <span>{notationValue(row.kind, row.entry.value)}</span>
                <StatusTag tone={row.entry.source === "set" ? "pri" : "ok"}>
                  {row.entry.source === "set"
                    ? "Người dùng đặt"
                    : "Học từ xác nhận"}
                </StatusTag>
              </Flex>
            ) : (
              <StatusTag tone="warn">Chưa biết: để người đọc</StatusTag>
            ),
        },
        {
          title: "Đổi",
          key: "change",
          fixed: "right",
          render: (_, row) => (
            <Flex wrap gap="small" align="center">
              <Tooltip title={blocked}>
                <Select
                  size="small"
                  className="min-w-56"
                  disabled={blocked !== null}
                  loading={pending === `notation/${customerCode}/${row.kind}`}
                  aria-label={`Đặt ${NOTATION_KIND[row.kind]} của khách ${customerCode}`}
                  value={row.entry?.value}
                  placeholder="Chọn"
                  options={(notation?.choices[row.kind] ?? []).map((value) => ({
                    value,
                    label: notationValue(row.kind, value),
                  }))}
                  onChange={(value: string) => onChange(row.kind, value)}
                />
              </Tooltip>
              {row.entry ? (
                <GuardedButton
                  size="small"
                  reason={blocked}
                  inlineReason={false}
                  onClick={() => onChange(row.kind, null)}
                  aria-label={`Bỏ ${NOTATION_KIND[row.kind]} của khách ${customerCode}`}
                >
                  Bỏ
                </GuardedButton>
              ) : null}
            </Flex>
          ),
        },
      ]}
    />
  );
}

function Evidence({
  entry,
  name,
}: {
  entry: NotationEntry;
  name: (id: string) => string;
}) {
  const href = caseHref(entry);
  return (
    <Flex vertical gap={2}>
      <Typography.Text>{evidenceLine(entry)}</Typography.Text>
      <Typography.Text>
        {name(entry.by)} · {formatDateTime(entry.at)}
        {href ? (
          <>
            {" · "}
            <Link href={href}>
              {entry.case_kind === "order" ? "Mở đơn" : "Mở yêu cầu báo giá"}
            </Link>
          </>
        ) : null}
      </Typography.Text>
    </Flex>
  );
}
