"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
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
import { EyeOutlined, FileSearchOutlined } from "@ant-design/icons";
import type { SalesSchemas, SourceRegion } from "@dw/api-client";
import { PageHeader, StatusTag, RegionState } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { formatAge, formatDate, formatDateTime } from "../../../../lib/dates";
import { useNow } from "../../../../lib/use-now";
import { salesApi } from "../../_lib/api";
import {
  ACTION,
  CLOSE_REASON,
  FIELD,
  label,
  ORDER_STATE,
} from "../../_lib/labels";
import { usePeople } from "../../_lib/people";
import {
  anchorRegion,
  regionLabel,
  useServedRevision,
  wasServed,
} from "../../_lib/served";
import { coverageStatement } from "../../_lib/statements";
import { useResource } from "../../_lib/use-resource";
import { isOpen } from "../../_lib/order-actions";
import { useSalesViewer } from "../../_lib/viewer";
import { ArtifactsPanel } from "../../_components/artifacts-panel";
import { CaseSummary } from "../../_components/case-summary";
import { CaseTimeline } from "../../_components/case-timeline";
import { salesCrumbs } from "../../_components/crumbs";
import { FindingWords, Money } from "../../_components/money";
import { SCOPE } from "../../_components/sales-frame";
import { ScopeGate } from "../../_components/scope-gate";
import {
  SourceDrawer,
  type SourceTarget,
} from "../../_components/source-drawer";
import { OrderStateTag, ValueStateTag } from "../../_components/tags";
import { OrderActions } from "./actions";
import { CandidatePicker } from "./candidate-picker";
import { FindingsPanel } from "./findings";
import { LinesTable } from "./lines";

type Order = SalesSchemas["OrderCaseView"];
type Anchor = SalesSchemas["SourceAnchor"];

export default function OrderPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <OrderDetail />
    </ScopeGate>
  );
}

/** Where a value of the order was read: a header field, or a line's field. */
function anchorOf(
  order: Order,
  field: string,
  lineNo: number | null,
): Anchor | null {
  if (lineNo === null)
    return (
      order.header_anchors[field] ??
      (field === "total"
        ? order.total_anchor
        : field === "buyer"
          ? order.buyer_anchor
          : null) ??
      null
    );
  const line = order.lines.find((l) => l.line_no === lineNo);
  return line?.anchors[field] ?? line?.anchors.description ?? null;
}

/**
 * The regions the screen expects the server to ask for before prepare and
 * cross-check: the page or sheet the PO number was read on, and every one
 * holding a value that is uncertain or typed by hand. The server's rule
 * (`required_regions`) is the owner; when it asks for more, its 409 names it.
 */
function expectedRegions(order: Order): SourceRegion[] {
  const regions = new Map<string, SourceRegion>();
  const add = (anchor: Anchor | null | undefined) => {
    const region = anchorRegion(anchor);
    if (region) regions.set(JSON.stringify(region), region);
  };
  add(order.header_anchors.po_no);
  for (const flag of order.header_flags) add(order.header_anchors[flag.field]);
  for (const line of order.lines) {
    for (const [field, state] of Object.entries(line.value_states))
      if (state === "uncertain" || state === "hand_entered")
        add(line.anchors[field]);
    for (const flag of line.flags) add(line.anchors[flag.field]);
  }
  return [...regions.values()];
}

function OrderDetail() {
  const { caseId } = useParams<{ caseId: string }>();
  const name = usePeople();
  const now = useNow();
  useServedRevision();
  const order = useResource(
    `sales/order/${caseId}`,
    useCallback(() => salesApi().order(caseId), [caseId]),
  );
  const work = useResource(
    "sales/my-work",
    useCallback(() => salesApi().myWork(), []),
  );
  const customers = useResource(
    "sales/master-data/customers",
    useCallback(() => salesApi().customers(), []),
  );
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [picking, setPicking] = useState<number | null>(null);

  const data = order.data;
  useEffect(() => {
    if (data) document.title = `PO ${data.po_no} · Đơn hàng · Sales`;
  }, [data]);

  const viewer = useSalesViewer();
  const reload = useCallback(() => {
    order.reload();
    work.reload();
  }, [order, work]);

  if (order.loading) return <RegionState kind="loading" />;
  if (order.error || !data)
    return <LoadError error={order.error} onRetry={order.reload} />;

  const required = expectedRegions(data);
  const missing = required.filter(
    (r) => !wasServed(data.case_id, data.case_version, r),
  );
  const mine = (work.data ?? []).find(
    (w) => w.kind === "order" && w.id === data.case_id,
  );
  const next = mine
    ? `Việc của bạn: ${label(ACTION, mine.action)}`
    : data.status === "closed"
      ? `Hồ sơ đã đóng${data.close_reason ? `: ${label(CLOSE_REASON, data.close_reason)}` : ""}.`
      : "Không có việc của bạn ở bước này.";

  const openSource = (field: string, lineNo: number | null) => {
    const anchor = anchorOf(data, field, lineNo);
    const region =
      anchorRegion(anchor) ?? anchorRegion(data.header_anchors.po_no);
    if (region) setSource({ region, field, lineNo });
  };
  const primary = anchorRegion(data.header_anchors.po_no);
  const customer = customers.data?.items.find(
    (c) => c.code === data.customer_code,
  );
  const openCount = data.findings.filter(isOpen).length;
  const blocking = data.findings.filter((f) => isOpen(f) && f.blocking).length;

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs(
          { title: "Đơn hàng", href: "/sales/orders" },
          `PO ${data.po_no}`,
        )}
        tags={
          <>
            <OrderStateTag status={data.status} />
            {data.revision ? (
              <StatusTag tone="outline" mono>
                Rev.{data.revision}
              </StatusTag>
            ) : null}
            <StatusTag tone="outline" mono>
              Phiên bản {data.case_version}
            </StatusTag>
            {data.rules_version ? (
              <StatusTag tone="outline" mono>
                Bộ quy tắc {data.rules_version}
              </StatusTag>
            ) : null}
          </>
        }
        title={`PO ${data.po_no}`}
        subtitle={`${customer?.name ?? `Khách ${data.customer_code}`} · mã khách ${data.customer_code} · ngày PO ${formatDate(data.po_date)}`}
        actions={
          primary ? (
            <Button
              icon={<FileSearchOutlined aria-hidden />}
              onClick={() =>
                setSource({ region: primary, field: "po_no", lineNo: null })
              }
            >
              Mở bản gốc
            </Button>
          ) : null
        }
      />

      {data.superseded_by_case ? (
        <Alert
          type="warning"
          showIcon
          title="Có phiếu mới hơn"
          description={
            <>
              Hồ sơ này đã được thay bằng một hồ sơ khác.{" "}
              <Link href={`/sales/orders/${data.superseded_by_case}`}>
                Mở hồ sơ mới hơn
              </Link>
            </>
          }
        />
      ) : null}
      {data.superseded.length ? (
        <Alert
          type="info"
          showIcon
          title={`Đang xem Rev.${data.revision}: bản mới nhất của PO này`}
          description={`Các bản trước (${data.superseded
            .map(
              (s) => `Rev.${s.revision}, nhận ${formatDateTime(s.received_at)}`,
            )
            .join(
              "; ",
            )}) đã có bản thay thế; mọi kiểm tra đã chạy lại trên bản này.`}
        />
      ) : null}
      {data.duplicate_of_case || data.duplicate_of_so ? (
        <Alert
          type="warning"
          showIcon
          title="PO gửi trùng"
          description={
            data.duplicate_of_case ? (
              <Link href={`/sales/orders/${data.duplicate_of_case}`}>
                Mở hồ sơ gốc
              </Link>
            ) : (
              `Trùng đơn Bravo ${data.duplicate_of_so}`
            )
          }
        />
      ) : null}
      {data.returned_reason ? (
        <Alert
          type="warning"
          showIcon
          title="Đơn bị trả lại sau kiểm chéo"
          description={`${name(data.returned_by)} trả lại lúc ${formatDateTime(data.returned_at)}. Lý do: ${data.returned_reason}`}
        />
      ) : null}

      <CaseSummary
        cells={[
          {
            key: "customer",
            label: "Khách hàng",
            value: customer?.name ?? data.customer_code,
            sub: `${data.lines.length} dòng · tiền tệ ${data.currency}`,
          },
          {
            key: "received",
            label: "Nhận lúc (giờ Việt Nam)",
            value: formatDateTime(data.received_at, { zoneLabel: false }),
            sub: `${formatAge(data.received_at, now)} trước`,
          },
          {
            key: "check",
            label: "Kiểm tra",
            ...(blocking
              ? { value: `Còn ${blocking} cờ chặn`, tone: "err" as const }
              : openCount
                ? {
                    value: `Còn ${openCount} cờ, không chặn`,
                    tone: "warn" as const,
                  }
                : { value: "Không còn cờ", tone: "ok" as const }),
            sub: `${openCount} cờ chưa quyết định / ${data.findings.length} cờ`,
          },
          {
            key: "owner",
            label: "Phụ trách",
            value: data.assigned_to ? name(data.assigned_to) : "Chưa giao",
            sub: next,
          },
        ]}
      />

      <CaseTimeline procedure="WIV-03-012" status={data.status} next={next} />

      <Card size="small" title="Bước tiếp theo">
        <Space orientation="vertical" className="w-full">
          <OrderActions
            order={data}
            viewer={viewer}
            sourceOpened={missing.length === 0}
            onChanged={reload}
          />
          {missing.length && data.status !== "closed" ? (
            <Typography.Text role="note">
              Chưa mở nguồn: {missing.map(regionLabel).join(", ")} của phiên bản{" "}
              {data.case_version}.{" "}
              <Button
                size="small"
                icon={<EyeOutlined aria-hidden />}
                onClick={() =>
                  setSource({
                    region: missing[0]!,
                    field: "po_no",
                    lineNo: null,
                  })
                }
              >
                Mở nguồn
              </Button>
            </Typography.Text>
          ) : null}
        </Space>
      </Card>

      <Alert
        type={data.coverage.unchecked_regions.length ? "warning" : "info"}
        showIcon
        title={`Phạm vi đã kiểm: ${coverageStatement(data)}.`}
        description={
          data.coverage.unchecked_regions.length
            ? `Chưa kiểm: ${data.coverage.unchecked_regions.join(", ")}. Phần này chưa được kiểm, không phải đã đạt.`
            : undefined
        }
      />

      <FindingsPanel
        order={data}
        viewer={viewer}
        onChanged={reload}
        onOpenSource={openSource}
        onPickCode={setPicking}
      />

      <Card
        size="small"
        title="Các dòng DW1 đọc"
        extra={
          <span>
            Tổng trên PO: <Money value={data.total} currency={data.currency} />
          </span>
        }
      >
        <LinesTable
          order={data}
          viewer={viewer}
          onChanged={reload}
          onOpenSource={openSource}
          onPickCode={setPicking}
        />
      </Card>

      <ArtifactsPanel
        kind="order"
        caseId={data.case_id}
        caseVersion={data.case_version}
        canRender={viewer.hasScope("sales.order.prepare")}
        renderReason="Bạn không có quyền soạn tệp của đơn hàng (cần vai Sales phụ trách)."
        language={customer?.language}
        refreshKey={data.case_version}
      />

      {data.changes.length ? (
        <Card
          size="small"
          title={`Thay đổi của Rev.${data.revision} so với bản trước`}
        >
          <Table
            size="small"
            pagination={false}
            rowKey={(c) => `${c.line_no}:${c.field}`}
            dataSource={data.changes}
            scroll={{ x: "max-content" }}
            columns={[
              { title: "Dòng", dataIndex: "line_no" },
              {
                title: "Trường",
                dataIndex: "field",
                render: (f: string) => label(FIELD, f),
              },
              {
                title: "Trước",
                key: "before",
                render: (_, c) => <FindingWords value={c.before} />,
              },
              {
                title: "Sau",
                key: "after",
                render: (_, c) => <FindingWords value={c.after} />,
              },
            ]}
          />
        </Card>
      ) : null}

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
                    children: data.rules_version ?? "Chưa kiểm",
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
                    key: "cross",
                    label: "Cần kiểm chéo",
                    children:
                      data.cross_check_required === false ? "Không" : "Có",
                  },
                  {
                    key: "prep",
                    label: "Chuẩn bị",
                    children: data.prepared_by
                      ? `${name(data.prepared_by)} · ${formatDateTime(data.prepared_at)}`
                      : "Chưa",
                  },
                  {
                    key: "bravo",
                    label: "Nhập Bravo",
                    children: data.bravo_so_no
                      ? `${data.bravo_so_no} · ${name(data.bravo_recorded_by)} · ${formatDateTime(data.bravo_recorded_at)}${data.bravo_entry_compared ? " · đã đối chiếu với PO" : ""}`
                      : "Chưa",
                  },
                  {
                    key: "check",
                    label: "Kiểm chéo",
                    children: data.cross_checked_by
                      ? `${name(data.cross_checked_by)} · ${formatDateTime(data.cross_checked_at)}`
                      : "Chưa",
                  },
                  {
                    key: "confirm",
                    label: "Xác nhận",
                    children: data.confirmed_by
                      ? `${name(data.confirmed_by)} · ${formatDateTime(data.confirmed_at)}`
                      : "Chưa",
                  },
                  {
                    key: "makers",
                    label: "Người làm (không tự kiểm chéo)",
                    children: data.makers.length
                      ? data.makers.map(name).join(", ")
                      : "Chưa có",
                  },
                  {
                    key: "header",
                    label: "Đầu PO",
                    children: (
                      <Space wrap>
                        {Object.keys(data.header_anchors).map((field) => (
                          <Button
                            key={field}
                            size="small"
                            type="text"
                            onClick={() => openSource(field, null)}
                          >
                            {label(FIELD, field)}{" "}
                            <ValueStateTag
                              state={
                                data.header_flags.some((f) => f.field === field)
                                  ? "uncertain"
                                  : "dw"
                              }
                            />
                          </Button>
                        ))}
                      </Space>
                    ),
                  },
                  {
                    key: "state",
                    label: "Trạng thái",
                    children: label(ORDER_STATE, data.status),
                  },
                ]}
              />
            ),
          },
        ]}
      />

      <SourceDrawer
        kind="order"
        caseId={data.case_id}
        caseVersion={data.case_version}
        attachmentId={data.attachment_id}
        target={source}
        onClose={() => setSource(null)}
      />
      {picking !== null ? (
        <CandidatePicker
          order={data}
          lineNo={picking}
          onClose={() => setPicking(null)}
          onDone={reload}
          onOpenSource={openSource}
        />
      ) : null}
    </div>
  );
}
