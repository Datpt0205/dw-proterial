"use client";

import { useCallback, useEffect, useState } from "react";
import { SendOutlined } from "@ant-design/icons";
import { App, Flex, Typography } from "antd";
import type { Artifact, SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { ARTIFACT_KIND, label } from "../_lib/labels";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { GuardedButton } from "./guarded-button";

type Mail = SalesSchemas["OutboundMailView"];

/** The drafts each case may send from the viewer's mailbox: every mail DW1
 * drafts to the customer (`SENDABLE`, ticket 76) and the requests to Design
 * and PC, which go only to that team's mailboxes in the tenant's rules
 * (`INTERNAL_SENDABLE`, 77). */
export const SENDABLE: Record<"order" | "quote", readonly string[]> = {
  order: [
    "confirmation_draft",
    "correction_request",
    "change_can_do_draft",
    "change_options_draft",
    "internal_change_notice",
    "cannot_supply_draft",
    "design_code_request",
    "pc_request_draft",
  ],
  quote: [
    "send_draft",
    "spec_discussion_draft",
    "decline_draft",
    "design_request_draft",
  ],
};

const PREPARE: Record<"order" | "quote", string> = {
  order: "sales.order.prepare",
  quote: "sales.quote.prepare",
};

/** Why a mail did not go, in words (`OutboundError`). */
const WHY: Record<NonNullable<Mail["error"]>, string> = {
  not_connected:
    "hộp thư của bạn chưa được nối để DW1 gửi. Tải tệp .eml và gửi từ Outlook.",
  write_failed: "DW1 không ghi được thư vào thư mục gửi. Bấm gửi lại.",
  flow_failed:
    "luồng gửi thư báo lỗi. Kiểm tra kết nối Power Automate, hoặc gửi tệp .eml từ Outlook.",
  no_receipt:
    "quá 30 phút chưa có xác nhận đã gửi. Xem mục Thư đã gửi trong Outlook trước khi gửi lại.",
  gone: "thư nháp không còn. Soạn lại rồi gửi.",
};

function said(mail: Mail): string {
  switch (mail.status) {
    case "queued":
      return `Đang chờ gửi từ ${mail.mailbox}…`;
    case "written":
      return `Đã chuyển cho luồng gửi của ${mail.mailbox}, đang chờ xác nhận…`;
    case "sent":
      return `Đã gửi từ ${mail.mailbox} lúc ${formatDateTime(mail.settled_at ?? mail.queued_at)}.`;
    default:
      return `Chưa gửi được: ${mail.error ? WHY[mail.error] : "không rõ lý do."}`;
  }
}

/**
 * "Gửi cho khách" (2026-10-29): one of the case's customer drafts sent from
 * the viewer's own mailbox, through their outbox folder and their own Power
 * Automate flow. Nothing goes until they press and confirm; where the
 * deployment has no outbox yet, the button says so and the `.eml` stays the
 * way. What it says is this draft's own mail, read again while it travels.
 */
export function OutboundSend({
  kind,
  caseId,
  draftKind,
  draft,
}: {
  kind: "order" | "quote";
  caseId: string;
  /** Which draft this sends (one of `SENDABLE[kind]`). */
  draftKind: string;
  /** That draft at the current version, downloadable; absent: not drafted yet. */
  draft: Artifact | undefined;
}) {
  const { hasScope } = useAuth();
  const { modal } = App.useApp();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const mails = useResource(
    `sales/${kind}/${caseId}/outbound`,
    useCallback(() => salesApi().outbound(kind, caseId), [kind, caseId]),
  );
  const latest = draft
    ? mails.data?.mails.find((m) => m.artifact_id === draft.artifact_id)
    : undefined;
  const travelling =
    latest?.status === "queued" || latest?.status === "written";
  const reload = mails.reload;
  useEffect(() => {
    if (!travelling) return;
    const timer = window.setInterval(reload, 10_000);
    return () => window.clearInterval(timer);
  }, [travelling, reload]);

  if (!mails.data) return null;
  const reason = !mails.data.enabled
    ? "DW1 chưa được nối để gửi thư: tải tệp .eml và gửi từ hộp thư của bạn."
    : !hasScope(PREPARE[kind])
      ? "Chỉ người chuẩn bị hồ sơ mới gửi được thư này."
      : !draft
        ? `Soạn “${label(ARTIFACT_KIND, draftKind)}” ở trên trước.`
        : travelling || latest?.status === "sent"
          ? "Thư này đã được gửi hoặc đang trên đường đi."
          : null;
  const id = `send/${caseId}/${draftKind}`;

  const send = () => {
    if (!draft) return;
    modal.confirm({
      title: `Gửi “${label(ARTIFACT_KIND, draft.kind)}”?`,
      content:
        "Thư đi từ hộp thư Outlook của bạn, tới người nhận ghi trong thư nháp, kèm các tệp đính kèm. Gửi rồi không thu hồi được.",
      okText: "Gửi",
      cancelText: "Chưa gửi",
      autoFocusButton: "cancel",
      onOk: async () => {
        const result = await run(
          id,
          { artifact: draft.artifact_id },
          (key) =>
            salesApi().sendArtifact(
              kind,
              caseId,
              draft.artifact_id,
              draft.case_version,
              key,
            ),
          "Đã chuyển thư cho luồng gửi từ hộp thư của bạn",
        );
        if (result.ok) {
          setError(null);
          reload();
        } else setError(result.error);
      },
    });
  };

  return (
    <Flex vertical gap={6}>
      <Flex wrap gap={8} align="center">
        <GuardedButton
          type="primary"
          icon={<SendOutlined aria-hidden />}
          reason={reason}
          loading={pending === id}
          onClick={send}
        >
          Gửi “{label(ARTIFACT_KIND, draftKind)}” từ hộp thư của bạn
        </GuardedButton>
      </Flex>
      {latest ? (
        <Typography.Text role="status">{said(latest)}</Typography.Text>
      ) : null}
      <ActionError error={error ?? mails.error} />
    </Flex>
  );
}
