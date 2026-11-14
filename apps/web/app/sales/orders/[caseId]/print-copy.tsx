"use client";

import { Alert, Button, Space } from "antd";
import { EyeOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { formatDate } from "../../../../lib/dates";
import { FIELD, label } from "../../_lib/labels";

type Order = SalesSchemas["OrderCaseView"];

/** A value as a file prints it: an ISO date in the one date format. */
function shown(value: string | null | undefined): string | null {
  if (!value) return null;
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? formatDate(value) : value;
}

/**
 * The second file of the same PO in the mail: the PDF print beside its
 * workbook (ticket 34), or any other file naming the same PO number (ticket
 * 22). The two are one PO; the lines sit on the first file, and neither file
 * wins: each value they print differently is `value_uncertain` on the case's
 * value and `files_disagree` names both, waiting for Sales to type it or ask
 * the customer. Each difference opens on the second file (`print:<n>`).
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
          ? `Cùng PO có tệp thứ hai (${copy.attachment_id}): ${differences.length} giá trị ghi khác tệp ${order.attachment_id ?? ""}.`
          : `Cùng PO có tệp thứ hai (${copy.attachment_id}): khớp với tệp ${order.attachment_id ?? ""}.`
      }
      description={
        <Space orientation="vertical" size={4}>
          <span>
            {differences.length
              ? "Không tệp nào được ưu tiên: Sales nhập từng giá trị đúng hoặc hỏi khách."
              : "Tệp thứ hai được giữ làm nguồn đối chiếu, không mở hồ sơ thứ hai."}
          </span>
          {differences.length ? (
            <Space wrap size={[8, 4]}>
              {differences.map((d, index) => {
                const where = d.line_no ? `Dòng ${d.line_no}: ` : "";
                const what = label(FIELD, d.field);
                const ours = shown(d.ours);
                const theirs = shown(d.theirs);
                const values = ours && theirs ? ` ${ours} / ${theirs}` : "";
                return (
                  <Button
                    key={`${d.line_no ?? "-"}:${d.field}`}
                    size="small"
                    type="text"
                    icon={<EyeOutlined aria-hidden />}
                    onClick={() => onOpenSource(`print:${index}`, null)}
                    aria-label={`Xem trên tệp thứ hai: ${where}${what}`}
                  >
                    {where}
                    {what}
                    {values}
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
