"use client";

import { Alert, Button, Space } from "antd";
import { EyeOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { FIELD, label } from "../../_lib/labels";

type Order = SalesSchemas["OrderCaseView"];

/**
 * The PDF print the customer attached beside the workbook (ticket 34). The
 * two are one PO, read from the workbook; each value the print shows
 * differently is `value_uncertain` on the workbook's value, and opens here on
 * the print (`print:<n>`) for Sales to compare.
 */
export function PrintCopyNotice({
  order,
  onOpenSource,
}: {
  order: Order;
  onOpenSource: (field: string, lineNo: number | null) => void;
}) {
  const copy = order.print_copy;
  if (!copy) return null;
  const differences = copy.differences;
  return (
    <Alert
      type={differences.length ? "warning" : "info"}
      showIcon
      title={
        differences.length
          ? `Kèm bản in PDF (${copy.attachment_id}): ${differences.length} giá trị bản in ghi khác file Excel.`
          : `Kèm bản in PDF (${copy.attachment_id}): khớp với file Excel.`
      }
      description={
        <Space orientation="vertical" size={4}>
          <span>
            DW1 đọc đơn từ file Excel; bản in được giữ làm nguồn đối chiếu,
            không mở hồ sơ thứ hai.
          </span>
          {differences.length ? (
            <Space wrap size={[8, 4]}>
              {differences.map((d, index) => {
                const where = d.line_no ? `Dòng ${d.line_no}: ` : "";
                const what = label(FIELD, d.field);
                return (
                  <Button
                    key={`${d.line_no ?? "-"}:${d.field}`}
                    size="small"
                    type="text"
                    icon={<EyeOutlined aria-hidden />}
                    onClick={() => onOpenSource(`print:${index}`, null)}
                    aria-label={`Xem trên bản in: ${where}${what}`}
                  >
                    {where}
                    {what}
                  </Button>
                );
              })}
            </Space>
          ) : null}
        </Space>
      }
    />
  );
}
