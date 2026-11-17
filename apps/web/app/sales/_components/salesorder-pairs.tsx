"use client";

import { useCallback, useState } from "react";
import { App, Button, Flex, Table, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { InfoTip, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";

export type WorkedPair = SalesSchemas["WorkedPairView"];

/**
 * A customer's worked pairs (ticket 41): each PO and the SalesOrder file the
 * PIC made from it, kept when an example was read, which every proposed
 * version of the customer's SalesOrder skill is replayed on. A wrong pair
 * (the PIC's file was itself wrong) is withdrawn here, after a confirmation
 * naming its PO; the server refuses a caller who may not, and audits who
 * did. Pairs past the company's term leave on their own.
 */
export function SalesOrderPairs({ customerCode }: { customerCode: string }) {
  const { modal } = App.useApp();
  const { run, pending } = useAction();
  const name = usePeople();
  const [error, setError] = useState<unknown>(null);
  const pairs = useResource(
    `sales/salesorder-pairs/${customerCode}`,
    useCallback(() => salesApi().salesOrderPairs(customerCode), [customerCode]),
  );
  const list = pairs.data ?? [];
  const id = (p: WorkedPair) => `withdraw-pair/${p.pair_id}`;

  const withdraw = (p: WorkedPair) =>
    modal.confirm({
      title: `Rút cặp ví dụ PO ${p.po_no}?`,
      content:
        "Kỹ năng SalesOrder của khách không còn được chạy thử trên cặp này. Không hoàn tác được: muốn dùng lại thì tải lại ví dụ.",
      okText: "Rút cặp",
      okButtonProps: { danger: true },
      cancelText: "Giữ lại",
      focusable: { autoFocusButton: "cancel" },
      onOk: async () => {
        setError(null);
        const result = await run(
          id(p),
          { pair: p.pair_id },
          (key) => salesApi().withdrawSalesOrderPair(p.pair_id, key),
          `Đã rút cặp ví dụ PO ${p.po_no}.`,
        );
        if (result.ok) pairs.reload();
        else setError(result.error);
      },
    });

  return (
    <Flex vertical gap="small">
      <Flex gap="small" align="center">
        <Typography.Title level={5} className="mb-0!">
          Cặp ví dụ của khách
        </Typography.Title>
        <InfoTip label="Cặp ví dụ là gì">
          Mỗi ví dụ đã đọc được giữ lại thành một cặp: PO và tệp SalesOrder PIC
          đã làm. Phiên bản kỹ năng SalesOrder đề xuất cho khách được chạy thử
          trên các cặp mới nhất và chỉ được duyệt khi điền đúng mọi cặp. Cặp quá
          thời hạn công ty đặt tự được xóa.
        </InfoTip>
      </Flex>
      <ActionError error={error} />
      {pairs.error ? (
        <LoadError error={pairs.error} onRetry={pairs.reload} />
      ) : (
        <Table<WorkedPair>
          rowKey="pair_id"
          size="small"
          loading={pairs.loading}
          dataSource={list}
          pagination={false}
          scroll={{ x: "max-content" }}
          locale={{
            emptyText: pairs.loading
              ? " "
              : "Khách này chưa có cặp ví dụ nào: tải một ví dụ ở trên.",
          }}
          footer={() => `${list.length} cặp, mới nhất trước`}
          columns={[
            {
              title: "PO",
              key: "po",
              render: (_, p) => (
                <span className="flex flex-col items-start gap-1">
                  <Typography.Text strong>{p.po_no}</Typography.Text>
                  <span>
                    {p.rows} dòng · nhận {formatDateTime(p.received_on)}
                  </span>
                </span>
              ),
            },
            {
              title: "Chạy thử",
              key: "replayed",
              render: (_, p) =>
                p.replayed ? (
                  <StatusTag tone="ok">Được chạy thử</StatusTag>
                ) : (
                  <StatusTag tone="gray">Cũ, không chạy thử</StatusTag>
                ),
            },
            {
              title: "Thêm bởi",
              key: "added",
              render: (_, p) => (
                <span className="flex flex-col">
                  <span>{name(p.added_by)}</span>
                  <span>{formatDateTime(p.added_at)}</span>
                </span>
              ),
            },
            {
              title: "Thao tác",
              key: "actions",
              fixed: "right",
              render: (_, p) => (
                <Button
                  size="small"
                  danger
                  loading={pending === id(p)}
                  onClick={() => withdraw(p)}
                  aria-label={`Rút cặp ví dụ PO ${p.po_no}`}
                >
                  Rút cặp
                </Button>
              ),
            },
          ]}
        />
      )}
    </Flex>
  );
}
