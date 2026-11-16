"use client";

import { useCallback } from "react";
import { Alert, Card, Table, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { MaskedValue } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { formatDateTime } from "../../../../lib/dates";
import { salesApi } from "../../_lib/api";
import { usePeople } from "../../_lib/people";
import { useResource } from "../../_lib/use-resource";

type View = SalesSchemas["ReadBackView"];
type Difference = SalesSchemas["SoDifference"];

const FIELD: Record<Difference["field"], string> = {
  missing_row: "Bravo thiếu dòng (import đã bỏ qua)",
  extra_row: "Bravo có dòng thừa",
  item_code: "Mã hàng",
  quantity: "Số lượng",
  unit_price: "Đơn giá",
  requested_date: "Ngày khách yêu cầu",
};

// Who sees a price difference's values: said once, beside the column.
const PRICES_HIDDEN = "Chỉ người được xem giá thấy đơn giá.";

/**
 * The sales order as Bravo held it when last read back (ticket 03): beside
 * the PIC's entry, for the cross-checker. It decides nothing: Bravo's own
 * import skips a row it refuses without a log, and this is what shows it.
 */
export function BravoReadBackPanel({ caseId }: { caseId: string }) {
  const name = usePeople();
  const view = useResource(
    `sales/order/${caseId}/bravo-read-back`,
    useCallback(() => salesApi().bravoReadBack(caseId), [caseId]),
  );
  return (
    <Card size="small" title="Đối chiếu với Bravo">
      {view.error ? (
        <LoadError error={view.error} onRetry={view.reload} />
      ) : view.data ? (
        <ReadBack view={view.data} name={name} />
      ) : null}
    </Card>
  );
}

function ReadBack({
  view,
  name,
}: {
  view: View;
  name: (id: string | null | undefined) => string;
}) {
  const back = view.read_back;
  if (!back)
    return (
      <Typography.Text role="note">
        Chưa đọc lại SO từ Bravo. Sau khi import, xuất màn Customer order
        information (Form 1) và tải lên ở trang Đơn hàng (“Đọc lại SO từ
        Bravo”); đến lúc đó chỉ có lời xác nhận của người nhập.
      </Typography.Text>
    );
  const meta = `${back.so_no} · đọc ${formatDateTime(back.read_at)} · ${name(back.read_by)} tải lên · ${back.rows_read} dòng`;
  return (
    <div className="space-y-2">
      {view.stale ? (
        <Alert
          type="warning"
          showIcon
          title="Hồ sơ đã đổi sau lần đọc này: tải lại tệp xuất Bravo để đối chiếu phiên bản hiện tại."
        />
      ) : null}
      {back.differences.length ? (
        <Alert
          type="error"
          showIcon
          title={`Bravo lệch bản đã duyệt ở ${back.differences.length} chỗ`}
          description={meta}
        />
      ) : (
        <Alert
          type="success"
          showIcon
          title="Bravo khớp bản đã duyệt"
          description={meta}
        />
      )}
      {back.differences.length ? (
        <Table
          size="small"
          rowKey={(d, i) => `${d.line_no}-${d.field}-${i}`}
          pagination={false}
          dataSource={back.differences}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Dòng PO", dataIndex: "line_no" },
            {
              title: "Chỗ lệch",
              dataIndex: "field",
              render: (f: Difference["field"]) => (
                <Tag color="error">{FIELD[f]}</Tag>
              ),
            },
            {
              title: "Bản đã duyệt",
              key: "expected",
              render: (_: unknown, d: Difference) =>
                d.field === "unit_price" && view.prices_hidden ? (
                  <MaskedValue sentence={PRICES_HIDDEN} />
                ) : (
                  (d.expected ?? "—")
                ),
            },
            {
              title: "Bravo",
              key: "actual",
              render: (_: unknown, d: Difference) =>
                d.field === "unit_price" && view.prices_hidden ? (
                  <MaskedValue sentence={PRICES_HIDDEN} />
                ) : (
                  (d.actual ?? "—")
                ),
            },
          ]}
        />
      ) : null}
    </div>
  );
}
