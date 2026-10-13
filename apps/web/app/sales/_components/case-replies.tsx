"use client";

import Link from "next/link";
import { Card, Space, Typography } from "antd";
import { MailOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";
import { formatDateTime } from "../../../lib/dates";
import { label, REPLY_KIND, REPLY_STEP } from "../_lib/labels";

type Reply = SalesSchemas["CaseReplyView"];

/**
 * The customer's replies the mail thread attached to this case (ticket 32):
 * each with what a model read it as and the sentences code found in it, and
 * the newest one's proposed step. A proposal is a suggestion: the step is the
 * case's ordinary one, marked in "Bước tiếp theo", and nothing happens until
 * Sales presses it.
 */
export function CaseReplies({ replies }: { replies: readonly Reply[] }) {
  if (!replies.length) return null;
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
        {replies.map((reply) => (
          <ReplyRow key={reply.message_id} reply={reply} />
        ))}
      </Space>
    </Card>
  );
}

function ReplyRow({ reply }: { reply: Reply }) {
  return (
    <div className="space-y-1">
      <Space wrap size="small">
        <Link
          href={`/sales/inbox?message=${encodeURIComponent(reply.message_id)}`}
        >
          Thư {reply.message_id}
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
