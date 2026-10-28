"use client";

import { Alert, Button, Space, Typography } from "antd";
import { EyeOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { FIELD, label } from "../../_lib/labels";

type Order = SalesSchemas["OrderCaseView"];
type Unopened = SalesSchemas["UnopenedValue"];

/**
 * For the cross-checker (audit gap 5): the values whose page or sheet nobody
 * was served before Bravo was recorded, so nobody compared them with the PO,
 * whatever the step says. The server sends the list to a holder of
 * `sales.order.cross_check` only (null for anyone else, and then the page
 * draws nothing); each value opens its source at its anchor.
 */
export function UnopenedValues({
  order,
  values,
  onOpenSource,
}: {
  order: Order;
  values: Unopened[];
  onOpenSource: (field: string, lineNo: number | null) => void;
}) {
  // Drawn at the cross-check only (Đạt's open question of 10-24, decided
  // 10-28): before Bravo the preparer is still opening sources and the page
  // already says which page they have not opened, so a list of every value
  // nobody opened yet runs a screen long and tells them nothing new.
  if (!values.length || order.status !== "uploaded_to_bravo") return null;
  // Grouped as the server ordered them: the PO's own values, then by line.
  const groups = new Map<number | null, string[]>();
  for (const v of values) {
    const line = v.line_no ?? null;
    groups.set(line, [...(groups.get(line) ?? []), v.field]);
  }
  return (
    <Alert
      type="warning"
      showIcon
      role="status"
      title={`${values.length} giá trị chưa ai mở nguồn${order.bravo_recorded_at ? " trước khi nhập Bravo" : ""}`}
      description={
        <Space orientation="vertical" size={4} className="w-full">
          <Typography.Text>
            Chưa ai đối chiếu các giá trị này với PO: mở nguồn của từng giá trị
            khi kiểm chéo.
          </Typography.Text>
          <ul className="m-0 list-none space-y-1 p-0">
            {[...groups].map(([line, fields]) => (
              <li
                key={line ?? "po"}
                className="flex flex-wrap items-center gap-1"
              >
                <Typography.Text strong>
                  {line === null ? "Đầu PO:" : `Dòng ${line}:`}
                </Typography.Text>
                {fields.map((field) => (
                  <Button
                    key={field}
                    size="small"
                    type="link"
                    icon={<EyeOutlined aria-hidden />}
                    onClick={() => onOpenSource(field, line)}
                    aria-label={`Mở nguồn ${label(FIELD, field)}${line === null ? "" : ` dòng ${line}`}`}
                  >
                    {label(FIELD, field)}
                  </Button>
                ))}
              </li>
            ))}
          </ul>
        </Space>
      }
    />
  );
}
