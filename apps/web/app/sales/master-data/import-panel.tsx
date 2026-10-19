"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Alert,
  App,
  Button,
  Space,
  Table,
  Typography,
  Upload,
  type TableColumnsType,
} from "antd";
import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import { StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import {
  diffSummary,
  IMPORT_ACCEPT,
  IMPORT_STATUS,
  IMPORT_TONE,
  MAX_IMPORT_BYTES,
  shownImport,
  sourceLabel,
  toBase64,
  uploadBlocked,
  type CatalogImport,
  type CatalogListState,
  type CatalogPreview,
} from "../_lib/catalog";
import { ActionError } from "../_lib/errors";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { GuardedButton } from "../_components/guarded-button";
import { saveBlob } from "../_components/artifacts-panel";

// How often a file the worker is still reading is asked about again.
const POLL_MS = 3000;

/**
 * One list's import (ticket 41): where its rows come from now, the template,
 * a file to import, how far the import is, its preview against the list in
 * force, and the submission. Nothing here approves: the head decides on
 * `/approvals`, and the server refuses whoever imported or submitted it.
 */
export function ImportPanel({
  state,
  onChanged,
}: {
  state: CatalogListState;
  onChanged: () => void;
}) {
  const name = usePeople();
  const { message } = App.useApp();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const list = state.catalog_list;
  const source = sourceLabel(state.in_force, name);
  const shown = shownImport(state);
  const blocked = uploadBlocked(state);

  // A file the worker has not read yet: asked about again until it has.
  useEffect(() => {
    if (shown?.status !== "queued") return;
    const timer = window.setInterval(onChanged, POLL_MS);
    return () => window.clearInterval(timer);
  }, [shown?.status, onChanged]);

  const template = async () => {
    try {
      saveBlob(await salesApi().catalogTemplate(list), `mau-${list}.xlsx`);
    } catch (failed) {
      setError(failed);
    }
  };

  const send = async (file: File) => {
    setError(null);
    if (file.size > MAX_IMPORT_BYTES) {
      void message.error("Tệp lớn hơn 2 MB: tách danh mục hoặc bỏ cột thừa.");
      return;
    }
    const body = {
      file_name: file.name,
      content_b64: toBase64(new Uint8Array(await file.arrayBuffer())),
    };
    const result = await run(
      `import/${list}`,
      { list, name: file.name, size: file.size, modified: file.lastModified },
      (key) => salesApi().uploadCatalog(list, body, key),
      `Đã nhận tệp ${file.name}: DW1 đang đọc, bản xem trước hiện ở đây khi đọc xong.`,
    );
    if (result.ok) onChanged();
    else setError(result.error);
  };

  const submit = async (snapshot: CatalogImport) => {
    setError(null);
    const result = await run(
      `submit/${snapshot.snapshot_id}`,
      { snapshot: snapshot.snapshot_id },
      (key) => salesApi().submitCatalog(snapshot.snapshot_id, key),
      "Đã gửi duyệt. Trưởng bộ phận Sales quyết trên trang Duyệt.",
    );
    if (result.ok) onChanged();
    else setError(result.error);
  };

  return (
    <div className="space-y-3">
      <Space wrap align="start">
        <StatusTag tone={source.tone}>
          {source.tone === "warn" ? "Dữ liệu mẫu" : "Dữ liệu thật"}
        </StatusTag>
        <Typography.Text>{source.text}</Typography.Text>
      </Space>
      <Space wrap align="start">
        <GuardedButton
          reason={state.can_import ? null : blocked}
          inlineReason={false}
          icon={<DownloadOutlined aria-hidden />}
          onClick={() => void template()}
        >
          Tải mẫu
        </GuardedButton>
        {blocked ? (
          <GuardedButton reason={blocked} icon={<UploadOutlined aria-hidden />}>
            Nhập file
          </GuardedButton>
        ) : (
          <Upload
            accept={IMPORT_ACCEPT}
            showUploadList={false}
            maxCount={1}
            beforeUpload={(file) => {
              void send(file);
              return false;
            }}
          >
            <Button
              type="primary"
              icon={<UploadOutlined aria-hidden />}
              loading={pending === `import/${list}`}
            >
              Nhập file
            </Button>
          </Upload>
        )}
      </Space>
      <Typography.Paragraph className="!mb-0">
        Tệp .xlsx, .xls hoặc .csv (UTF-8), tối đa 2 MB, dòng đầu là tên cột như
        tệp mẫu. Tệp thay cả danh mục khi được duyệt; chưa có gì áp dụng trước
        khi Trưởng bộ phận Sales duyệt.
      </Typography.Paragraph>
      <ActionError error={error} />
      {shown ? (
        <ImportStatus
          snapshot={shown}
          canPreview={state.can_import}
          submitting={pending === `submit/${shown.snapshot_id}`}
          onSubmit={() => void submit(shown)}
          onReload={onChanged}
        />
      ) : null}
      <History history={state.history} />
    </div>
  );
}

function ImportStatus({
  snapshot,
  canPreview,
  submitting,
  onSubmit,
  onReload,
}: {
  snapshot: CatalogImport;
  canPreview: boolean;
  submitting: boolean;
  onSubmit: () => void;
  onReload: () => void;
}) {
  const name = usePeople();
  const who = `${snapshot.file_name ?? "Đồng bộ ERP"} · ${name(snapshot.imported_by)} · ${formatDateTime(snapshot.imported_at)}`;
  if (snapshot.status === "queued")
    return (
      <Alert
        type="info"
        showIcon
        role="status"
        title={`Đang đọc tệp: ${who}`}
        description="DW1 đọc tệp trong vùng cách ly; trang tự cập nhật khi xong."
        action={<Button onClick={onReload}>Tải lại</Button>}
      />
    );
  if (snapshot.status === "failed")
    return (
      <Alert
        type="error"
        showIcon
        title={`Không đọc được tệp: ${who}`}
        description={snapshot.error ?? "Không rõ lý do."}
      />
    );
  return (
    <div className="space-y-3">
      <Alert
        type={snapshot.status === "submitted" ? "warning" : "info"}
        showIcon
        title={`${IMPORT_STATUS[snapshot.status]}: ${who}`}
        description={
          snapshot.status === "submitted"
            ? `${name(snapshot.submitted_by)} đã gửi duyệt. Người nhập và người gửi không tự duyệt được.`
            : `${snapshot.row_count} dòng hợp lệ, ${snapshot.rejected_count} dòng bị loại. Kiểm tra bản xem trước rồi gửi duyệt.`
        }
        action={
          snapshot.status === "submitted" && snapshot.approval_id ? (
            <Link href={`/approvals/${snapshot.approval_id}`}>
              Mở yêu cầu duyệt
            </Link>
          ) : snapshot.status === "parsed" ? (
            <GuardedButton
              type="primary"
              reason={
                canPreview ? null : "Bạn chưa có quyền gửi duyệt danh mục này."
              }
              loading={submitting}
              onClick={onSubmit}
            >
              Gửi duyệt
            </GuardedButton>
          ) : undefined
        }
      />
      {canPreview ? <Preview snapshotId={snapshot.snapshot_id} /> : null}
    </div>
  );
}

function Preview({ snapshotId }: { snapshotId: string }) {
  const preview = useResource<CatalogPreview>(
    `sales/master-data/imports/${snapshotId}`,
    useCallback(() => salesApi().catalogPreview(snapshotId), [snapshotId]),
  );
  if (preview.error)
    return <LoadError error={preview.error} onRetry={preview.reload} />;
  const data = preview.data;
  const cellColumns: TableColumnsType<{
    key: string;
    cells: Record<string, string>;
  }> = (data?.columns ?? []).map((column) => ({
    title: column,
    key: column,
    render: (_, row) => row.cells[column] ?? "",
  }));
  const paged = { pageSize: 20, hideOnSinglePage: true } as const;
  return (
    <div className="space-y-3" aria-busy={preview.loading}>
      <Typography.Title level={5} className="!mb-0">
        Bản xem trước so với{" "}
        {data?.compared_with.source === "mock"
          ? "dữ liệu mẫu"
          : "bản đang áp dụng"}
      </Typography.Title>
      <Typography.Text role="status">
        {data ? diffSummary(data) : "Đang tải bản xem trước…"}
      </Typography.Text>
      {data && data.unknown_headers.length ? (
        <Alert
          type="warning"
          showIcon
          title={`Cột không dùng (bỏ qua): ${data.unknown_headers.join(", ")}`}
        />
      ) : null}
      <Section title="Dòng thêm mới" count={data?.added.length}>
        <Table
          rowKey="key"
          size="small"
          loading={preview.loading}
          dataSource={data?.added ?? []}
          pagination={paged}
          scroll={{ x: "max-content" }}
          columns={cellColumns}
          locale={{ emptyText: preview.loading ? " " : "Không có dòng mới." }}
        />
      </Section>
      <Section title="Dòng thay đổi" count={data?.changed.length}>
        <Table
          rowKey="key"
          size="small"
          loading={preview.loading}
          dataSource={data?.changed ?? []}
          pagination={paged}
          scroll={{ x: "max-content" }}
          locale={{
            emptyText: preview.loading ? " " : "Không có dòng thay đổi.",
          }}
          columns={[
            { title: "Khóa", dataIndex: "key" },
            {
              title: "Thay đổi (cũ → mới)",
              key: "changes",
              render: (_, row) => (
                <ul className="m-0 list-none p-0">
                  {row.changes.map((change) => (
                    <li key={change.column}>
                      {change.column}: {change.old || "(trống)"} →{" "}
                      {change.new || "(trống)"}
                    </li>
                  ))}
                </ul>
              ),
            },
          ]}
        />
      </Section>
      <Section title="Dòng bị bỏ khi duyệt" count={data?.removed.length}>
        <Table
          rowKey="key"
          size="small"
          loading={preview.loading}
          dataSource={data?.removed ?? []}
          pagination={paged}
          scroll={{ x: "max-content" }}
          columns={cellColumns}
          locale={{
            emptyText: preview.loading ? " " : "Không dòng nào bị bỏ.",
          }}
        />
      </Section>
      <Section
        title="Dòng bị loại (không áp dụng)"
        count={data?.rejected_count}
      >
        <Table
          rowKey={(r) => `${r.row}:${r.column ?? ""}:${r.reason}`}
          size="small"
          loading={preview.loading}
          dataSource={data?.rejected ?? []}
          pagination={paged}
          scroll={{ x: "max-content" }}
          locale={{
            emptyText: preview.loading ? " " : "Không có dòng bị loại.",
          }}
          footer={() =>
            data && data.rejected_count > data.rejected.length
              ? `Hiện ${data.rejected.length}/${data.rejected_count} dòng bị loại đầu tiên.`
              : ""
          }
          columns={[
            {
              title: "Dòng",
              dataIndex: "row",
              align: "right",
              render: (row: number) => (row === 0 ? "Cả tệp" : row),
            },
            {
              title: "Cột",
              dataIndex: "column",
              render: (c: string | null) => c ?? "",
            },
            { title: "Lý do", dataIndex: "reason" },
          ]}
        />
      </Section>
    </div>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number | undefined;
  children: React.ReactNode;
}) {
  return (
    <section aria-label={title} className="space-y-1">
      <Typography.Text strong>
        {title}
        {count === undefined ? "" : ` (${count})`}
      </Typography.Text>
      {children}
    </section>
  );
}

function History({ history }: { history: CatalogImport[] }) {
  const name = usePeople();
  if (!history.length) return null;
  return (
    <section aria-label="Các lần nhập" className="space-y-1">
      <Typography.Text strong>Các lần nhập gần đây</Typography.Text>
      <Table<CatalogImport>
        rowKey="snapshot_id"
        size="small"
        dataSource={history}
        pagination={false}
        scroll={{ x: "max-content" }}
        footer={() => `${history.length} lần nhập gần nhất`}
        columns={[
          {
            title: "Trạng thái",
            key: "status",
            render: (_, s) => (
              <StatusTag tone={IMPORT_TONE[s.status]}>
                {IMPORT_STATUS[s.status]}
              </StatusTag>
            ),
          },
          {
            title: "Tệp",
            key: "file",
            render: (_, s) => s.file_name ?? "Đồng bộ ERP",
          },
          {
            title: `Người nhập (${TIME_ZONE_LABEL})`,
            key: "imported",
            render: (_, s) =>
              `${name(s.imported_by)} · ${formatDateTime(s.imported_at, { zoneLabel: false })}`,
          },
          { title: "Dòng", dataIndex: "row_count", align: "right" },
          { title: "Bị loại", dataIndex: "rejected_count", align: "right" },
          {
            title: "Quyết định",
            key: "decided",
            render: (_, s) =>
              s.decided_by
                ? `${name(s.decided_by)} · ${formatDateTime(s.decided_at, { zoneLabel: false })}${s.comment ? ` · ${s.comment}` : ""}`
                : "",
          },
          {
            title: "Yêu cầu duyệt",
            key: "approval",
            render: (_, s) =>
              s.approval_id ? (
                <Link href={`/approvals/${s.approval_id}`}>
                  Mở yêu cầu duyệt
                </Link>
              ) : (
                ""
              ),
          },
        ]}
      />
    </section>
  );
}
