"use client";

import { Suspense, useCallback, useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Empty, Progress, Segmented, Table, Tag, Typography } from "antd";
import type { ActivityQuery, SalesSchemas } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import {
  formatDate,
  formatDateTime,
  formatLatency,
  lastDays,
  TIME_ZONE_LABEL,
} from "../../../lib/dates";
import { formatShare } from "../../../lib/money";
import { useNow } from "../../../lib/use-now";
import {
  activityHref,
  describeActivity,
  modelStepLabel,
  reasonLabel,
} from "../_lib/activity";
import { salesApi } from "../_lib/api";
import { ACTIVITY_RESULT, CASE_KIND } from "../_lib/labels";
import { useResource } from "../_lib/use-resource";
import { salesCrumbs } from "../_components/crumbs";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";
import { useAuth } from "../../../lib/auth/auth-context";

type Summary = SalesSchemas["ActivitySummaryView"];
type StepSummary = SalesSchemas["StepSummaryView"];
type Filter = SalesSchemas["ActivityFilter"];
type Lane = "order" | "quote";

const RANGES = ["7", "30"] as const;
type Range = (typeof RANGES)[number];
const LANES = ["all", "order", "quote"] as const;
type LaneChoice = (typeof LANES)[number];

/**
 * Hoạt động DW1 (slice 3): per model step over the last 7 or 30 days, how
 * many items it handled, how many DW1 carried and how many went to a person,
 * how often the model gave no answer, how long it took, and the reasons most
 * often given; each count opens the case list it stands for, narrowed by the
 * filter the server served with it. A series per day sits under each step.
 *
 * Counts and times only, no case and no amount: the API's summary, which it
 * opens to `sales.overview.read` and `sales.rules.propose` alike, as this
 * page's gate does. A count over both lanes is one number for two lists, so
 * it links only once a lane is chosen.
 */
export default function ActivityPage() {
  return (
    <ScopeGate scope={[SCOPE.overview, SCOPE.rulesPropose]}>
      <Suspense>
        <Activity />
      </Suspense>
    </ScopeGate>
  );
}

/** The range and the lane, in the URL (ui-quality §11). */
function useChoices() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const range: Range =
    RANGES.find((r) => r === params.get("range")) ?? RANGES[0];
  const lane: LaneChoice =
    LANES.find((l) => l === params.get("lane")) ?? LANES[0];
  const set = (name: string, value: string, fallback: string) => {
    const query = new URLSearchParams(params.toString());
    if (value === fallback) query.delete(name);
    else query.set(name, value);
    router.replace(`${pathname}${query.size ? `?${query}` : ""}`, {
      scroll: false,
    });
  };
  return {
    range,
    lane,
    setRange: (value: Range) => set("range", value, RANGES[0]),
    setLane: (value: LaneChoice) => set("lane", value, LANES[0]),
  };
}

function Activity() {
  const choices = useChoices();
  const opensCases = useAuth().hasScope(SCOPE.caseRead);
  const now = useNow();
  const { from, to } = lastDays(Number(choices.range), now);
  const lane = choices.lane === "all" ? null : choices.lane;
  const summary = useResource<Summary>(
    `sales/activity:${from}:${to}:${lane ?? "all"}`,
    useCallback(() => {
      const query: ActivityQuery = { from, to };
      if (lane) query.lane = lane;
      return salesApi().activity(query);
    }, [from, to, lane]),
  );
  useEffect(() => {
    document.title = "Hoạt động DW1 · Sales";
  }, []);

  const data = summary.data;
  const handled = (data?.steps ?? []).reduce((n, s) => n + s.handled.count, 0);
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Hoạt động DW1")}
        title="Hoạt động DW1"
        help={`Mỗi bước có mô hình: DW1 tự làm bao nhiêu, chuyển cho người bao nhiêu và vì sao.${opensCases ? " Mỗi số mở danh sách hồ sơ nó đếm." : ""}`}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Segmented<Range>
          aria-label="Khoảng thời gian"
          value={choices.range}
          onChange={choices.setRange}
          options={[
            { value: "7", label: "7 ngày" },
            { value: "30", label: "30 ngày" },
          ]}
        />
        <Segmented<LaneChoice>
          aria-label="Luồng hồ sơ"
          value={choices.lane}
          onChange={choices.setLane}
          options={[
            { value: "all", label: "Tất cả" },
            { value: "order", label: CASE_KIND.order },
            { value: "quote", label: CASE_KIND.quote },
          ]}
        />
      </div>
      <Typography.Paragraph className="mb-0!">
        Từ {formatDate(data?.from ?? from)} đến hết {formatDate(data?.to ?? to)}{" "}
        ({TIME_ZONE_LABEL})
        {data ? ` · số liệu lúc ${formatDateTime(data.as_of)}` : ""}.
        {lane || !opensCases
          ? ""
          : " Chọn Đơn hàng hoặc Báo giá để mở danh sách hồ sơ sau mỗi số."}
      </Typography.Paragraph>
      {summary.error ? (
        <LoadError error={summary.error} onRetry={summary.reload} />
      ) : data && handled === 0 ? (
        <Empty
          description={`Trong ${choices.range} ngày qua DW1 chưa dùng mô hình ở bước nào${lane ? ` (${CASE_KIND[lane]})` : ""}. Số liệu hiện ở đây khi DW1 đọc thư và tệp mới.`}
        />
      ) : (
        <Table<StepSummary>
          rowKey="step"
          loading={summary.loading}
          dataSource={data?.steps ?? []}
          pagination={false}
          sticky
          scroll={{ x: "max-content" }}
          locale={{ emptyText: summary.loading ? " " : "Không có bước nào." }}
          expandable={{
            expandedRowRender: (row) => <DaySeries summary={data!} row={row} />,
          }}
          columns={[
            {
              title: "Bước",
              key: "step",
              render: (_, row) => (
                <span className="flex flex-col items-start gap-1">
                  <Typography.Text strong>
                    {modelStepLabel(row.step)}
                  </Typography.Text>
                  <span className="flex flex-wrap gap-1">
                    {row.process_steps.map((s) => (
                      <Tag key={s} className="me-0">
                        {s}
                      </Tag>
                    ))}
                  </span>
                </span>
              ),
            },
            {
              title: "Đã xử lý",
              key: "handled",
              align: "right",
              render: (_, row) => <Count linked={row.handled} lane={lane} />,
            },
            {
              title: "Tự động",
              key: "automatic",
              align: "right",
              render: (_, row) => (
                <span className="flex flex-col items-end">
                  <Count linked={row.automatic} lane={lane} />
                  <Typography.Text type="secondary">
                    {row.automatic_share === null
                      ? "chưa có dữ liệu"
                      : formatShare(row.automatic_share)}
                  </Typography.Text>
                </span>
              ),
            },
            {
              title: ACTIVITY_RESULT.to_person,
              key: "to_person",
              align: "right",
              render: (_, row) => <Count linked={row.to_person} lane={lane} />,
            },
            {
              title: ACTIVITY_RESULT.unavailable,
              key: "unavailable",
              align: "right",
              render: (_, row) => (
                <Count linked={row.model_unavailable} lane={lane} />
              ),
            },
            {
              title: "Độ trễ p50 / p95",
              key: "latency",
              align: "right",
              render: (_, row) =>
                row.latency.samples ? (
                  <span className="flex flex-col items-end">
                    <span>
                      {formatLatency(row.latency.p50_ms)} /{" "}
                      {formatLatency(row.latency.p95_ms)}
                    </span>
                    <Typography.Text type="secondary">
                      {row.latency.samples} lần đo
                    </Typography.Text>
                  </span>
                ) : (
                  "Chưa có"
                ),
            },
            {
              title: "Lý do hay gặp",
              key: "reasons",
              render: (_, row) =>
                row.top_reasons.length ? (
                  <ul className="m-0 flex list-none flex-col gap-1 p-0">
                    {row.top_reasons.map((r) => (
                      <li key={r.reason_code}>
                        {reasonLabel(r.reason_code)}:{" "}
                        <Count linked={r} lane={lane} />
                      </li>
                    ))}
                  </ul>
                ) : (
                  "Không có"
                ),
            },
          ]}
        />
      )}
    </div>
  );
}

/**
 * A count, linking to the case list it stands for once a lane is chosen and
 * there is a case to see. The link's name starts with the count it shows.
 */
function Count({
  linked,
  lane,
}: {
  linked: { count: number; filter: Filter };
  lane: Lane | null;
}) {
  // A count opens the case list it counts, for someone who may open it.
  const opensCases = useAuth().hasScope(SCOPE.caseRead);
  if (!lane || linked.count === 0 || !opensCases)
    return <span>{linked.count}</span>;
  return (
    <Link
      href={activityHref(lane, linked.filter)}
      aria-label={`${linked.count}: mở danh sách ${lane === "order" ? "đơn hàng" : "báo giá"}, ${describeActivity(linked.filter)}`}
    >
      {linked.count}
    </Link>
  );
}

/** One step's days, oldest first: handled, carried by DW1, handed over. */
function DaySeries({ summary, row }: { summary: Summary; row: StepSummary }) {
  const days = summary.days.map((d) => ({
    day: d.day,
    ...(d.steps.find((s) => s.step === row.step) ?? {
      handled: 0,
      automatic: 0,
      to_person: 0,
    }),
  }));
  return (
    <Table
      size="small"
      rowKey="day"
      pagination={false}
      scroll={{ x: "max-content" }}
      aria-label={`Theo ngày: ${modelStepLabel(row.step)}`}
      dataSource={days}
      columns={[
        {
          title: "Ngày",
          key: "day",
          render: (_, d) => formatDate(d.day),
        },
        { title: "Đã xử lý", dataIndex: "handled", align: "right" },
        { title: "Tự động", dataIndex: "automatic", align: "right" },
        {
          title: ACTIVITY_RESULT.to_person,
          dataIndex: "to_person",
          align: "right",
        },
        {
          title: "Tỉ lệ tự động",
          key: "share",
          render: (_, d) =>
            d.handled ? (
              <Progress
                size="small"
                className="m-0! min-w-32"
                percent={Math.round((d.automatic / d.handled) * 100)}
                format={() => formatShare(d.automatic / d.handled)}
              />
            ) : (
              "Không có"
            ),
        },
      ]}
    />
  );
}
