"use client";

import { useId, useState } from "react";
import { Alert, App, Button, Card, Form, Input, Space, Typography } from "antd";
import { CopyOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";

type Draft = NonNullable<SalesSchemas["InboxMessageView"]["handoff_draft"]>;
type Handoff = NonNullable<SalesSchemas["MessageDispositionView"]["handoff"]>;

const TEAM: Record<Draft["to"], string> = {
  pc: "PC (kế hoạch sản xuất)",
  qa: "QA (chất lượng)",
};

/**
 * The hand-off to PC or QA DW1 wrote from a routed message (ticket 33): the
 * template's words around the values code located in the customer's mail and
 * the customer's own sentences in «». Sales reads it beside the mail, edits it
 * here, copies it and sends it from their own mailbox: DW1 sends nothing and
 * changes nothing in Bravo. Where the model gave nothing code could keep, the
 * form is the template with every value left for Sales to fill.
 */
export function HandoffDraft({
  draft,
  handoff,
}: {
  draft: Draft;
  handoff: Handoff;
}) {
  const { message } = App.useApp();
  const id = useId();
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const read = handoff.outcome === "read";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(`${subject}\n\n${body}`);
      message.success("Đã chép bản chuyển: dán vào thư gửi " + TEAM[draft.to]);
    } catch {
      message.error("Trình duyệt không cho chép: chọn và chép tay nội dung.");
    }
  };

  return (
    <Card
      size="small"
      type="inner"
      title={`Bản chuyển ${TEAM[draft.to]}: DW1 soạn sẵn, bạn xem, sửa và gửi`}
    >
      <Space orientation="vertical" className="w-full">
        <Space wrap size="small">
          {read ? (
            <StatusTag tone="warn">
              Mô hình chép từ thư khách, DW1 kiểm từng giá trị
            </StatusTag>
          ) : (
            <StatusTag tone="unk">
              Mô hình không đọc được: điền tay như trước
            </StatusTag>
          )}
          {handoff.po_no ? (
            <Typography.Text>
              PO {handoff.po_no}
              {handoff.so_no ? ` · đơn bán ${handoff.so_no}` : ""} (đã khớp đơn
              của chính khách)
            </Typography.Text>
          ) : null}
        </Space>
        {read ? null : (
          <Alert
            type="info"
            showIcon
            title="Mọi giá trị đang để “chưa rõ”: đọc thư khách và điền."
          />
        )}
        <Form layout="vertical">
          <Form.Item label="Tiêu đề" htmlFor={`${id}-subject`}>
            <Input
              id={`${id}-subject`}
              value={subject}
              maxLength={300}
              onChange={(e) => setSubject(e.target.value)}
            />
          </Form.Item>
          <Form.Item
            label="Nội dung"
            htmlFor={`${id}-body`}
            extra={`Mẫu ${draft.template_ref}. Câu trong «» là nguyên văn của khách. DW1 không gửi thư này.`}
          >
            <Input.TextArea
              id={`${id}-body`}
              value={body}
              autoSize={{ minRows: 6, maxRows: 18 }}
              maxLength={4000}
              onChange={(e) => setBody(e.target.value)}
            />
          </Form.Item>
        </Form>
        <Button icon={<CopyOutlined aria-hidden />} onClick={copy}>
          Chép bản chuyển
        </Button>
      </Space>
    </Card>
  );
}
