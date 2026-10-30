"use client";

import { MailOutlined } from "@ant-design/icons";
import { Alert, Button, Flex, Space, Tag, Typography } from "antd";

/** A mail the model drafted for a person to send: code chose `to`. */
export type Drafted = {
  to: string[];
  subject?: string | null;
  body?: string | null;
};

/** The longest `mailto:` link mail programs reliably open. */
const MAILTO_MAX = 1900;

/** The draft as a `mailto:` link the person's own mail program opens. */
export function mailtoOf(draft: Drafted): string | null {
  if (!draft.subject || !draft.body || !draft.to.length) return null;
  const link =
    `mailto:${draft.to.map(encodeURIComponent).join(",")}` +
    `?subject=${encodeURIComponent(draft.subject)}` +
    `&body=${encodeURIComponent(draft.body)}`;
  return link.length <= MAILTO_MAX ? link : null;
}

/**
 * A drafted mail to a customer (Q12's question, a reminder), marked as the
 * machine's. Nothing is sent: "Mở trong Outlook" opens it in the person's own
 * mail program to read, change and send from their own mailbox; "Sao chép
 * thư" when the mail is too long for a link.
 */
export function DraftedMail({ draft }: { draft: Drafted }) {
  const mailto = mailtoOf(draft);
  return (
    <Flex vertical gap={6} className="max-w-xl">
      <Alert
        type="info"
        showIcon
        role="status"
        title={
          <Space wrap>
            <span>{draft.subject}</span>
            <Tag>Máy viết</Tag>
          </Space>
        }
        description={
          <Flex vertical gap={4}>
            <Typography.Text>Gửi tới: {draft.to.join(", ")}</Typography.Text>
            <Typography.Paragraph className="mb-0! whitespace-pre-wrap">
              {draft.body}
            </Typography.Paragraph>
          </Flex>
        }
      />
      <Space wrap>
        {mailto ? (
          <Button
            type="primary"
            icon={<MailOutlined aria-hidden />}
            href={mailto}
          >
            Mở trong Outlook
          </Button>
        ) : null}
        <Button
          onClick={() =>
            void navigator.clipboard.writeText(
              `${draft.subject}\n\n${draft.body}`,
            )
          }
        >
          Sao chép thư
        </Button>
      </Space>
    </Flex>
  );
}
