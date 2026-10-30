"use client";

import { useState } from "react";
import { Space, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../../lib/auth/auth-context";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { DraftedMail } from "../../_components/drafted-mail";
import { GuardedButton } from "../../_components/guarded-button";

type Draft = SalesSchemas["FollowupDraftView"];

/**
 * Q12's question to the customer (AI item 11): DW1 drafts it on request, with
 * no price, to the customer's contacts in the master data. Nothing is sent
 * (`DraftedMail`).
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

  if (draft?.status === "drafted") return <DraftedMail draft={draft} />;
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
