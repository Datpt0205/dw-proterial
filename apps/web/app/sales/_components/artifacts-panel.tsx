"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Card, Space, Table, Typography } from "antd";
import { StatusTag } from "@dw/ui";
import { DownloadOutlined, FileAddOutlined } from "@ant-design/icons";
import type { Artifact, SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { formatQuantity } from "../../../lib/money";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { ARTIFACT_KIND, label, LANGUAGE } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource, type Resource } from "../_lib/use-resource";
import { GuardedButton } from "./guarded-button";
import { PAUSED_REASON, useSalesFrame } from "./sales-frame";

/** Save a file the browser holds, under the name the server listed. */
export function saveBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export type CaseArtifacts = Resource<SalesSchemas["ArtifactListView"]>;

/**
 * The case's file list, read once by the page and handed to every panel that
 * shows it (the files panel, the quote approval's preview), so a render in one
 * is seen by all without a second copy to tell. Read again when the case
 * changes (`refreshKey`, the case version) and after a render.
 */
export function useCaseArtifacts(
  kind: "order" | "quote",
  caseId: string,
  /** The case version; `undefined` while the case itself is loading. */
  refreshKey: number | undefined,
): CaseArtifacts {
  const list = useResource(
    `sales/${kind}/${caseId}/artifacts`,
    useCallback(() => salesApi().artifacts(kind, caseId), [kind, caseId]),
    // Read once the case is: a case the viewer may not open lists nothing.
    { enabled: refreshKey !== undefined },
  );
  const reload = list.reload;
  const seen = useRef(refreshKey);
  useEffect(() => {
    if (seen.current === refreshKey) return;
    const first = seen.current === undefined;
    seen.current = refreshKey;
    // The first version to arrive is the one the list was just read at.
    if (!first) reload();
  }, [refreshKey, reload]);
  return list;
}

/**
 * The files DW1 renders from a case (V3BidDrafts re-cut): the upload file,
 * the cross-check sheet and every draft, each with its template, the case
 * version it was rendered at and its hash, so what is sent is what was
 * checked. A kind is offered for rendering only while the API lists it as
 * available; a download is refused by the API before its state, after an
 * edit made it stale, and for a price-bearing file without the price scope.
 * While DW1 is paused, rendering is DW1's work and is refused (the server's
 * `worker_paused`); a file already rendered still downloads.
 */
export function ArtifactsPanel({
  kind,
  caseId,
  caseVersion,
  canRender,
  renderReason,
  language,
  list,
}: {
  kind: "order" | "quote";
  caseId: string;
  caseVersion: number;
  canRender: boolean;
  /** Why rendering is refused for this viewer, in words. */
  renderReason: string;
  /** `Customer.language`: the language the drafts are written in. */
  language?: string | null;
  /** The page's one copy of the file list (`useCaseArtifacts`). */
  list: CaseArtifacts;
}) {
  const name = usePeople();
  const { paused } = useSalesFrame();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const reload = list.reload;
  const refused = !canRender ? renderReason : paused ? PAUSED_REASON : null;

  const artifacts = list.data?.artifacts ?? [];
  const current = new Set(
    artifacts.filter((a) => a.case_version === caseVersion).map((a) => a.kind),
  );
  const toRender = (list.data?.available ?? []).filter((k) => !current.has(k));

  const render = async (artifactKind: string) => {
    const body = { case_version: caseVersion, kind: artifactKind };
    const result = await run(
      `render/${artifactKind}`,
      body,
      (key) => salesApi().renderArtifact(kind, caseId, body, key),
      `DW1 đã soạn: ${label(ARTIFACT_KIND, artifactKind)}`,
    );
    if (result.ok) {
      setError(null);
      reload();
    } else setError(result.error);
  };

  const download = async (artifact: Artifact) => {
    setError(null);
    try {
      saveBlob(
        await salesApi().downloadArtifact(kind, caseId, artifact.artifact_id),
        artifact.file_name,
      );
    } catch (failure) {
      setError(failure);
    }
  };

  return (
    <Card
      size="small"
      title="Tệp và thư nháp DW1 soạn"
      extra={
        language ? (
          <span>Thư nháp viết bằng {label(LANGUAGE, language)}</span>
        ) : null
      }
    >
      {list.error ? (
        <LoadError error={list.error} onRetry={reload} />
      ) : (
        <div className="space-y-3">
          {toRender.length ? (
            <Space wrap align="start">
              {toRender.map((k) => (
                <GuardedButton
                  key={k}
                  icon={<FileAddOutlined aria-hidden />}
                  reason={refused}
                  inlineReason={false}
                  loading={pending === `render/${k}`}
                  onClick={() => render(k)}
                >
                  Soạn {label(ARTIFACT_KIND, k)}
                </GuardedButton>
              ))}
            </Space>
          ) : null}
          <Table<Artifact>
            size="small"
            rowKey="artifact_id"
            loading={list.loading}
            dataSource={artifacts}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: list.loading
                ? " "
                : toRender.length
                  ? "Chưa soạn tệp nào. Bấm “Soạn …” ở trên để DW1 soạn từ hồ sơ."
                  : "Chưa có tệp nào ở bước này.",
            }}
            columns={[
              {
                title: "Tệp",
                key: "kind",
                render: (_, a) => label(ARTIFACT_KIND, a.kind),
              },
              {
                title: "Phiên bản hồ sơ",
                key: "v",
                render: (_, a) =>
                  a.case_version === caseVersion ? (
                    `${a.case_version} (hiện tại)`
                  ) : (
                    <StatusTag tone="warn">{`${a.case_version}: đã có phiên bản mới hơn`}</StatusTag>
                  ),
              },
              {
                title: "Mẫu",
                dataIndex: "template_ref",
                render: (t: string) => (
                  <Typography.Text code>{t}</Typography.Text>
                ),
              },
              {
                title: "SHA-256",
                dataIndex: "sha256",
                render: (h: string) => (
                  <Typography.Text code>{h.slice(0, 16)}…</Typography.Text>
                ),
              },
              {
                title: "Soạn lúc",
                key: "at",
                render: (_, a) =>
                  `${formatDateTime(a.created_at)} · ${name(a.created_by)}`,
              },
              {
                title: "Cỡ",
                dataIndex: "size_bytes",
                align: "right",
                render: (n: number) =>
                  `${formatQuantity(Math.ceil(n / 1024))} KB`,
              },
              {
                title: "Tải",
                key: "dl",
                fixed: "right",
                render: (_, a) => (
                  <GuardedButton
                    size="small"
                    icon={<DownloadOutlined aria-hidden />}
                    inlineReason={false}
                    reason={
                      a.downloadable
                        ? null
                        : a.case_version !== caseVersion
                          ? "Tệp soạn ở phiên bản cũ: soạn lại từ phiên bản hiện tại."
                          : "Chưa tải được tệp này ở bước hiện tại, hoặc vai của bạn không xem giá."
                    }
                    onClick={() => download(a)}
                    aria-label={`Tải ${label(ARTIFACT_KIND, a.kind)}`}
                  >
                    Tải
                  </GuardedButton>
                ),
              },
            ]}
          />
          <ActionError error={error} />
        </div>
      )}
    </Card>
  );
}

/** For the approval: the newest PDF of `artifactKind` at this version, if any. */
export function latestPdf(
  artifacts: readonly Artifact[],
  caseVersion: number,
  artifactKind: string,
): Artifact | null {
  return (
    artifacts
      .filter(
        (a) =>
          a.kind === artifactKind &&
          a.case_version === caseVersion &&
          a.content_type === "application/pdf",
      )
      .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0] ?? null
  );
}

/** Bytes as the base64 the PDF renderer takes. */
export async function blobBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000)
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}
