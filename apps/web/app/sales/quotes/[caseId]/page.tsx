"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Space,
  Table,
  Typography,
} from "antd";
import {
  ClockCircleOutlined,
  EyeOutlined,
  FileSearchOutlined,
  QuestionCircleOutlined,
} from "@ant-design/icons";
import type { SourceRegion } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import {
  RegionLoading,
  RegionState,
} from "../../../../components/region-state";
import {
  dayDeadline,
  daysSince,
  formatAge,
  formatDate,
  formatDateTime,
  formatMonth,
  UNKNOWN_TIME,
} from "../../../../lib/dates";
import type { Currency } from "../../../../lib/money";
import { useNow } from "../../../../lib/use-now";
import { salesApi } from "../../_lib/api";
import {
  ACTION,
  DECLINE_REASON,
  FIELD,
  FINDING_CODE,
  label,
  LANGUAGE,
  QUOTE_STATE,
} from "../../_lib/labels";
import { usePeople } from "../../_lib/people";
import { anchorRegion } from "../../_lib/served";
import { useResource } from "../../_lib/use-resource";
import { useSalesViewer } from "../../_lib/viewer";
import { ArtifactsPanel } from "../../_components/artifacts-panel";
import { CaseSummary } from "../../_components/case-summary";
import { CaseTimeline } from "../../_components/case-timeline";
import { salesCrumbs } from "../../_components/crumbs";
import { FindingWords, Money, Quantity } from "../../_components/money";
import { SCOPE } from "../../_components/sales-frame";
import { ScopeGate } from "../../_components/scope-gate";
import {
  SourceDrawer,
  type SourceTarget,
} from "../../_components/source-drawer";
import { QuoteStateTag, SeverityTag } from "../../_components/tags";
import { QuoteActions } from "./actions";
import { ApprovalPanel } from "./approval";
import { EvidencePanel } from "./evidence";
import { PricingForm } from "./pricing";

const DAY = 86_400_000;

export default function QuotePage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <QuoteDetail />
    </ScopeGate>
  );
}

function QuoteDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const viewer = useSalesViewer();
  const name = usePeople();
  const now = useNow();
  const quote = useResource(
    `sales/quote/${caseId}`,
    useCallback(() => salesApi().quote(caseId), [caseId]),
  );
  const work = useResource(
    "sales/my-work",
    useCallback(() => salesApi().myWork(), []),
  );
  const customers = useResource(
    "sales/master-data/customers",
    useCallback(() => salesApi().customers(), []),
  );
  const [source, setSource] = useState<
    (SourceTarget & { attachmentId: string }) | null
  >(null);

  const data = quote.data;
  useEffect(() => {
    if (data) document.title = `RFQ ${data.rfq_no} · Báo giá · Sales`;
  }, [data]);

  const reload = useCallback(() => {
    quote.reload();
    work.reload();
  }, [quote, work]);

  if (quote.loading) return <RegionLoading rows={14} />;
  if (quote.error || !data)
    return <RegionState error={quote.error} onRetry={quote.reload} />;

  const currency = data.currency as Currency;
  const customer = customers.data?.items.find(
    (c) => c.code === data.customer_code,
  );
  const deadline = dayDeadline(data.quote_due, now);
  const done = ["sent", "master_list_recorded", "declined"].includes(
    data.status,
  );
  const overdue = data.overdue && !done;
  const openFindings = data.findings.filter(
    (f) => f.disposition.kind === "open",
  ).length;
  const mine = (work.data ?? []).find(
    (w) => w.kind === "quote" && w.id === data.case_id,
  );
  const next = mine
    ? `Việc của bạn: ${label(ACTION, mine.action)}`
    : data.status === "declined"
      ? "Báo giá đã bị từ chối."
      : data.status === "sent_to_design"
        ? "Đang chờ Design phản hồi theo số YCBG."
        : "Không có việc của bạn ở bước này.";
  const firstAnchor = data.lines[0]
    ? Object.values(data.lines[0].anchors)[0]
    : null;
  const firstRegion: SourceRegion | null = anchorRegion(firstAnchor);
  const otherFindings = data.findings.filter(
    (f) => !["rfq_incomplete", "customer_unknown"].includes(f.code),
  );
  const showPricing = [
    "design_replied",
    "priced",
    "returned",
    "pending_approval",
    "approved",
  ].includes(data.status);

  const openLine = (field: string, lineNo: number) => {
    const line = data.lines.find((l) => l.line_no === lineNo);
    const region = anchorRegion(line?.anchors[field] ?? firstAnchor);
    if (region)
      setSource({ region, field, lineNo, attachmentId: data.attachment_id });
  };

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs(
          { title: "Báo giá", href: "/sales/quotes" },
          `RFQ ${data.rfq_no}`,
        )}
        meta={
          <>
            <QuoteStateTag status={data.status} />
            <StatusTag tone="outline" mono>
              Phiên bản {data.case_version}
            </StatusTag>
            {data.ycbg_no ? (
              <StatusTag tone="outline" mono>
                YCBG {data.ycbg_no}
              </StatusTag>
            ) : null}
            {overdue ? (
              <StatusTag tone="err" icon={<ClockCircleOutlined aria-hidden />}>
                Quá hạn
              </StatusTag>
            ) : null}
          </>
        }
        title={`RFQ ${data.rfq_no}`}
        description={`${customer?.name ?? `Khách ${data.customer_code}`} · mã khách ${data.customer_code} · gửi từ ${data.sender}`}
        extra={
          firstRegion ? (
            <Button
              icon={<FileSearchOutlined aria-hidden />}
              onClick={() =>
                setSource({
                  region: firstRegion,
                  attachmentId: data.attachment_id,
                })
              }
            >
              Mở bản gốc
            </Button>
          ) : null
        }
      />

      <CaseSummary
        cells={[
          {
            key: "due",
            label: "Hạn báo giá (giờ Việt Nam)",
            ...(deadline
              ? {
                  value: deadline.absolute,
                  sub: done ? undefined : deadline.relative,
                  tone: done
                    ? undefined
                    : deadline.overdue || deadline.leftMs < DAY
                      ? ("err" as const)
                      : deadline.leftMs < 2 * DAY
                        ? ("warn" as const)
                        : undefined,
                }
              : {
                  value: (
                    <StatusTag
                      tone="unk"
                      icon={<QuestionCircleOutlined aria-hidden />}
                    >
                      Chưa rõ hạn báo giá
                    </StatusTag>
                  ),
                  sub: "DW1 không đọc được hạn trên yêu cầu",
                }),
          },
          {
            key: "received",
            label: "Nhận lúc (giờ Việt Nam)",
            value: formatDateTime(data.received_at, { zoneLabel: false }),
            sub: `${formatAge(data.received_at, now)} trước`,
          },
          {
            key: "flags",
            label: "Cờ của báo giá",
            ...(openFindings
              ? {
                  value: `Còn ${openFindings} cờ chưa quyết định`,
                  tone: "warn" as const,
                }
              : { value: "Không còn cờ", tone: "ok" as const }),
            sub: `${data.lines.length} dòng yêu cầu · tiền tệ ${data.currency}`,
          },
          {
            key: "owner",
            label: "Phụ trách",
            value: data.assigned_to ? name(data.assigned_to) : "Chưa giao",
            sub: next,
          },
        ]}
      />

      <Descriptions
        size="small"
        bordered
        column={{ xs: 1, md: 2 }}
        items={[
          {
            key: "ycbg",
            label: "YCBG",
            children: data.ycbg_no
              ? `${data.ycbg_no} · ${name(data.ycbg_recorded_by)} · ${formatDateTime(data.ycbg_recorded_at)}${
                  data.status === "sent_to_design" && data.ycbg_recorded_at
                    ? ` · đã lập ${daysSince(data.ycbg_recorded_at.slice(0, 10), now) ?? "?"} ngày`
                    : ""
                }`
              : "Chưa lập",
          },
          {
            key: "lang",
            label: "Ngôn ngữ thư nháp",
            children: customer
              ? `${label(LANGUAGE, customer.language)} (${customer.language})`
              : UNKNOWN_TIME,
          },
        ]}
      />

      {data.decline ? (
        <Alert
          type="warning"
          showIcon
          title={`Từ chối báo giá: ${label(DECLINE_REASON, data.decline.reason)}`}
          description={`${name(data.decline.declined_by)} · ${formatDateTime(data.decline.declined_at)}${data.decline.note ? ` · ${data.decline.note}` : ""}`}
        />
      ) : null}
      {data.returns.length ? (
        <Alert
          type={data.status === "returned" ? "warning" : "info"}
          showIcon
          title={`Đã bị trả lại định giá ${data.returns.length} lần`}
          description={data.returns
            .map(
              (r) =>
                `${name(r.returned_by)} · ${formatDateTime(r.returned_at)} · phiên bản ${r.case_version}: ${r.reason}`,
            )
            .join(" | ")}
        />
      ) : null}

      <CaseTimeline procedure="WIV-03-023" status={data.status} next={next} />

      <Card size="small" title="Bước tiếp theo">
        <QuoteActions quote={data} viewer={viewer} onDone={reload} />
      </Card>

      {data.status === "pending_approval" ? (
        <ApprovalPanel quote={data} viewer={viewer} onDone={reload} />
      ) : null}

      <Card size="small" title="Yêu cầu của khách">
        <Table
          size="small"
          rowKey="line_no"
          pagination={false}
          dataSource={data.lines}
          scroll={{ x: "max-content" }}
          columns={[
            { title: "Dòng", dataIndex: "line_no" },
            {
              title: "Mã của khách",
              dataIndex: "customer_item_code",
              render: (c: string | null) => c ?? "Không ghi",
            },
            {
              title: "Mô tả",
              dataIndex: "description",
              render: (text: string) => (
                <Typography.Text
                  ellipsis={{ tooltip: text }}
                  className="max-w-[22rem]"
                >
                  {text}
                </Typography.Text>
              ),
            },
            {
              title: "Số lượng",
              key: "q",
              align: "right",
              render: (_, l) =>
                l.quantity ? (
                  <Quantity value={l.quantity} uom={l.uom} />
                ) : (
                  <StatusTag tone="unk">Chưa có</StatusTag>
                ),
            },
            {
              title: "Ngày cần hàng",
              key: "n",
              render: (_, l) =>
                l.needed_by ? (
                  formatDate(l.needed_by)
                ) : (
                  <StatusTag tone="unk">Chưa có</StatusTag>
                ),
            },
            {
              title: "Giá mong muốn",
              key: "t",
              align: "right",
              render: (_, l) =>
                l.target_price === null ? (
                  "Không ghi"
                ) : (
                  <Money value={l.target_price} currency={currency} />
                ),
            },
            {
              title: "Nguồn",
              key: "src",
              render: (_, l) => (
                <Button
                  size="small"
                  icon={<EyeOutlined aria-hidden />}
                  onClick={() => openLine("description", l.line_no)}
                  aria-label={`Xem nguồn dòng ${l.line_no}`}
                >
                  Xem
                </Button>
              ),
            },
          ]}
        />
      </Card>

      <Card size="small" title="Phản hồi của Design">
        {data.design_reply ? (
          <div className="space-y-2">
            <Typography.Text>
              YCBG {data.design_reply.ycbg_no} · trả lời ngày{" "}
              {formatDate(data.design_reply.reply_date)} · nhận{" "}
              {formatDateTime(data.design_reply.received_at)}
              {data.design_replies > 1
                ? ` · lần phản hồi thứ ${data.design_replies}`
                : ""}{" "}
              <Button
                size="small"
                icon={<EyeOutlined aria-hidden />}
                onClick={() => {
                  const anchor = data.design_reply
                    ? Object.values(
                        data.design_reply.lines[0]?.anchors ?? {},
                      )[0]
                    : null;
                  const region = anchorRegion(anchor);
                  if (region && data.design_reply)
                    setSource({
                      region,
                      attachmentId: data.design_reply.attachment_id,
                    });
                }}
              >
                Xem bản gốc
              </Button>
            </Typography.Text>
            <Table
              size="small"
              rowKey="line_no"
              pagination={false}
              dataSource={data.design_reply.lines}
              scroll={{ x: "max-content" }}
              columns={[
                { title: "Dòng", dataIndex: "line_no" },
                { title: label(FIELD, "bp_code"), dataIndex: "bp_code" },
                {
                  title: label(FIELD, "prv_code"),
                  dataIndex: "prv_code",
                  render: (c: string | null) => c ?? "Design chưa tạo",
                },
                { title: label(FIELD, "spec_no"), dataIndex: "spec_no" },
                {
                  title: label(FIELD, "copper_kg_per_km"),
                  dataIndex: "copper_kg_per_km",
                  render: (c: string | null) =>
                    c ? <Quantity value={c} /> : "Không ghi",
                },
              ]}
            />
          </div>
        ) : (
          <Typography.Text>
            {data.status === "sent_to_design"
              ? "Đang chờ Design. Phản hồi được ghép bằng số YCBG."
              : "Chưa gửi Design."}
          </Typography.Text>
        )}
      </Card>

      {otherFindings.length ? (
        <Card size="small" title="Cờ của báo giá">
          <div className="space-y-2">
            {otherFindings.map((f) => (
              <Card key={f.key} size="small" type="inner">
                <Space wrap>
                  <Typography.Text strong>
                    {label(FINDING_CODE, f.code)}
                    {f.line_no ? ` · dòng ${f.line_no}` : ""}
                  </Typography.Text>
                  <SeverityTag blocking={f.blocking} />
                  <StatusTag tone="gray">
                    {f.disposition.kind === "open"
                      ? "Chưa quyết định"
                      : "Đã ghi nhận khi duyệt"}
                  </StatusTag>
                </Space>
                <Descriptions
                  size="small"
                  column={{ xs: 1, md: 2 }}
                  items={[
                    {
                      key: "e",
                      label: "Mong đợi",
                      children: <FindingWords value={f.expected} />,
                    },
                    {
                      key: "a",
                      label: "Thực tế",
                      children: <FindingWords value={f.actual} />,
                    },
                  ]}
                />
              </Card>
            ))}
          </div>
        </Card>
      ) : null}

      <Card size="small" title="Căn cứ giá">
        <EvidencePanel quote={data} />
      </Card>

      {data.pricing ? (
        <Card size="small" title="Giá đã quyết định">
          <Typography.Paragraph>
            {name(data.pricing.decided_by)} ·{" "}
            {formatDateTime(data.pricing.decided_at)}
            {data.pricing.lme
              ? ` · LME tháng ${formatMonth(data.pricing.lme.month)}`
              : ""}
            {data.earlier_pricing
              ? ` · ${data.earlier_pricing} lần định giá trước được giữ lại`
              : ""}
          </Typography.Paragraph>
          {data.pricing.management_guidance ? (
            <Typography.Paragraph>
              Ghi chú chỉ đạo:{" "}
              <FindingWords value={data.pricing.management_guidance} />
            </Typography.Paragraph>
          ) : null}
          <Table
            size="small"
            rowKey="line_no"
            pagination={false}
            dataSource={data.pricing.lines}
            scroll={{ x: "max-content" }}
            columns={[
              { title: "Dòng", dataIndex: "line_no" },
              {
                title: "Đơn giá",
                key: "p",
                align: "right",
                render: (_, l) => (
                  <Money value={l.unit_price} currency={currency} />
                ),
              },
              {
                title: "MOQ",
                key: "m",
                align: "right",
                render: (_, l) => <Quantity value={l.moq} />,
              },
              {
                title: "Lead time",
                key: "lt",
                render: (_, l) => `${l.lead_time_days} ngày`,
              },
              {
                title: "Căn cứ đồng",
                key: "cu",
                render: (_, l) =>
                  l.copper_basis.kind === "fixed" ? "Cố định" : "Theo dải LME",
              },
            ]}
          />
        </Card>
      ) : null}

      {showPricing ? <PricingForm quote={data} onDone={reload} /> : null}

      <ArtifactsPanel
        kind="quote"
        caseId={data.case_id}
        caseVersion={data.case_version}
        canRender={viewer.hasScope("sales.quote.prepare")}
        renderReason="Bạn không có quyền soạn tệp của báo giá (cần vai Sales phụ trách)."
        language={customer?.language}
        refreshKey={data.case_version}
      />

      <Collapse
        items={[
          {
            key: "facts",
            label: "Căn cứ và dấu vết của hồ sơ",
            children: (
              <Descriptions
                size="small"
                column={{ xs: 1, md: 2 }}
                items={[
                  {
                    key: "rules",
                    label: "Bộ quy tắc",
                    children: data.rules_version,
                  },
                  {
                    key: "parser",
                    label: "Bộ đọc",
                    children: data.parser_version,
                  },
                  {
                    key: "asof",
                    label: "Dữ liệu đến ngày",
                    children: formatDateTime(data.catalog_as_of),
                  },
                  {
                    key: "file",
                    label: "Tệp",
                    children: `${data.attachment_id} · ${data.attachment_sha256.slice(0, 16)}…`,
                  },
                  {
                    key: "release",
                    label: "Bản phát hành",
                    children: data.release_manifest_ref ?? "Không rõ",
                  },
                  {
                    key: "approval",
                    label: "Duyệt",
                    children: data.approval
                      ? `${name(data.approval.approved_by)} · ${formatDateTime(data.approval.approved_at)} · phiên bản ${data.approval.case_version}`
                      : "Chưa",
                  },
                  {
                    key: "sent",
                    label: "Gửi khách",
                    children: data.sent
                      ? `${name(data.sent.by)} · ${formatDateTime(data.sent.at)}`
                      : "Chưa",
                  },
                  {
                    key: "ml",
                    label: "Master list",
                    children: data.master_list
                      ? `${name(data.master_list.by)} · ${formatDateTime(data.master_list.at)}`
                      : "Chưa",
                  },
                  {
                    key: "state",
                    label: "Trạng thái",
                    children: label(QUOTE_STATE, data.status),
                  },
                ]}
              />
            ),
          },
        ]}
      />

      <SourceDrawer
        kind="quote"
        caseId={data.case_id}
        caseVersion={data.case_version}
        attachmentId={source?.attachmentId ?? data.attachment_id}
        target={source}
        onClose={() => setSource(null)}
      />
    </div>
  );
}
