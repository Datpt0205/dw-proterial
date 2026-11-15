"use client";

import Link from "next/link";
import { Card, Space, Typography } from "antd";
import { MailOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";
import { formatDateTime } from "../../../lib/dates";
import {
  AGENT_FALLBACK,
  label,
  REPLY_STEP,
  THREAD_INTENT,
} from "../_lib/labels";
import { messageRef } from "../_lib/messages";

type Reply = SalesSchemas["CaseReplyView"];
type Sent = SalesSchemas["SentMessageView"];
type Earlier = SalesSchemas["ThreadMessageView"];
type Intent = SalesSchemas["IntentView"];
type Proposal = Reply["proposal"];

/**
 * The case's mail thread (tickets 32, 24, 25 and 26): the customer's mails
 * before the case opened ("Trao đổi trước PO", each opening in the inbox),
 * the replies the thread attached to it and the mails Sales sent on it
 * ("Sales gửi"), each with the intents a model read in it and the sentences
 * code found for each, and the newest one's proposed step. A proposal is a
 * suggestion: the step is the case's ordinary one, marked in "Bước tiếp
 * theo", and nothing happens until Sales presses it.
 */
export function CaseReplies({
  replies,
  sent = [],
  before = [],
  beforeTitle = "Trao đổi trước PO",
}: {
  replies: readonly Reply[];
  sent?: readonly Sent[];
  before?: readonly Earlier[];
  beforeTitle?: string;
}) {
  if (!replies.length && !before.length && !sent.length) return null;
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
        {talk(replies, sent).map((item) =>
          item.kind === "reply" ? (
            <ReplyRow key={item.reply.message_id} reply={item.reply} />
          ) : (
            <SentRow key={item.sent.message_id} sent={item.sent} />
          ),
        )}
      </Space>
    </Card>
  );
}

type Talk = { kind: "reply"; reply: Reply } | { kind: "sent"; sent: Sent };

/** Replies and Sales' mails in the order they came. */
function talk(replies: readonly Reply[], sent: readonly Sent[]): Talk[] {
  const items: [string, Talk][] = [
    ...replies.map((reply): [string, Talk] => [
      reply.processed_at,
      { kind: "reply", reply },
    ]),
    ...sent.map((mail): [string, Talk] => [
      mail.received_at,
      { kind: "sent", sent: mail },
    ]),
  ];
  return items
    .sort((a, b) => Date.parse(a[0]) - Date.parse(b[0]))
    .map(([, item]) => item);
}

function EarlierRow({ mail }: { mail: Earlier }) {
  return (
    <Space wrap size="small" className="w-full">
      <MessageLink id={mail.message_id} />
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

function MessageLink({ id }: { id: string }) {
  return (
    <Link href={`/sales/inbox?message=${encodeURIComponent(id)}`}>
      Thư {messageRef(id)}
    </Link>
  );
}

function ReplyRow({ reply }: { reply: Reply }) {
  return (
    <div className="space-y-1">
      <Space wrap size="small">
        <MessageLink id={reply.message_id} />
        <Typography.Text type="secondary">
          DW1 nhận lúc {formatDateTime(reply.processed_at)} · trả lời thư{" "}
          {reply.linked_to}
        </Typography.Text>
        <ReadingTag
          outcome={reply.outcome}
          intents={reply.intents}
          off={
            reply.picked_by
              ? "Sales chọn hồ sơ: chưa đọc"
              : "Chưa đọc: bước mô hình đang tắt"
          }
        />
      </Space>
      <FallbackNote fallback={reply.fallback} />
      <Quotes intents={reply.intents} who="khách" />
      <ProposalNote proposal={reply.proposal} />
    </div>
  );
}

function SentRow({ sent }: { sent: Sent }) {
  return (
    <div className="space-y-1">
      <Space wrap size="small">
        <StatusTag tone="pri">Sales gửi</StatusTag>
        <MessageLink id={sent.message_id} />
        <Typography.Text type="secondary">
          {formatDateTime(sent.received_at)}
        </Typography.Text>
        <Typography.Text
          ellipsis={{ tooltip: sent.subject }}
          className="max-w-md"
        >
          {sent.subject}
        </Typography.Text>
        {sent.outcome ? (
          <ReadingTag outcome={sent.outcome} intents={sent.intents} off="" />
        ) : null}
      </Space>
      <FallbackNote fallback={sent.fallback} />
      <Quotes intents={sent.intents} who="Sales" />
      <ProposalNote proposal={sent.proposal} />
    </div>
  );
}

function Quotes({ intents, who }: { intents: readonly Intent[]; who: string }) {
  const quoted = intents.filter((i) => i.quotes.length);
  if (!quoted.length) return null;
  return (
    <ul className="m-0 pl-5" aria-label={`Câu ${who} viết mà mô hình dựa vào`}>
      {quoted.flatMap((i) =>
        i.quotes.map((quote) => (
          <li key={`${i.intent}:${quote}`}>
            {label(THREAD_INTENT, i.intent)}:{" "}
            <Typography.Text italic>“{quote}”</Typography.Text>
          </li>
        )),
      )}
    </ul>
  );
}

/** The thread agent was asked first and gave no reading: why, in one line. */
function FallbackNote({ fallback }: { fallback?: Reply["fallback"] }) {
  if (!fallback) return null;
  return (
    <Typography.Text type="secondary" role="note">
      DW1 tra cứu thêm không xong ({label(AGENT_FALLBACK, fallback)}): đọc
      một lần như bình thường.
    </Typography.Text>
  );
}

function ProposalNote({ proposal }: { proposal: Proposal }) {
  if (!proposal) return null;
  return (
    <Typography.Paragraph className="!mb-0" role="note">
      <Typography.Text strong>DW1 đề xuất: </Typography.Text>
      {label(REPLY_STEP, proposal)}. Đọc câu trích ở trên rồi tự quyết: nút
      tương ứng ở “Bước tiếp theo” được đánh dấu “đề xuất”, DW1 không tự làm
      bước này.
    </Typography.Paragraph>
  );
}

function ReadingTag({
  outcome,
  intents,
  off,
}: {
  outcome: Reply["outcome"];
  intents: readonly Intent[];
  off: string;
}) {
  if (outcome === null) return <StatusTag tone="unk">{off}</StatusTag>;
  if (outcome !== "read" || !intents.length)
    return (
      <StatusTag tone="unk">Mô hình không đọc được: Sales đọc thư</StatusTag>
    );
  return (
    <StatusTag tone="warn">
      Mô hình đọc:{" "}
      {intents.map((i) => label(THREAD_INTENT, i.intent)).join(", ")}
    </StatusTag>
  );
}

/**
 * The action the thread's proposal pre-selects on the case's own buttons:
 * the newest message's, a reply or one Sales sent (the server proposes on
 * one of them at most).
 */
export function suggestedStep(
  replies: readonly Reply[],
  sent: readonly Sent[] = [],
): Proposal | null {
  return (
    [...replies, ...sent].find((message) => message.proposal)?.proposal ?? null
  );
}
