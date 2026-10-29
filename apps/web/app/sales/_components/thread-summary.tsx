"use client";

import { useState } from "react";
import { Button, Card, Space, Tag, Typography } from "antd";
import Link from "next/link";
import type { SalesSchemas } from "@dw/api-client";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";

type Summary = SalesSchemas["ThreadSummaryView"];

const NONE: Record<string, string> = {
  empty: "Hồ sơ chưa có thư nào trong hộp thư để tóm tắt.",
  unavailable:
    "DW1 chưa tóm tắt được lúc này: máy chưa có mô hình hoặc mô hình không trả lời.",
  refused:
    "DW1 viết những ý không khớp thư trong hồ sơ nên bản tóm tắt bị bỏ; bấm lại để thử.",
};

/**
 * The case's mail thread in a few points, on request (AI item 8): each point
 * links the mails it rests on, and the summary is marked as the machine's.
 * Code kept only points citing this case's mails and quoting their figures;
 * how many it dropped is said, so a short summary is not read as complete.
 */
export function ThreadSummary({
  kind,
  caseId,
}: {
  kind: "order" | "quote";
  caseId: string;
}) {
  const [busy, setBusy] = useState(false);
  const [view, setView] = useState<Summary | null>(null);
  const [error, setError] = useState<unknown>(null);
  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      setView(await salesApi().threadSummary(kind, caseId));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card
      size="small"
      title={
        <Space wrap>
          <span>Tóm tắt chuỗi thư</span>
          {view?.status === "summarized" ? <Tag>Máy viết</Tag> : null}
        </Space>
      }
      extra={
        <Button size="small" loading={busy} onClick={() => void ask()}>
          {view ? "Tóm tắt lại" : "DW1 tóm tắt"}
        </Button>
      }
    >
      {view?.status === "summarized" ? (
        <Space orientation="vertical" size={4} role="status">
          <ul className="m-0 pl-5">
            {view.points.map((point, index) => (
              <li key={index}>
                <Typography.Text>{point.text} </Typography.Text>
                {point.cites.map((mail) => (
                  <Link
                    key={mail}
                    href={`/sales/inbox?message=${encodeURIComponent(mail)}`}
                    aria-label={`Mở thư ${mail}`}
                  >
                    <Tag>{mail}</Tag>
                  </Link>
                ))}
              </li>
            ))}
          </ul>
          <Typography.Text>
            Từ {view.mails} thư mới nhất của hồ sơ
            {view.dropped
              ? `; ${view.dropped} ý bị bỏ vì không khớp thư được trích`
              : ""}
            .
          </Typography.Text>
        </Space>
      ) : view ? (
        <Typography.Text role="status">{NONE[view.status]}</Typography.Text>
      ) : (
        <Typography.Text>
          DW1 đọc các thư của hồ sơ và tóm tắt điều đang diễn ra, mỗi ý kèm
          thư làm căn cứ.
        </Typography.Text>
      )}
      <ActionError error={error} />
    </Card>
  );
}
