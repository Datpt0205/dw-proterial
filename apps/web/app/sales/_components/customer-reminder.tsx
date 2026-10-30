"use client";

import { useState } from "react";
import { Card, Space, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDate } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { DraftedMail } from "./drafted-mail";
import { GuardedButton } from "./guarded-button";

type Reminder = SalesSchemas["CustomerReminderView"];

const WAITS = {
  order: {
    scope: "sales.order.prepare",
    what: "PO đã sửa",
    who: "Chỉ Sales phụ trách đơn hàng mới soạn được thư nhắc khách.",
  },
  quote: {
    scope: "sales.quote.prepare",
    what: "câu trả lời về spec",
    who: "Chỉ Sales phụ trách báo giá mới soạn được thư nhắc khách.",
  },
} as const;

/**
 * A reminder to the customer this case waits on (DW01 function 4): DW1
 * drafts it on request, with no amount, to the customer's contacts in the
 * master data. Drawn only while the case waits on the customer; nothing is
 * sent (`DraftedMail`).
 */
export function CustomerReminder({
  kind,
  caseId,
}: {
  kind: "order" | "quote";
  caseId: string;
}) {
  const { hasScope } = useAuth();
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<Reminder | null>(null);
  const [error, setError] = useState<unknown>(null);
  const wait = WAITS[kind];
  const reason = hasScope(wait.scope) ? null : wait.who;

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      setView(await salesApi().customerReminder(kind, caseId));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      size="small"
      title="Nhắc khách"
      extra={
        <GuardedButton
          size="small"
          reason={reason}
          loading={busy}
          onClick={() => void ask()}
        >
          {view ? "Soạn lại" : "DW1 soạn thư nhắc khách"}
        </GuardedButton>
      }
    >
      {view?.status === "drafted" ? (
        <Space orientation="vertical" size={4}>
          <Typography.Text>
            Khách được hỏi từ {formatDate(view.asked_on)}.
          </Typography.Text>
          <DraftedMail draft={view} />
        </Space>
      ) : view ? (
        <Typography.Text role="status">
          {view.status === "unavailable"
            ? "DW1 chưa soạn được lúc này: máy chưa có mô hình hoặc mô hình không trả lời."
            : "DW1 viết một con số hoặc một số tiền không có trong hồ sơ nên thư bị bỏ; bấm lại để thử."}
        </Typography.Text>
      ) : (
        <Typography.Text>
          Hồ sơ đang chờ khách gửi {wait.what}. DW1 soạn thư nhắc bằng ngôn ngữ
          của khách, không có số tiền; bạn đọc, sửa rồi gửi từ hộp thư của mình.
        </Typography.Text>
      )}
      <ActionError error={error} />
    </Card>
  );
}
