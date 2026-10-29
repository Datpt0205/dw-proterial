"use client";

import { useState } from "react";
import { MailOutlined } from "@ant-design/icons";
import { Alert, Button, Flex, Space, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../../lib/auth/auth-context";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { GuardedButton } from "../../_components/guarded-button";

type Draft = SalesSchemas["FollowupDraftView"];

/** The longest `mailto:` link mail programs reliably open. */
const MAILTO_MAX = 1900;

/** The draft as a `mailto:` link the person's own mail program opens. */
export function mailtoOf(draft: Draft): string | null {
  if (!draft.subject || !draft.body || !draft.to.length) return null;
  const link =
    `mailto:${draft.to.map(encodeURIComponent).join(",")}` +
    `?subject=${encodeURIComponent(draft.subject)}` +
    `&body=${encodeURIComponent(draft.body)}`;
  return link.length <= MAILTO_MAX ? link : null;
}

/**
 * Q12's question to the customer (AI item 11): DW1 drafts it on request, with
 * no price, to the customer's contacts in the master data. Nothing is sent:
 * "Mở trong Outlook" opens it in the person's own mail program to read,
 * change and send from their own mailbox; "Sao chép" when the mail is too
 * long for a link.
 */
export function FollowupDraft({
  customerCode,
  prvCode,
}: {
  customerCode: string;
  prvCode: string;
}) {
  const { hasScope } = useAuth();
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<unknown>(null);
  const reason = hasScope("sales.quote.prepare")
    ? null
    : "Chỉ Sales phụ trách báo giá mới soạn được thư hỏi khách.";

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      setDraft(await salesApi().screeningFollowup(customerCode, prvCode));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  if (draft?.status === "drafted") {
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
  return (
    <Space orientation="vertical" size={4}>
      <GuardedButton
        size="small"
        reason={reason}
        loading={busy}
        onClick={() => void ask()}
      >
        DW1 soạn thư hỏi khách
      </GuardedButton>
      {draft ? (
        <Typography.Text role="status">
          {draft.status === "unavailable"
            ? "DW1 chưa soạn được lúc này: máy chưa có mô hình hoặc mô hình không trả lời."
            : "DW1 viết một con số hoặc một số tiền không có trong hồ sơ nên thư bị bỏ; bấm lại để thử."}
        </Typography.Text>
      ) : null}
      <ActionError error={error} />
    </Space>
  );
}
