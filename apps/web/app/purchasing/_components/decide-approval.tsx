"use client";

import { useState } from "react";
import { App, Button, Flex, Input, Tooltip, Typography } from "antd";
import { CheckOutlined, CloseOutlined } from "@ant-design/icons";
import type { Approval } from "@dw/api-client";
import { apiClient } from "../../../lib/session";
import { errorMessage } from "../../../lib/error-message";
import { useIdempotencyKeys } from "../../../lib/idempotency";

/**
 * One approval decided with one press: the reason the strict `purchasing.`
 * approvals require, then "Duyệt" or "Từ chối". Whether the viewer may
 * decide is the server's `can_decide` (a maker of the case, or someone
 * without the tier the approval stamped, is refused there), never inferred
 * here. `subjectVersion` binds the decision to the case the person was shown:
 * a case that moved since is refused (409) and the page reloads.
 */
export function DecideApproval({
  approval,
  subjectVersion,
  what,
  onDecided,
}: {
  approval: Approval;
  subjectVersion?: number;
  /** What is decided, as the button's accessible name carries it. */
  what: string;
  onDecided: () => void;
}) {
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [comment, setComment] = useState("");
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);

  const why = !approval.can_decide
    ? approval.requested_by_me
      ? "Bạn đã làm hồ sơ này nên không tự duyệt được (tách nhiệm)."
      : "Bạn không giữ quyền duyệt bậc này."
    : approval.requires_comment && !comment.trim()
      ? "Ghi lý do trước khi quyết định: phê duyệt mua hàng cần lý do."
      : null;

  async function decide(approve: boolean) {
    const body = {
      approve,
      comment: comment.trim() || undefined,
      subject_version: subjectVersion,
    };
    const id = `decide:${approval.id}`;
    setPending(approve ? "approve" : "reject");
    try {
      await apiClient().decideApproval(
        approval.id,
        body,
        keys.keyFor(id, body),
      );
      keys.settle(id);
      message.success(approve ? `Đã duyệt ${what}` : `Đã từ chối ${what}`);
      onDecided();
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setPending(null);
    }
  }

  return (
    <Flex vertical gap={8}>
      {approval.can_decide ? (
        <Input.TextArea
          aria-label={`Lý do quyết định ${what}`}
          placeholder="Ví dụ: đúng nhu cầu, giá trong hạn mức"
          autoSize={{ minRows: 1, maxRows: 4 }}
          maxLength={1000}
          value={comment}
          onChange={(event) => setComment(event.target.value)}
        />
      ) : null}
      <Flex gap={8} wrap align="center">
        <Tooltip title={why}>
          <Button
            type="primary"
            size="large"
            icon={<CheckOutlined aria-hidden />}
            aria-label={`Duyệt ${what}`}
            disabled={why !== null || pending !== null}
            loading={pending === "approve"}
            onClick={() => void decide(true)}
          >
            Duyệt
          </Button>
        </Tooltip>
        <Tooltip title={why}>
          <Button
            danger
            size="large"
            icon={<CloseOutlined aria-hidden />}
            aria-label={`Từ chối ${what}`}
            disabled={why !== null || pending !== null}
            loading={pending === "reject"}
            onClick={() => void decide(false)}
          >
            Từ chối
          </Button>
        </Tooltip>
        {why ? <Typography.Text role="note">{why}</Typography.Text> : null}
      </Flex>
    </Flex>
  );
}
