"use client";

import Link from "next/link";
import { Card, Space, Typography } from "antd";
import { MailOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";
import { formatDateTime } from "../../../lib/dates";
import { label, REPLY_KIND, REPLY_STEP } from "../_lib/labels";
import { messageRef } from "../_lib/messages";

type Reply = SalesSchemas["CaseReplyView"];
type Earlier = SalesSchemas["ThreadMessageView"];

/**
 * The case's mail thread (tickets 32 and 24): the customer's mails before the
 * case opened ("Trao đổi trước PO", each opening in the inbox), then the
 * replies the thread attached to it, each with what a model read it as and
 * the sentences code found in it, and the newest one's proposed step. A
 * proposal is a suggestion: the step is the case's ordinary one, marked in
 * "Bước tiếp theo", and nothing happens until Sales presses it.
 */
export function CaseReplies({
  replies,
  before = [],
  beforeTitle = "Trao đổi trước PO",
}: {
  replies: readonly Reply[];
  before?: readonly Earlier[];
  beforeTitle?: string;
}) {
  if (!replies.length && !before.length) return null;
  return (
    <Card
      size="small"
      title={
        <span>
          <MailOutlined aria-hidden /> Khách trả lời trong luồng thư
        </span>
      }
    >
      <Space orientation="vertical" className="w-full" size="middle">
        {before.length ? (
          <section aria-label={beforeTitle} className="space-y-1">
            <Typography.Text strong>{beforeTitle}</Typography.Text>
            {before.map((mail) => (
              <EarlierRow key={mail.message_id} mail={mail} />
            ))}
          </section>
        ) : null}
        {replies.map((reply) => (
          <ReplyRow key={reply.message_id} reply={reply} />
        ))}
      </Space>
    </Card>
  );
}

function EarlierRow({ mail }: { mail: Earlier }) {
  return (
    <Space wrap size="small" className="w-full">
      <Link
        href={`/sales/inbox?message=${encodeURIComponent(mail.message_id)}`}
      >
        Thư {messageRef(mail.message_id)}
      </Link>
      <Typography.Text type="secondary">
        {formatDateTime(mail.received_at)} · {mail.sender}
      </Typography.Text>
      <Typography.Text
        ellipsis={{ tooltip: mail.subject }}
        className="max-w-md"
      >
        {mail.subject}
      </Typography.Text>
    </Space>
  );
}

function ReplyRow({ reply }: { reply: Reply }) {
  return (
    <div className="space-y-1">
      <Space wrap size="small">
        <Link
          href={`/sales/inbox?message=${encodeURIComponent(reply.message_id)}`}
        >
          Thư {messageRef(reply.message_id)}
        </Link>
        <Typography.Text type="secondary">
          DW1 nhận lúc {formatDateTime(reply.processed_at)} · trả lời thư{" "}
          {reply.linked_to}
        </Typography.Text>
        <ReadingTag reply={reply} />
      </Space>
      {reply.quotes.length ? (
        <ul className="m-0 pl-5" aria-label="Câu khách viết mà mô hình dựa vào">
          {reply.quotes.map((quote) => (
            <li key={quote}>
              <Typography.Text italic>“{quote}”</Typography.Text>
            </li>
          ))}
        </ul>
      ) : null}
      {reply.proposal ? (
        <Typography.Paragraph className="!mb-0" role="note">
          <Typography.Text strong>DW1 đề xuất: </Typography.Text>
          {label(REPLY_STEP, reply.proposal)}. Đọc câu khách viết ở trên rồi tự
          quyết: nút tương ứng ở “Bước tiếp theo” được đánh dấu “đề xuất”, DW1
          không tự làm bước này.
        </Typography.Paragraph>
      ) : null}
    </div>
  );
}

function ReadingTag({ reply }: { reply: Reply }) {
  if (reply.outcome === null && reply.picked_by)
    return <StatusTag tone="unk">Sales chọn hồ sơ: chưa đọc</StatusTag>;
  if (reply.outcome === null)
    return <StatusTag tone="unk">Chưa đọc: bước mô hình đang tắt</StatusTag>;
  if (reply.outcome !== "read" || !reply.kind)
    return (
      <StatusTag tone="unk">Mô hình không đọc được: Sales đọc thư</StatusTag>
    );
  return (
    <StatusTag tone="warn">
      Mô hình đọc: {label(REPLY_KIND, reply.kind)}
    </StatusTag>
  );
}

/** The action a reply's proposal pre-selects on the case's own buttons. */
export function suggestedStep(
  replies: readonly Reply[],
): Reply["proposal"] | null {
  return replies.at(-1)?.proposal ?? null;
}
