"use client";

import {
  Alert,
  Card,
  Col,
  Descriptions,
  Row,
  Statistic,
  Table,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag, RegionState } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import {
  formatDateTime,
  formatDuration,
  formatMonth,
  TIME_ZONE_LABEL,
  UNKNOWN_TIME,
} from "../../../lib/dates";
import {
  FINDING_CODE,
  label,
  ORDER_STATE,
  PROCEDURE,
  QUOTE_STATE,
  STEP_COVERAGE,
  TIME_BUCKET,
} from "../_lib/labels";
import { SCOPE, useSalesFrame } from "../_components/sales-frame";
import { salesCrumbs } from "../_components/crumbs";
import { ScopeGate } from "../_components/scope-gate";

type Overview = SalesSchemas["OverviewView"];
type Step = SalesSchemas["StepCount"];
type TimeStat = SalesSchemas["TimeStat"];

/** Every figure here is counted on the fictional mock set, and says so. */
const MOCK_SET = "trên bộ mẫu giả lập";

const seconds = (value: number | null | undefined) =>
  value === null || value === undefined
    ? UNKNOWN_TIME
    : formatDuration(value * 1000);

/**
 * Tổng quan quy trình (V3Exec, re-cut): counts and times only, never an
 * amount, which is all a `sales_viewer` may read. The steps are the API's
 * (`WIV_STEPS` through `/overview`); this page holds no step table of its own
 * and draws what it is sent.
 */
export default function OverviewPage() {
  return (
    <ScopeGate scope={SCOPE.overview}>
      <OverviewBody />
    </ScopeGate>
  );
}

function OverviewBody() {
  const { overview } = useSalesFrame();
  const data = overview.data;
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Tổng quan quy trình")}
        title="Tổng quan quy trình"
        subtitle={`Số hồ sơ ở mỗi bước của hai quy trình, và thời gian DW1 và Sales bỏ ra, ${MOCK_SET}. Không có số tiền nào ở trang này.`}
        tags={
          data ? (
            <StatusTag tone="gray">{`Cập nhật ${formatDateTime(data.as_of)}`}</StatusTag>
          ) : null
        }
      />
      {overview.loading ? (
        <RegionState kind="loading" />
      ) : overview.error ? (
        <LoadError error={overview.error} onRetry={overview.reload} />
      ) : data ? (
        <OverviewContent data={data} />
      ) : null}
    </div>
  );
}

function Kpi({
  title,
  value,
  note,
}: {
  title: string;
  value: string | number;
  note?: string;
}) {
  return (
    <Card size="small" className="h-full">
      <Statistic title={title} value={value} />
      {note ? <Typography.Text>{note}</Typography.Text> : null}
    </Card>
  );
}

function OverviewContent({ data }: { data: Overview }) {
  const m = data.messages;
  const kpis = [
    {
      title: "Email chưa có hướng xử lý",
      value: m.without_disposition,
      note:
        m.oldest_waiting_seconds !== null
          ? `Thư chờ lâu nhất: ${seconds(m.oldest_waiting_seconds)}`
          : `Tổng ${m.total} thư`,
    },
    {
      title: "Thư chuyển Sales chưa có người phụ trách",
      value: m.routed_without_owner,
      note: `${m.routed_to_sales} thư chuyển Sales xử lý`,
    },
    {
      title: "Dòng PO đã đọc / dòng in trên PO",
      value: `${data.lines_read}/${data.lines_printed}`,
    },
    {
      title: "Mã PRV: khớp convert list · Sales xác nhận · chưa giải quyết",
      value: `${data.mapping.convert_list} · ${data.mapping.confirmed_candidate} · ${data.mapping.unresolved}`,
    },
    {
      title: "Đơn tự kiểm xong không phải sửa giá trị",
      value: data.orders_prepared_without_correction,
    },
    {
      title: "Báo giá gửi đúng bản soạn đầu",
      value: data.quotes_sent_as_first_drafted,
    },
    {
      title: "Đơn đủ điều kiện tối thiểu A3 (chỉ đếm, không tự xác nhận)",
      value: data.a3_shadow,
    },
  ];

  const times: [string, TimeStat][] = [
    [label(TIME_BUCKET, "dw"), data.times.dw],
    [label(TIME_BUCKET, "sales"), data.times.sales],
    [label(TIME_BUCKET, "design"), data.times.design],
    [label(TIME_BUCKET, "approver"), data.times.approver],
    [label(TIME_BUCKET, "customer"), data.times.customer],
  ];

  const procedures = [...new Set(data.steps.map((s) => s.procedure))];
  const findings = Object.entries(data.findings_by_code);

  return (
    <div className="space-y-4">
      <section aria-labelledby="kpi-title" className="space-y-2">
        <Typography.Title level={4} id="kpi-title">
          Chỉ số {MOCK_SET}
        </Typography.Title>
        <Alert
          type="info"
          showIcon
          title={`Số đếm ${MOCK_SET}: bộ mẫu quá nhỏ để tính tỷ lệ, nên không có tỷ lệ hay kết luận đạt/không đạt.`}
        />
        <Row gutter={[12, 12]}>
          {kpis.map((kpi) => (
            <Col key={kpi.title} xs={24} sm={12} lg={8} xl={6}>
              <Kpi {...kpi} />
            </Col>
          ))}
        </Row>
      </section>

      <Card title={`Thời gian (trung vị · lâu nhất), ${MOCK_SET}`} size="small">
        <Table
          rowKey={(row) => row[0]}
          size="small"
          pagination={false}
          dataSource={times}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Ai giữ hồ sơ", render: (_, row) => row[0] },
            {
              title: "Số hồ sơ",
              align: "right",
              render: (_, row) => row[1].cases,
            },
            {
              title: "Trung vị",
              render: (_, row) => seconds(row[1].median_seconds),
            },
            {
              title: "Lâu nhất",
              render: (_, row) => seconds(row[1].max_seconds),
            },
          ]}
          footer={() =>
            "Thời gian chờ PC không đo được: việc với PC diễn ra ngoài cổng."
          }
        />
        <Descriptions
          className="mt-3"
          size="small"
          column={{ xs: 1, md: 2 }}
          items={[
            {
              key: "order",
              label: "Xác nhận đơn: mục tiêu · đo được (trung vị)",
              children: `${seconds(data.order_confirmation.target_seconds)} · ${seconds(data.order_confirmation.measured.median_seconds)} (${data.order_confirmation.measured.cases} đơn)`,
            },
            {
              key: "quote",
              label: "Báo giá: mục tiêu · đo được (trung vị)",
              children: `${seconds(data.quotation_time.target_seconds)} · ${seconds(data.quotation_time.measured.median_seconds)} (${data.quotation_time.measured.cases} báo giá)`,
            },
            {
              key: "policy",
              label: "Chính sách chỉ số",
              children: (
                <Typography.Text code>{data.kpi_policy}</Typography.Text>
              ),
            },
          ]}
        />
      </Card>

      {procedures.map((procedure) => (
        <Card
          key={procedure}
          title={`${label(PROCEDURE, procedure)}: số hồ sơ ở mỗi bước`}
          size="small"
        >
          <Table<Step>
            rowKey="step_id"
            size="small"
            pagination={false}
            scroll={{ x: "max-content" }}
            dataSource={data.steps.filter((s) => s.procedure === procedure)}
            columns={[
              { title: "Bước", dataIndex: "step_id" },
              {
                title: "Trạng thái hồ sơ",
                key: "states",
                render: (_, step) =>
                  step.states.length
                    ? step.states
                        .map((s) =>
                          label(
                            procedure === "WIV-03-012"
                              ? ORDER_STATE
                              : QUOTE_STATE,
                            s,
                          ),
                        )
                        .join(" · ")
                    : "Không có trạng thái riêng",
              },
              {
                title: "Phạm vi",
                key: "coverage",
                render: (_, step) => label(STEP_COVERAGE, step.coverage),
              },
              { title: "Số hồ sơ", dataIndex: "cases", align: "right" },
            ]}
          />
        </Card>
      ))}

      <Card title={`Cờ theo loại, ${MOCK_SET}`} size="small">
        <Table
          rowKey={(row) => row[0]}
          size="small"
          pagination={false}
          dataSource={findings}
          locale={{ emptyText: "Chưa có cờ nào: chưa có hồ sơ nào được kiểm." }}
          columns={[
            {
              title: "Loại cờ",
              render: (_, row) => label(FINDING_CODE, row[0]),
            },
            { title: "Số lần", align: "right", render: (_, row) => row[1] },
          ]}
        />
      </Card>

      <Card
        title={`Số lần DW1 đi qua mỗi bước theo tháng (${TIME_ZONE_LABEL}), ${MOCK_SET}`}
        size="small"
      >
        <Table
          rowKey={(row) => `${row.step_id}:${row.month}`}
          size="small"
          pagination={false}
          scroll={{ x: "max-content" }}
          dataSource={data.export}
          locale={{ emptyText: "Chưa có lượt nào." }}
          columns={[
            { title: "Bước", dataIndex: "step_id" },
            {
              title: "Tháng",
              dataIndex: "month",
              render: (month: string) => formatMonth(month),
            },
            { title: "Số lần", dataIndex: "times", align: "right" },
            {
              title: "Làm tay mất (phút/lần, mức nền)",
              dataIndex: "manual_baseline_minutes",
              align: "right",
            },
          ]}
          footer={() =>
            "Không quy ra số giờ tiết kiệm: các bước trùng với kế hoạch Bravo của khách không được tính."
          }
        />
      </Card>
    </div>
  );
}
