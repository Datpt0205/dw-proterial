"use client";

import { useState } from "react";
import Link from "next/link";
import { Flex, Space, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../lib/auth/auth-context";
import { salesApi } from "../_lib/api";
import { label, CASE_KIND } from "../_lib/labels";
import { messageRef } from "../_lib/messages";
import { useAction } from "../_lib/use-action";
import { ActionError } from "../_lib/errors";
import { GuardedButton } from "../_components/guarded-button";
import { SCOPE } from "../_components/sales-frame";

type Offered = SalesSchemas["ThreadCaseView"];

/**
 * "Chọn hồ sơ" (ticket 24): a reply whose mail thread holds several of the
 * customer's cases and names none of them. DW1 does not guess; Sales opens a
 * case if needed and picks the one the reply is about, and only one of those
 * offered (the server refuses any other). Picking attaches the reply to it.
 */
export function ThreadCasesPanel({
  messageId,
  offered,
  onPicked,
}: {
  messageId: string;
  offered: readonly Offered[];
  onPicked: () => void;
}) {
  const { hasScope } = useAuth();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const reason = hasScope(SCOPE.inbox)
    ? null
    : "Chỉ người xử lý thư mới chọn được hồ sơ.";
  const ref = messageRef(messageId);

  const pick = async (c: Offered) => {
    const result = await run(
      `thread-case/${messageId}`,
      { case_id: c.case_id },
      (key) => salesApi().pickThreadCase(messageId, c.case_id, key),
      `Đã gắn thư ${ref} vào hồ sơ ${c.number}`,
    );
    if (result.ok) {
      setError(null);
      onPicked();
    } else setError(result.error);
  };

  return (
    <Flex vertical gap={6}>
      <Typography.Text strong>Chọn hồ sơ</Typography.Text>
      <Space wrap>
        {offered.map((c) => (
          <Space key={c.case_id} size="small">
            <Link
              href={`/sales/${c.case_kind === "quote" ? "quotes" : "orders"}/${c.case_id}`}
            >
              {label(CASE_KIND, c.case_kind)} {c.number}
            </Link>
            <GuardedButton
              reason={reason}
              loading={pending === `thread-case/${messageId}`}
              aria-label={`Gắn thư ${ref} vào hồ sơ ${c.number}`}
              onClick={() => void pick(c)}
            >
              Chọn
            </GuardedButton>
          </Space>
        ))}
      </Space>
      <ActionError error={error} />
    </Flex>
  );
}
