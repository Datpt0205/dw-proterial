"use client";

import { RegionState } from "@dw/ui";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Segmented,
  Space,
  Typography,
} from "antd";
import type { SalesSchemas, SourceRegion } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { FIELD, label } from "../_lib/labels";
import {
  anchorRegion,
  markServed,
  regionKey,
  regionLabel,
} from "../_lib/served";
import { useResource } from "../_lib/use-resource";
import { PdfPage, type DrawnBox } from "./pdf-page";
import { SheetGrid } from "./sheet-grid";

type Source = SalesSchemas["SourceView"];
type Labelled = SalesSchemas["LabelledAnchor"];

export interface SourceTarget {
  /** The region to open on; the drawer offers the others once it knows them. */
  region: SourceRegion;
  /** The value being checked, drawn stronger: field and line. */
  field?: string;
  lineNo?: number | null;
}

function anchorName(anchor: Labelled): string {
  const field = label(FIELD, anchor.field);
  return anchor.line_no ? `Dòng ${anchor.line_no} · ${field}` : field;
}

function sameAnchor(anchor: Labelled, target: SourceTarget | null): boolean {
  return (
    !!target?.field &&
    anchor.field === target.field &&
    (anchor.line_no ?? null) === (target.lineNo ?? null)
  );
}

/**
 * The original beside the values read from it (V3Source, re-cut): a right
 * drawer, 560–1040 px, full width on a phone. Opening a page or a sheet is
 * what the server records as "served"; the drawer reports each region it was
 * shown so the case's buttons can stop saying "Chưa mở nguồn".
 */
export function SourceDrawer({
  kind,
  caseId,
  caseVersion,
  attachmentId,
  target,
  onClose,
}: {
  kind: "order" | "quote";
  caseId: string;
  caseVersion: number;
  attachmentId: string;
  target: SourceTarget | null;
  onClose: () => void;
}) {
  const [region, setRegion] = useState<SourceRegion | null>(
    target?.region ?? null,
  );
  const [focus, setFocus] = useState<SourceTarget | null>(target);
  useEffect(() => {
    setRegion(target?.region ?? null);
    setFocus(target);
  }, [target]);

  const load = useCallback(() => {
    if (!region) return Promise.reject(new Error("no region"));
    const api = salesApi();
    return kind === "order"
      ? api.orderSource(caseId, attachmentId, region)
      : api.quoteSource(caseId, attachmentId, region);
  }, [kind, caseId, attachmentId, region]);

  const source = useResource<Source>(
    `sales/${kind}/${caseId}/${caseVersion}/source/${attachmentId}/${region ? regionKey(region) : "-"}`,
    load,
    { enabled: !!region },
  );

  useEffect(() => {
    // The server recorded the serve for the version it answered with.
    if (source.data && region)
      markServed(caseId, source.data.case_version, region);
  }, [source.data, region, caseId]);

  const regions = useMemo<SourceRegion[]>(() => {
    const data = source.data;
    if (!data) return region ? [region] : [];
    if (data.kind === "pdf")
      return Array.from({ length: data.page_count ?? 1 }, (_, i) => ({
        page: i + 1,
      }));
    return (data.sheets ?? []).map((sheet) => ({ sheet }));
  }, [source.data, region]);

  const here = useMemo(
    () =>
      (source.data?.anchors ?? []).filter((a) => {
        const r = anchorRegion(a.anchor);
        return r && region && regionKey(r) === regionKey(region);
      }),
    [source.data, region],
  );

  const body = () => {
    if (source.loading) return <RegionState kind="loading" />;
    if (source.error)
      return <LoadError error={source.error} onRetry={source.reload} />;
    const data = source.data;
    if (!data) return null;
    if (data.kind === "pdf" && data.pdf_base64) {
      const boxes: DrawnBox[] = here.flatMap((a, i) =>
        a.anchor.boxes.map((box, j) => ({
          key: `${i}-${j}`,
          box,
          focused: sameAnchor(a, focus),
          label: anchorName(a),
        })),
      );
      return (
        <PdfPage data={data.pdf_base64} page={data.page ?? 1} boxes={boxes} />
      );
    }
    if (data.kind === "sheet" && data.grid) {
      const marked = new Map<string, string>();
      let focused: string | null = null;
      for (const a of here) {
        const ref = a.anchor.cell_ref?.slice(
          a.anchor.cell_ref.lastIndexOf("!") + 1,
        );
        if (!ref) continue;
        marked.set(ref, anchorName(a));
        if (sameAnchor(a, focus)) focused = ref;
      }
      return <SheetGrid grid={data.grid} marked={marked} focused={focused} />;
    }
    return <Empty description="Máy chủ không gửi nội dung cho vùng này." />;
  };

  return (
    <Drawer
      open={!!target}
      onClose={onClose}
      placement="right"
      size="min(1040px, 100vw)"
      title={`Bản gốc${region ? ` · ${regionLabel(region)}` : ""}`}
      destroyOnHidden
    >
      <div className="space-y-3">
        {regions.length > 1 ? (
          <Segmented
            aria-label="Trang hoặc sheet"
            value={region ? regionKey(region) : undefined}
            options={regions.map((r) => ({
              label: regionLabel(r),
              value: regionKey(r),
            }))}
            onChange={(value) => {
              const next = regions.find((r) => regionKey(r) === value);
              if (next) setRegion(next);
            }}
          />
        ) : null}
        {source.data ? (
          <Descriptions
            size="small"
            column={{ xs: 1, md: 2 }}
            items={[
              { key: "file", label: "Tệp", children: attachmentId },
              {
                key: "sha",
                label: "SHA-256",
                children: (
                  <Typography.Text code>
                    {source.data.attachment_sha256.slice(0, 16)}…
                  </Typography.Text>
                ),
              },
              {
                key: "version",
                label: "Phiên bản hồ sơ",
                children: source.data.case_version,
              },
              {
                key: "served",
                label: "Đã mở lúc",
                children: formatDateTime(source.data.served_at),
              },
            ]}
          />
        ) : null}
        {source.data && source.data.case_version !== caseVersion ? (
          <Alert
            type="warning"
            showIcon
            title="Hồ sơ đã có phiên bản mới"
            description="Bản gốc này được mở cho một phiên bản khác của hồ sơ. Tải lại hồ sơ rồi mở lại nguồn trước khi quyết định."
          />
        ) : null}
        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_16rem]">
          <div className="min-w-0">{body()}</div>
          <div>
            <Typography.Title level={5}>
              Giá trị đọc từ vùng này
            </Typography.Title>
            {here.length === 0 ? (
              <Typography.Text>
                Không có giá trị nào đọc từ vùng này.
              </Typography.Text>
            ) : (
              <ul className="m-0 list-none space-y-1 p-0">
                {here.map((a) => (
                  <li
                    key={`${a.field}:${a.line_no ?? "-"}`}
                    className="flex items-center gap-2"
                  >
                    <Button
                      type={sameAnchor(a, focus) ? "primary" : "text"}
                      size="small"
                      onClick={() =>
                        setFocus({
                          region: region!,
                          field: a.field,
                          lineNo: a.line_no,
                        })
                      }
                      aria-pressed={sameAnchor(a, focus)}
                    >
                      {anchorName(a)}
                    </Button>
                    {a.anchor.cell_ref ? (
                      <Typography.Text code>
                        {a.anchor.cell_ref.split("!").pop()}
                      </Typography.Text>
                    ) : null}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        <Space>
          <Button onClick={onClose}>Đóng</Button>
        </Space>
      </div>
    </Drawer>
  );
}
