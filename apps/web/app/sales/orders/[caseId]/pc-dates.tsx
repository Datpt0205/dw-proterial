"use client";

import { useState } from "react";
import { Button, Collapse, Flex, Input, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { useAction } from "../../_lib/use-action";

type Dates = SalesSchemas["PcDatesView"];
type PcDate = SalesSchemas["PcDateView"];

/** The longest mail the API reads (`PcDatesBody.text`). */
const TEXT_MAX = 8000;

/**
 * PC's answer on delivery dates (AI item 7): Sales pastes PC's mail, DW1
 * reads the date PC gives for each line, and ``onDates`` fills the
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

  const read = async () => {
    const result = await run(
      id,
      { caseVersion, text },
      (key) => salesApi().readPcDates(caseId, caseVersion, text, key),
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

  const said = (v: Dates) =>
    v.status === "read"
      ? `Đã điền ${v.dates.length} ngày từ thư PC (máy đọc) vào cột Ngày xác nhận: kiểm từng ngày trước khi ghi.` +
        (v.dropped
          ? ` ${v.dropped} ngày bị bỏ vì không khớp thư hoặc không đúng dòng.`
          : "")
      : v.status === "nothing"
        ? "DW1 không thấy ngày nào PC cho từng dòng trong thư này."
        : "DW1 chưa đọc được lúc này: máy chưa có mô hình hoặc mô hình không trả lời.";

  return (
    <Collapse
      size="small"
      items={[
        {
          key: "pc",
          label: "Dán thư trả lời của PC để DW1 điền ngày",
          children: (
            <Flex vertical gap={8}>
              <Input.TextArea
                aria-label="Thư trả lời của PC"
                placeholder="Dán nội dung thư PC trả lời về ngày giao"
                autoSize={{ minRows: 3, maxRows: 8 }}
                maxLength={TEXT_MAX}
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
