"use client";

import { useState } from "react";
import { Alert, Flex, Input, Select, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { errorMessage } from "../../../lib/error-message";
import { INTENT_KIND } from "../_lib/labels";
import { messageRef } from "../_lib/messages";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { GuardedButton } from "../_components/guarded-button";
import { SCOPE } from "../_components/sales-frame";

type Message = SalesSchemas["InboxMessageView"];
type Kind = NonNullable<SalesSchemas["HandledRequest"]["kind"]>;

const KINDS = Object.entries(INTENT_KIND).map(([value, label]) => ({
  value: value as Kind,
  label,
}));

/** The PICs' pool, as a routed message names it (`SALES_PIC_POOL`). */
const POOL = "role:sales_pic";
/** The longest note the API takes (`HANDLED_NOTE_MAX`). */
const NOTE_MAX = 500;

/**
 * A message routed to Sales, closed by a person once they have dealt with
 * it outside DW1 (2026-10-27): "Đánh dấu đã xử lý" with an optional note, and
 * "Mở lại" to undo. It leaves Việc cần làm and stays here, saying who and
 * when. Who may is whoever Việc cần làm shows it to (its PIC, any PIC for the
 * pool's) and the head; the server decides the same and refuses anyone else.
 */
export function HandledPanel({
  message,
  onChanged,
}: {
  message: Message;
  onChanged: () => void;
}) {
  const { hasScope, email } = useAuth();
  const name = usePeople();
  const { run, pending } = useAction();
  const [note, setNote] = useState("");
  // What the mail was, one optional click (ticket 67): it teaches DW1, it
  // routes nothing.
  const [kind, setKind] = useState<Kind | null>(null);
  const [error, setError] = useState<unknown>(null);
  const d = message.disposition;
  const owner = (d.owner ?? "").toLowerCase();
  const ref = messageRef(message.message_id);
  const allowed =
    (hasScope(SCOPE.inbox) &&
      (owner === POOL || owner === (email ?? "").toLowerCase())) ||
    hasScope(SCOPE.assign);
  const reason = allowed
    ? null
    : "Thư này giao cho người khác: người phụ trách hoặc trưởng nhóm đánh dấu.";
  const id = `handled/${message.message_id}`;

  const after = (result: { ok: boolean; error?: unknown }) => {
    if (result.ok) {
      setError(null);
      setNote("");
      setKind(null);
      onChanged();
    } else setError(result.error);
  };

  if (d.handled_at)
    return (
      <Flex vertical gap={6} className="max-w-xl">
        <Typography.Text>
          Sales đã xử lý: {name(d.handled_by)} lúc{" "}
          {formatDateTime(d.handled_at)}.
        </Typography.Text>
        {d.handled_note ? (
          <Typography.Text>Ghi chú: {d.handled_note}</Typography.Text>
        ) : null}
        {error ? (
          <Alert type="error" showIcon title={errorMessage(error)} />
        ) : null}
        <div>
          <GuardedButton
            reason={reason}
            loading={pending === id}
            aria-label={`Mở lại thư ${ref}`}
            onClick={async () =>
              after(
                await run(
                  id,
                  null,
                  (key) => salesApi().reopenMessage(message.message_id, key),
                  `Đã mở lại thư ${ref}`,
                ),
              )
            }
          >
            Mở lại
          </GuardedButton>
        </div>
      </Flex>
    );

  return (
    <Flex vertical gap={6} className="max-w-xl">
      <Typography.Text>
        Xử lý xong ngoài DW1 (đã trả lời khách, đã chuyển PC/QA, hoặc không cần
        làm gì)? Đánh dấu để thư rời Việc cần làm; thư vẫn nằm ở đây.
      </Typography.Text>
      <Input.TextArea
        aria-label={`Ghi chú khi đánh dấu thư ${ref} đã xử lý`}
        placeholder="Ví dụ: đã gọi khách, hẹn giao lại ngày 30/10"
        autoSize={{ minRows: 1, maxRows: 4 }}
        maxLength={NOTE_MAX}
        value={note}
        disabled={reason !== null}
        onChange={(e) => setNote(e.target.value)}
      />
      <Flex vertical gap={2}>
        <Typography.Text id={`kind-${message.message_id}`}>
          Thư này là (không bắt buộc, giúp DW1 học phân loại thư)
        </Typography.Text>
        <Select<Kind>
          aria-labelledby={`kind-${message.message_id}`}
          allowClear
          placeholder="Chọn loại thư"
          options={KINDS}
          value={kind ?? undefined}
          disabled={reason !== null}
          onChange={(value) => setKind(value ?? null)}
          className="max-w-xs"
        />
      </Flex>
      {error ? (
        <Alert type="error" showIcon title={errorMessage(error)} />
      ) : null}
      <div>
        <GuardedButton
          type="primary"
          reason={reason}
          loading={pending === id}
          aria-label={`Đánh dấu thư ${ref} đã xử lý`}
          onClick={async () =>
            after(
              await run(
                id,
                { note, kind },
                (key) =>
                  salesApi().markHandled(
                    message.message_id,
                    note.trim() || null,
                    key,
                    kind,
                  ),
                `Đã đánh dấu thư ${ref} đã xử lý`,
              ),
            )
          }
        >
          Đánh dấu đã xử lý
        </GuardedButton>
      </div>
    </Flex>
  );
}
