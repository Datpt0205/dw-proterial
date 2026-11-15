"use client";

import { useState } from "react";
import { Button, Flex, Space, Typography } from "antd";
import type { ReplyDraft, ReplyKind } from "@dw/api-client";
import { useAuth } from "../../../../lib/auth/auth-context";
import { ActionError } from "../../_lib/errors";
import { salesApi } from "../../_lib/api";
import { DraftedMail } from "../../_components/drafted-mail";
import { GuardedButton } from "../../_components/guarded-button";

/** The template drafts the model may word beside (ticket 32). */
export const AGENT_KINDS: ReadonlySet<string> = new Set<ReplyKind>([
  "confirmation_draft",
  "change_can_do_draft",
  "change_options_draft",
]);

const REFUSAL: Record<NonNullable<ReplyDraft["refusal"]>, string> = {
  figure: "có con số không có trong hồ sơ",
  amount: "có số tiền",
  address: "có địa chỉ thư hoặc đường link",
};

/**
 * "Bản AI soạn" (ticket 32): the model's wording of a mail to the customer,
 * beside the template's draft of the same kind, or, for a customer's
 * question, the only draft. Asked on click. Code checked every figure
 * against the order, refused any amount or address, and chose the
 * recipients; a refused draft says why, the figures on click. Nothing is
 * sent: the person opens it in their own mail program (`DraftedMail`).
 */
export function AgentReply({
  caseId,
  kind,
  messageId,
}: {
  caseId: string;
  kind: ReplyKind;
  /** The customer's mail an answer is to (`question_answer` only). */
  messageId?: string;
}) {
  const { hasScope } = useAuth();
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<ReplyDraft | null>(null);
  const [error, setError] = useState<unknown>(null);
  const reason = hasScope("sales.order.prepare")
    ? null
    : "Chỉ Sales phụ trách đơn hàng mới nhờ DW1 soạn được.";

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      setView(await salesApi().replyDraft(caseId, kind, messageId));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Flex vertical gap={6} className="w-full">
      <div>
        <GuardedButton
          size="small"
          reason={reason}
          loading={busy}
          onClick={() => void ask()}
        >
          {view ? "AI soạn lại" : "Bản AI soạn"}
        </GuardedButton>
      </div>
      {view ? (
        <Outcome view={view} fallback={kind !== "question_answer"} />
      ) : null}
      <ActionError error={error} />
    </Flex>
  );
}

function Outcome({ view, fallback }: { view: ReplyDraft; fallback: boolean }) {
  const instead = fallback
    ? "Dùng thư nháp theo mẫu."
    : "Sales tự trả lời khách.";
  if (view.status === "drafted")
    return (
      <Space orientation="vertical" size={4} className="w-full">
        <DraftedMail draft={view} />
        <Typography.Text type="secondary">
          DW1 đã kiểm: {view.figures_checked} con số đều có trong hồ sơ, không
          có số tiền.
        </Typography.Text>
      </Space>
    );
  if (view.status === "refused")
    return <Refused view={view} instead={instead} />;
  return (
    <Typography.Text role="status">
      {view.status === "off"
        ? "Công ty chưa bật bước AI soạn thư, hoặc bước chưa đạt chuẩn đo."
        : "DW1 chưa soạn được lúc này: máy chưa có mô hình hoặc mô hình không trả lời."}{" "}
      {instead}
    </Typography.Text>
  );
}

function Refused({ view, instead }: { view: ReplyDraft; instead: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Space orientation="vertical" size={2}>
      <Typography.Text role="status">
        DW1 bỏ bản AI soạn vì{" "}
        {view.refusal ? REFUSAL[view.refusal] : "không qua kiểm"}. {instead}
      </Typography.Text>
      {view.unsupported.length ? (
        open ? (
          <Typography.Text type="secondary">
            Số không có trong hồ sơ: {view.unsupported.join(", ")}
          </Typography.Text>
        ) : (
          <Button
            type="link"
            size="small"
            className="p-0!"
            onClick={() => setOpen(true)}
          >
            Xem số không khớp
          </Button>
        )
      ) : null}
    </Space>
  );
}
