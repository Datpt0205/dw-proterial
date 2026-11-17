"use client";

import { useCallback, useState } from "react";
import { Button, Collapse, Flex, Input, Typography } from "antd";
import { MailOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { useAction } from "../../_lib/use-action";
import { formatDateTime } from "../../../../lib/dates";
import { useCachedResource } from "../../../../lib/use-cached-resource";

type Dates = SalesSchemas["PcDatesView"];
type PcDate = SalesSchemas["PcDateView"];

/**
 * PC's answer on delivery dates (AI item 7): Sales has DW1 read one of the
 * verified mails naming the order (listed by the server, sender shown), or
 * pastes PC's mail; DW1 reads the date PC gives for each line, and
 * ``onDates`` fills the
 * confirmation's fields with them. Nothing is recorded here: the dates stay
 * in the form until Sales checks them and presses "Ghi đã gửi xác nhận".
 */
export function PcDatesReader({
  caseId,
  caseVersion,
  onDates,
}: {
  caseId: string;
  caseVersion: number;
  onDates: (dates: PcDate[]) => void;
}) {
  const [text, setText] = useState("");
  const { run, pending } = useAction();
  const [view, setView] = useState<Dates | null>(null);
  const [error, setError] = useState<unknown>(null);
  const id = `pc-dates/${caseId}`;

  const mails = useCachedResource(
    `sales/pc-mails/${caseId}`,
    useCallback(() => salesApi().pcMails(caseId), [caseId]),
  );

  const read = async (messageId?: string) => {
    const result = await run(
      messageId ? `${id}/${messageId}` : id,
      { caseVersion, text, messageId },
      (key) =>
        messageId
          ? salesApi().readPcDatesFromMail(caseId, messageId, caseVersion, key)
          : salesApi().readPcDates(caseId, caseVersion, text, key),
      "DW1 đã đọc thư PC",
    );
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    setView(result.value);
    if (result.value.dates.length) onDates(result.value.dates);
  };

  // A date the mail writes in an order it does not settle (03/04) is
  // dropped too, but it is there: Sales is told to read it, never that PC
  // gave no date.
  const drops = (v: Dates) =>
    (v.unsettled
      ? ` ${v.unsettled} ngày PC viết kiểu 03/04 mà thư không cho biết ngày hay tháng đứng trước: bạn tự điền.`
      : "") +
    (v.dropped > v.unsettled
      ? ` ${v.dropped - v.unsettled} ngày bị bỏ vì không khớp thư hoặc không đúng dòng.`
      : "");
  const said = (v: Dates) =>
    v.status === "read"
      ? `Đã điền ${v.dates.length} ngày từ thư PC (máy đọc) vào cột Ngày xác nhận: kiểm từng ngày trước khi ghi.` +
        drops(v)
      : v.status === "nothing"
        ? v.dropped
          ? `DW1 không điền được ngày nào.${drops(v)}`
          : "DW1 không thấy ngày nào PC cho từng dòng trong thư này."
        : "DW1 chưa đọc được lúc này: máy chưa có mô hình hoặc mô hình không trả lời.";

  return (
    <Collapse
      size="small"
      items={[
        {
          key: "pc",
          label: mails.data?.mails.length
            ? `Thư nêu đơn này (${mails.data.mails.length}) hoặc dán thư PC để DW1 điền ngày`
            : "Dán thư trả lời của PC để DW1 điền ngày",
          children: (
            <Flex vertical gap={8}>
              {(mails.data?.mails ?? []).map((mail) => (
                <Flex key={mail.message_id} gap={8} align="center" wrap>
                  <MailOutlined aria-hidden />
                  <Typography.Text>
                    {mail.sender} · {mail.subject} ·{" "}
                    {formatDateTime(mail.received_at)}
                  </Typography.Text>
                  <Button
                    loading={pending === `${id}/${mail.message_id}`}
                    onClick={() => void read(mail.message_id)}
                  >
                    DW1 đọc ngày từ thư này
                  </Button>
                </Flex>
              ))}
              <Input.TextArea
                aria-label="Thư trả lời của PC"
                placeholder="Dán nội dung thư PC trả lời về ngày giao"
                autoSize={{ minRows: 3, maxRows: 8 }}
                // The longest text DW1 reads, as the API says it.
                maxLength={mails.data?.text_max}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
              <div>
                <Button
                  loading={pending === id}
                  disabled={!text.trim()}
                  onClick={() => void read()}
                >
                  DW1 đọc ngày
                </Button>
              </div>
              {view ? (
                <Typography.Text role="status">{said(view)}</Typography.Text>
              ) : null}
              <ActionError error={error} />
            </Flex>
          ),
        },
      ]}
    />
  );
}
