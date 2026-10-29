"use client";

import { useEffect, useState } from "react";
import { Alert, Flex, Space, Table, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../lib/auth/auth-context";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { messageRef } from "../_lib/messages";
import { useAction } from "../_lib/use-action";
import { GuardedButton } from "../_components/guarded-button";

type Reading = SalesSchemas["DesignTextReadingView"];
type Line = SalesSchemas["DesignTextLineView"];

/**
 * Design's reply written in the mail, not the reply form (AI item 6): DW1
 * reads it as soon as the row opens, and shows each value as the mail writes
 * it, marked as the machine's reading. Nothing reaches the case until Sales
 * confirms; the server checks every value against the mail again.
 */
export function DesignTextPanel({
  messageId,
  onAttached,
}: {
  messageId: string;
  onAttached: () => void;
}) {
  const { hasScope } = useAuth();
  const { run, pending } = useAction();
  const [reading, setReading] = useState<Reading | null>(null);
  const [error, setError] = useState<unknown>(null);
  const allowed = hasScope("sales.quote.prepare");
  const ref = messageRef(messageId);
  const id = `design-text/${messageId}`;

  useEffect(() => {
    if (!allowed) return;
    let live = true;
    salesApi()
      .designTextReply(messageId)
      .then((view) => live && setReading(view))
      .catch((e: unknown) => live && setError(e));
    return () => {
      live = false;
    };
  }, [allowed, messageId]);

  const confirm = async (view: Reading) => {
    const body = {
      ycbg_no: view.ycbg_no ?? "",
      lines: view.lines.map((line) => ({ ...line })),
    };
    const result = await run(
      id,
      body,
      (key) => salesApi().confirmDesignTextReply(messageId, body, key),
      `Đã gắn trả lời của Design (thư ${ref}) vào hồ sơ ${view.ycbg_no}`,
    );
    if (result.ok) {
      setError(null);
      onAttached();
    } else setError(result.error);
  };

  if (!allowed) return null;
  return (
    <Flex vertical gap={6} className="max-w-3xl">
      {reading?.status === "read" ? (
        <>
          <Alert
            type="info"
            showIcon
            role="status"
            title={
              <Space wrap>
                <span>
                  DW1 đọc được trả lời của Design cho {reading.ycbg_no}
                </span>
                <Tag>Máy đọc</Tag>
              </Space>
            }
            description="Mỗi giá trị chép nguyên văn từ thư. So với thư bên dưới rồi xác nhận để gắn vào hồ sơ đang chờ Design."
          />
          <Table<Line>
            size="small"
            rowKey="line_no"
            pagination={false}
            dataSource={reading.lines}
            scroll={{ x: "max-content" }}
            columns={[
              { title: "Dòng", dataIndex: "line_no" },
              { title: "Mã BP", dataIndex: "bp_code" },
              { title: "Số spec", dataIndex: "spec_no" },
              {
                title: "Mã PRV",
                dataIndex: "prv_code",
                render: (v: string | null) => v ?? "Chưa có (Design tạo sau)",
              },
              {
                title: "Đồng (kg/km)",
                dataIndex: "copper_kg_per_km",
                align: "right",
                render: (v: string | null) => v ?? "Thư không nêu",
              },
            ]}
          />
          <div>
            <GuardedButton
              type="primary"
              reason={null}
              loading={pending === id}
              aria-label={`Xác nhận trả lời của Design trong thư ${ref}`}
              onClick={() => void confirm(reading)}
            >
              Đúng, gắn vào hồ sơ
            </GuardedButton>
          </div>
        </>
      ) : reading ? (
        <Typography.Text role="status">
          {reading.status === "no_case"
            ? `Thư trả lời ${reading.ycbg_no ?? "một YCBG"}, nhưng không có hồ sơ nào đang chờ Design dưới số này, hoặc thư không trả lời đủ các dòng. Kiểm tra số YCBG của hồ sơ.`
            : "DW1 chưa đọc chắc được thư này (không có mô hình, hoặc giá trị không rõ ràng): đọc thư và nhập tay như trước."}
        </Typography.Text>
      ) : null}
      <ActionError error={error} />
    </Flex>
  );
}
