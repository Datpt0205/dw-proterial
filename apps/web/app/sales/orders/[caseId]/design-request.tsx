"use client";

import { useCallback, useState } from "react";
import { Alert, App, Button, Space, Typography } from "antd";
import { CopyOutlined, MailOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { RegionState, StatusTag } from "@dw/ui";
import { formatDateTime } from "../../../../lib/dates";
import { LoadError } from "../../../../components/load-error";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";

type Order = SalesSchemas["OrderCaseView"];

/**
 * "Đề nghị Design tạo mã" (ticket 06), inside the picker of a line no item
 * fits: the request DW1 drafts to Design (the line as the PO prints it and
 * the item master's three nearest codes), which the person copies into a
 * mail from their own account (DW1 sends nothing); "Ghi đã gửi Design"
 * starts the wait. While it waits, each code Design's mails name that the
 * item master holds is offered to fill the code box: the line maps only when
 * the person confirms it in the picker, which checks it again.
 */
export function DesignRequestPanel({
  order,
  lineNo,
  onUse,
  onChanged,
}: {
  order: Order;
  lineNo: number;
  /** Puts a code Design named in the picker's code box, unconfirmed. */
  onUse: (code: string) => void;
  onChanged: () => void;
}) {
  const name = usePeople();
  const { message } = App.useApp();
  const { run, pending } = useAction();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const waiting = order.design_requests.find((r) => r.line_no === lineNo);
  const draft = useResource(
    `sales/orders/${order.case_id}/lines/${lineNo}/design-request@${order.case_version}`,
    useCallback(
      () => salesApi().designRequest(order.case_id, lineNo),
      [order.case_id, lineNo],
    ),
  );
  const request = draft.data;
  const id = `design/asked/${lineNo}`;

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      message.success("Đã chép: dán vào thư gửi Design");
    } catch {
      message.error("Trình duyệt không cho chép: chọn và chép tay nội dung.");
    }
  };

  const asked = async () => {
    const result = await run(
      id,
      { version: order.case_version, line: lineNo },
      (key) =>
        salesApi().recordDesignAsked(
          order.case_id,
          lineNo,
          order.case_version,
          key,
        ),
      "Đã ghi đã gửi Design",
    );
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };

  return (
    <Space orientation="vertical" className="w-full">
      <Space wrap>
        {waiting ? (
          <span role="status">
            <StatusTag tone="warn">Chờ Design</StatusTag>
            <Typography.Text>
              {name(waiting.by)} đã gửi lúc {formatDateTime(waiting.at)}
            </Typography.Text>
          </span>
        ) : null}
        <Button
          icon={<MailOutlined aria-hidden />}
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          Đề nghị Design tạo mã
        </Button>
      </Space>
      {draft.loading ? <RegionState kind="loading" compact /> : null}
      {draft.error ? (
        <LoadError error={draft.error} onRetry={draft.reload} />
      ) : null}
      {request?.named.length ? (
        <Space orientation="vertical" size={4}>
          <Typography.Text strong>Design nêu trong thư</Typography.Text>
          {request.named.map((n) => (
            <Space key={`${n.message_id}/${n.code}`} wrap>
              <Button size="small" onClick={() => onUse(n.code)}>
                Dùng mã {n.code}
              </Button>
              <Typography.Text type="secondary">
                {n.sender} · {formatDateTime(n.received_at)}
              </Typography.Text>
            </Space>
          ))}
        </Space>
      ) : null}
      {open && request ? (
        <Space orientation="vertical" className="w-full">
          {request.to.length ? (
            <Typography.Text>Gửi: {request.to.join(", ")}</Typography.Text>
          ) : (
            <Alert
              type="warning"
              showIcon
              title="Chưa cấu hình hộp thư của Design (quy tắc báo giá): điền người nhận khi gửi."
            />
          )}
          <Alert
            type="info"
            title={request.subject}
            description={
              <Typography.Paragraph className="mb-0! whitespace-pre-wrap">
                {request.body}
              </Typography.Paragraph>
            }
          />
          <Space wrap>
            <Button
              icon={<CopyOutlined aria-hidden />}
              onClick={() => void copy(`${request.subject}\n\n${request.body}`)}
            >
              Chép thư
            </Button>
            <Button loading={pending === id} onClick={() => void asked()}>
              Ghi đã gửi Design
            </Button>
          </Space>
        </Space>
      ) : null}
      <ActionError error={error} />
    </Space>
  );
}
