"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Space, Table, Tag, Typography } from "antd";
import {
  PaperClipOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { RegionState } from "../../../components/region-state";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { label, MESSAGE_DISPOSITION, ROUTING_REASON } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { GuardedButton } from "../_components/guarded-button";
import { SCOPE, useSalesFrame } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";
import { MessageDispositionTag } from "../_components/tags";

type Message = SalesSchemas["InboxMessageView"];

/**
 * Hộp thư (mock): every sample message with the one disposition it ended in,
 * the reason and the owner of a message routed to Sales, and "DW xử lý" per
 * message or for all. The mock inbox stands in for a mailbox; processing
 * starts from the button.
 */
export default function InboxPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <Inbox />
      </Suspense>
    </ScopeGate>
  );
}

function Inbox() {
  const { hasScope } = useAuth();
  const { paused, overview } = useSalesFrame();
  const focus = useSearchParams().get("message");
  const name = usePeople();
  const inbox = useResource(
    "sales/inbox",
    useCallback(() => salesApi().inbox(), []),
  );
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);

  const messages = useMemo(() => inbox.data ?? [], [inbox.data]);
  const waiting = messages.filter(
    (m) => m.disposition.kind === "not_yet_processed",
  ).length;
  const counts = useMemo(() => {
    const byKind = new Map<string, number>();
    for (const m of messages)
      byKind.set(m.disposition.kind, (byKind.get(m.disposition.kind) ?? 0) + 1);
    return [...byKind.entries()];
  }, [messages]);

  const processReason = !hasScope(SCOPE.inbox)
    ? "Bạn không có quyền cho DW1 xử lý thư (cần quyền xử lý hộp thư của Sales)."
    : paused
      ? "DW1 đang tạm dừng: chỉ Trưởng bộ phận Sales cho DW1 chạy lại."
      : null;

  const after = (result: { ok: boolean; error?: unknown }) => {
    if (result.ok) {
      setError(null);
      inbox.reload();
      overview.reload();
    } else setError(result.error);
  };

  const processAll = async () =>
    after(
      await run(
        "inbox/all",
        null,
        (key) => salesApi().processAll(key),
        "DW1 đã xử lý các thư đang chờ",
      ),
    );

  const processOne = async (message: Message) =>
    after(
      await run(
        `inbox/${message.message_id}`,
        null,
        (key) => salesApi().processMessage(message.message_id, key),
        `DW1 đã xử lý thư ${message.message_id}`,
      ),
    );

  return (
    <div className="space-y-4">
      <PageHeader
        title="Hộp thư (giả lập)"
        description="Thư mẫu kèm PO, yêu cầu báo giá và phản hồi của Design. Mỗi thư kết thúc ở đúng một hướng xử lý; thư chuyển Sales có lý do và người phụ trách."
        extra={
          <GuardedButton
            type="primary"
            icon={<RobotOutlined aria-hidden />}
            loading={pending === "inbox/all"}
            reason={
              processReason ??
              (inbox.data && waiting === 0
                ? "Mọi thư đã có hướng xử lý."
                : null)
            }
            onClick={processAll}
          >
            DW xử lý tất cả ({waiting})
          </GuardedButton>
        }
      />
      <ActionError error={error} />
      {inbox.error ? (
        <RegionState error={inbox.error} onRetry={inbox.reload} />
      ) : (
        <>
          <Space wrap role="status" aria-label="Số thư theo hướng xử lý">
            {counts.map(([kind, n]) => (
              <Tag
                key={kind}
              >{`${label(MESSAGE_DISPOSITION, kind)}: ${n}`}</Tag>
            ))}
          </Space>
          <Table<Message>
            rowKey="message_id"
            loading={inbox.loading}
            dataSource={messages}
            pagination={false}
            sticky
            scroll={{ x: "max-content" }}
            rowClassName={(m) =>
              m.message_id === focus ? "ant-table-row-selected" : ""
            }
            expandable={{
              defaultExpandedRowKeys: focus ? [focus] : [],
              expandedRowRender: (m) => (
                <div className="max-w-3xl space-y-2">
                  {m.disposition.detail ? (
                    <Typography.Paragraph className="!mb-0">
                      <Typography.Text strong>
                        Ghi chú của DW1:{" "}
                      </Typography.Text>
                      {m.disposition.detail}
                    </Typography.Paragraph>
                  ) : null}
                  <Typography.Paragraph className="!mb-0 whitespace-pre-wrap">
                    {m.body_text}
                  </Typography.Paragraph>
                </div>
              ),
              expandRowByClick: false,
            }}
            locale={{
              emptyText: inbox.loading
                ? " "
                : "Hộp thư giả lập không có thư nào cho không gian làm việc này.",
            }}
            footer={() => `${messages.length} thư · ${waiting} chưa xử lý`}
            columns={[
              {
                title: `Nhận lúc (${TIME_ZONE_LABEL})`,
                dataIndex: "received_at",
                render: (at: string) =>
                  formatDateTime(at, { zoneLabel: false }),
              },
              {
                title: "Thư",
                key: "subject",
                render: (_, m) => (
                  <Space orientation="vertical" size={0} className="max-w-md">
                    <Typography.Text strong ellipsis={{ tooltip: m.subject }}>
                      {m.message_id} · {m.subject}
                    </Typography.Text>
                    <span>
                      {m.sender_name} &lt;{m.sender}&gt;{" "}
                      {m.sender_verified ? (
                        <Tag
                          color="success"
                          icon={<SafetyCertificateOutlined aria-hidden />}
                        >
                          Đã xác thực người gửi
                        </Tag>
                      ) : (
                        <Tag
                          color="warning"
                          icon={<WarningOutlined aria-hidden />}
                        >
                          Chưa xác thực người gửi
                        </Tag>
                      )}
                    </span>
                    {m.attachments.map((a) => (
                      <span key={a.attachment_id}>
                        <PaperClipOutlined aria-hidden /> {a.name}
                      </span>
                    ))}
                  </Space>
                ),
              },
              {
                title: "Hướng xử lý",
                key: "disposition",
                render: (_, m) => (
                  <Space orientation="vertical" size={2}>
                    <MessageDispositionTag kind={m.disposition.kind} />
                    {m.disposition.reason ? (
                      <span>
                        Lý do: {label(ROUTING_REASON, m.disposition.reason)}
                      </span>
                    ) : null}
                  </Space>
                ),
              },
              {
                title: "Người phụ trách",
                key: "owner",
                render: (_, m) =>
                  m.disposition.kind === "routed_to_sales" ? (
                    m.disposition.owner ? (
                      name(m.disposition.owner)
                    ) : (
                      <Tag color="error">Chưa có người phụ trách</Tag>
                    )
                  ) : (
                    ""
                  ),
              },
              {
                title: "Hồ sơ",
                key: "case",
                render: (_, m) =>
                  m.disposition.case_id ? (
                    <Link
                      href={`/sales/${m.disposition.case_kind === "quote" ? "quotes" : "orders"}/${m.disposition.case_id}`}
                    >
                      {m.disposition.case_kind === "quote"
                        ? "Mở báo giá"
                        : "Mở đơn hàng"}
                    </Link>
                  ) : (
                    ""
                  ),
              },
              {
                title: "DW1",
                key: "process",
                fixed: "right",
                render: (_, m) =>
                  m.disposition.kind === "not_yet_processed" ? (
                    <GuardedButton
                      size="small"
                      inlineReason={false}
                      reason={processReason}
                      loading={pending === `inbox/${m.message_id}`}
                      onClick={() => processOne(m)}
                      aria-label={`DW xử lý thư ${m.message_id}`}
                    >
                      DW xử lý
                    </GuardedButton>
                  ) : m.disposition.processed_at ? (
                    <Typography.Text>
                      {formatDateTime(m.disposition.processed_at, {
                        zoneLabel: false,
                      })}
                    </Typography.Text>
                  ) : null,
              },
            ]}
          />
        </>
      )}
    </div>
  );
}
