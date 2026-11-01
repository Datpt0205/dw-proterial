"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { App, Button, Card, Flex, Table, Tooltip, Typography } from "antd";
import { ReadOutlined } from "@ant-design/icons";
import type { PurchaseInboxItem } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { errorMessage } from "../../../lib/error-message";
import { useIdempotencyKeys } from "../../../lib/idempotency";
import { useAuth } from "../../../lib/auth/auth-context";
import { useCachedResource } from "../../../lib/use-cached-resource";
import { purchasingApi } from "../_lib/api";
import { MAIL_OUTCOME, mailReason } from "../_lib/labels";
import { SCOPE } from "../_lib/scopes";
import { purchasingCrumbs, ScopeGate } from "../_components/frame";

/**
 * The purchasing mailbox: each mail with what DW2 did with it, settled once
 * (a case opened, or a person reads it and why, in words). A mail not yet
 * sorted can be handed to DW2 by a buyer; one sent to a person is read by
 * them, never guessed at.
 */
export default function InboxPage() {
  return (
    <ScopeGate scope={[SCOPE.read]}>
      <Inbox />
    </ScopeGate>
  );
}

function Inbox() {
  const { hasScope } = useAuth();
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [pending, setPending] = useState<string | null>(null);
  const mail = useCachedResource(
    "purchasing/mail",
    useCallback(() => purchasingApi().mailbox(), []),
  );
  const items = mail.data ?? [];
  const toPerson = items.filter((m) => m.disposition === "to_person").length;
  const why = hasScope(SCOPE.intake)
    ? null
    : "Vai của bạn không gồm việc nhận yêu cầu.";

  async function read(item: PurchaseInboxItem) {
    const id = `read:${item.message_id}`;
    setPending(item.message_id);
    try {
      const result = await purchasingApi().readMail(
        item.message_id,
        keys.keyFor(id, null),
      );
      keys.settle(id);
      message.success(
        result.disposition === "opened"
          ? "DW2 đã mở hồ sơ từ thư"
          : `Thư cần người xem: ${mailReason(result.reason)}`,
      );
      mail.reload();
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={purchasingCrumbs("Hộp thư")}
        title="Hộp thư mua hàng"
        subtitle={
          mail.data
            ? `${items.length} thư · ${toPerson} thư cần người xem`
            : "Thư đến hộp thư mua hàng và DW2 đã làm gì với mỗi thư"
        }
      />
      <Card size="small">
        {mail.error && !mail.data ? (
          <LoadError error={mail.error} onRetry={mail.reload} />
        ) : (
          <Table<PurchaseInboxItem>
            rowKey="message_id"
            size="small"
            sticky
            loading={mail.loading}
            dataSource={items}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: mail.loading
                ? " "
                : "Hộp thư mua hàng chưa có thư nào.",
            }}
            columns={[
              {
                title: `Nhận lúc (${TIME_ZONE_LABEL})`,
                key: "t",
                render: (_, m) =>
                  formatDateTime(m.received_at, { zoneLabel: false }),
              },
              { title: "Người gửi", dataIndex: "sender" },
              {
                title: "Tiêu đề",
                key: "s",
                render: (_, m) => (
                  <Typography.Text
                    ellipsis={{ tooltip: m.subject }}
                    className="max-w-80"
                  >
                    {m.subject}
                  </Typography.Text>
                ),
              },
              {
                title: "DW2 đã làm",
                key: "d",
                render: (_, m) =>
                  m.disposition === null ? (
                    <StatusTag tone="outline">Chưa phân loại</StatusTag>
                  ) : (
                    <Flex vertical gap={2}>
                      <StatusTag
                        tone={m.disposition === "opened" ? "ok" : "warn"}
                      >
                        {MAIL_OUTCOME[m.disposition]}
                      </StatusTag>
                      {m.disposition === "to_person" ? (
                        <Typography.Text>
                          {mailReason(m.reason)}
                        </Typography.Text>
                      ) : null}
                    </Flex>
                  ),
              },
              {
                title: "Hồ sơ",
                key: "c",
                fixed: "right",
                render: (_, m) =>
                  m.case_id ? (
                    <Link href={`/purchasing/requests/${m.case_id}`}>
                      Mở hồ sơ
                    </Link>
                  ) : m.disposition === null ? (
                    <Tooltip title={why}>
                      <Button
                        size="small"
                        icon={<ReadOutlined aria-hidden />}
                        disabled={
                          why !== null ||
                          (pending !== null && pending !== m.message_id)
                        }
                        loading={pending === m.message_id}
                        aria-label={`DW2 đọc thư ${m.subject}`}
                        onClick={() => void read(m)}
                      >
                        DW2 đọc thư
                      </Button>
                    </Tooltip>
                  ) : (
                    "Không có"
                  ),
              },
            ]}
          />
        )}
      </Card>
    </div>
  );
}
