"use client";

import { useEffect, useState } from "react";
import { Alert, Flex, Select, Space, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../lib/auth/auth-context";
import { salesApi } from "../_lib/api";
import { messageRef } from "../_lib/messages";
import { useAction } from "../_lib/use-action";
import { ActionError } from "../_lib/errors";
import { GuardedButton } from "../_components/guarded-button";
import { SCOPE } from "../_components/sales-frame";

type Suggestion = SalesSchemas["SenderCustomerView"];
type Customer = SalesSchemas["CustomerView"];

/**
 * A mail routed `customer_unknown` (AI item 5): DW1 reads, as soon as the
 * row opens, which customer wrote it, and shows the words in the mail it
 * rests on. Sales confirms it, or picks another customer; the sender's
 * address is then kept as that customer's and the mail processed again.
 * Nothing is recorded until Sales presses.
 */
export function SenderCustomerPanel({
  messageId,
  onConfirmed,
}: {
  messageId: string;
  onConfirmed: () => void;
}) {
  const { hasScope } = useAuth();
  const { run, pending } = useAction();
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const allowed = hasScope(SCOPE.inbox);
  const reason = allowed ? null : "Chỉ người xử lý thư mới xác nhận được khách.";
  const ref = messageRef(messageId);
  const id = `sender/${messageId}`;

  useEffect(() => {
    if (!allowed) return;
    let live = true;
    salesApi()
      .senderCustomer(messageId)
      .then((view) => live && setSuggestion(view))
      .catch((e: unknown) => live && setError(e));
    salesApi()
      .customers()
      .then((page) => live && setCustomers(page.items))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [allowed, messageId]);

  const confirm = async (code: string) => {
    const result = await run(
      id,
      { code },
      (key) => salesApi().confirmSenderCustomer(messageId, code, key),
      `Đã ghi nhớ người gửi thư ${ref} là khách ${code}; DW1 đang xử lý lại`,
    );
    if (result.ok) {
      setError(null);
      onConfirmed();
    } else setError(result.error);
  };

  const suggested = suggestion?.status === "suggested" ? suggestion : null;
  return (
    <Flex vertical gap={6} className="max-w-xl">
      {suggested ? (
        <Alert
          type="info"
          showIcon
          role="status"
          title={
            <Space wrap>
              <span>
                DW1 đoán thư này của khách {suggested.customer_name} (
                {suggested.customer_code})
              </span>
              <Tag>Máy đoán</Tag>
            </Space>
          }
          description={
            <Typography.Text>
              Căn cứ trong thư: “{suggested.evidence}”
            </Typography.Text>
          }
        />
      ) : suggestion ? (
        <Typography.Text role="status">
          {suggestion.status === "unavailable"
            ? "DW1 chưa đọc được thư này lúc này: máy chưa có mô hình hoặc mô hình không trả lời."
            : suggestion.evidence
              ? `Thư ký tên “${suggestion.evidence}”, không khớp khách nào trong danh sách: có thể là khách mới.`
              : "DW1 không thấy thư nêu khách nào trong danh sách."}
        </Typography.Text>
      ) : null}
      <Space wrap>
        {suggested?.customer_code ? (
          <GuardedButton
            type="primary"
            reason={reason}
            loading={pending === id}
            aria-label={`Xác nhận thư ${ref} của khách ${suggested.customer_code}`}
            onClick={() => void confirm(suggested.customer_code!)}
          >
            Đúng, ghi nhớ và xử lý lại
          </GuardedButton>
        ) : null}
        <Select
          className="min-w-64"
          showSearch
          optionFilterProp="label"
          placeholder="Hoặc chọn khách khác"
          aria-label={`Chọn khách cho thư ${ref}`}
          disabled={reason !== null}
          value={picked}
          onChange={setPicked}
          options={customers.map((c) => ({
            value: c.code,
            label: `${c.code} · ${c.name}`,
          }))}
        />
        {picked ? (
          <GuardedButton
            reason={reason}
            loading={pending === id}
            aria-label={`Ghi nhớ thư ${ref} của khách ${picked}`}
            onClick={() => void confirm(picked)}
          >
            Ghi nhớ và xử lý lại
          </GuardedButton>
        ) : null}
      </Space>
      <ActionError error={error} />
    </Flex>
  );
}
