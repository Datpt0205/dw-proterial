"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { InboxOutlined, UploadOutlined } from "@ant-design/icons";
import { Alert, Modal, Table, Tag, Typography, Upload } from "antd";
import type { UploadFile } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { base64 } from "../_lib/files";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { GuardedButton } from "./guarded-button";

type Export = SalesSchemas["BravoExport"];
type Screen = Export["screen"];
type Outcome = Export["outcomes"][number];

/** How often the list is read again while an export waits for the worker. */
const POLL_MS = 5_000;

/** What became of one document of an export, in Sales' words. */
const OUTCOME: Record<Outcome["outcome"], { text: string; color: string }> = {
  recorded: { text: "Đã ghi vào hồ sơ", color: "success" },
  unchanged: { text: "Đã ghi trước đó", color: "default" },
  pending: { text: "Design chưa xong", color: "processing" },
  no_case: { text: "Không hồ sơ nào đang chờ", color: "warning" },
  lines_differ: { text: "Dòng khác yêu cầu", color: "warning" },
  changed: { text: "Khác kết quả đã ghi", color: "warning" },
  unreadable: { text: "Kết quả không đọc được", color: "warning" },
  equal: { text: "Khớp bản đã duyệt", color: "success" },
  differs: { text: "Lệch bản đã duyệt", color: "error" },
  several_cases: { text: "Nhiều hồ sơ cùng số PO", color: "warning" },
  several_sos: { text: "PO nằm dưới nhiều SO", color: "warning" },
};

const STATUS: Record<Export["status"], string> = {
  queued: "DW1 đang đọc",
  read: "Đã đọc",
  failed: "Không đọc được",
};

/** Each screen's words: the button, what the file is, and where a case opens. */
const SCREEN: Record<
  Screen,
  { button: string; file: string; key: string; caseHref: string }
> = {
  ycbg: {
    button: "Kết quả Design từ Bravo",
    file: "Tệp xuất màn hình Phiếu yêu cầu báo giá trên Bravo. DW1 ghi kết quả Design của dòng đã CLOSE vào hồ sơ đang chờ đúng số YCBG đó.",
    key: "Số YCBG",
    caseHref: "/sales/quotes/",
  },
  sales_orders: {
    button: "Đọc lại SO từ Bravo",
    file: "Tệp xuất màn hình Customer order information (Form 1) trên Bravo, sau khi import. DW1 so từng dòng với file dán đã duyệt của hồ sơ cùng khách và số PO.",
    key: "Khách · Số PO",
    caseHref: "/sales/orders/",
  },
};

/**
 * One Bravo screen exported by Sales and dropped here (tickets 16, 03), until
 * the vendor's API reads Bravo. The worker reads it; whatever matches no case
 * surely comes back here for Sales, never onto a guessed case. Nothing is
 * written to Bravo.
 */
export function BravoExportButton({
  screen,
  reason,
}: {
  screen: Screen;
  reason: string | null;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <GuardedButton
        reason={reason}
        inlineReason={false}
        icon={<UploadOutlined aria-hidden />}
        onClick={() => setOpen(true)}
      >
        {SCREEN[screen].button}
      </GuardedButton>
      {open ? (
        <ExportDialog screen={screen} onClose={() => setOpen(false)} />
      ) : null}
    </>
  );
}

function ExportDialog({
  screen,
  onClose,
}: {
  screen: Screen;
  onClose: () => void;
}) {
  const exports = useResource(
    `sales/bravo-exports:${screen}`,
    useCallback(() => salesApi().bravoExports(screen), [screen]),
  );
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [error, setError] = useState<unknown>(null);
  const { run, pending } = useAction();
  const latest = exports.data?.[0] ?? null;
  const reload = exports.reload;

  // Read again while the worker has the latest one.
  useEffect(() => {
    if (latest?.status !== "queued") return;
    const timer = setTimeout(reload, POLL_MS);
    return () => clearTimeout(timer);
  }, [latest, reload]);

  const send = async () => {
    const file = files[0]?.originFileObj as File | undefined;
    if (!file) return;
    setError(null);
    const body = {
      screen,
      file_name: file.name,
      content_b64: await base64(file),
    };
    const result = await run(
      `bravo-exports/${screen}`,
      body,
      (key) => salesApi().uploadBravoExport(body, key),
      "Đã lưu tệp và xếp cho DW1 đọc",
    );
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setFiles([]);
    reload();
  };

  return (
    <Modal
      open
      title={SCREEN[screen].button}
      onCancel={onClose}
      footer={
        <GuardedButton
          type="primary"
          reason={files.length ? null : "Thả hoặc chọn tệp xuất từ Bravo."}
          loading={pending === `bravo-exports/${screen}`}
          onClick={() => void send()}
        >
          Tải lên
        </GuardedButton>
      }
    >
      <Typography.Paragraph>{SCREEN[screen].file}</Typography.Paragraph>
      <Upload.Dragger
        maxCount={1}
        accept=".xlsx,.csv"
        fileList={files}
        beforeUpload={() => false}
        onChange={({ fileList }) => setFiles(fileList.slice(-1))}
      >
        <p className="ant-upload-drag-icon">
          <InboxOutlined aria-hidden />
        </p>
        <p className="ant-upload-text">Thả tệp vào đây hoặc bấm để chọn</p>
        <p className="ant-upload-hint">Tệp .xlsx hoặc .csv, tối đa 2 MB.</p>
      </Upload.Dragger>
      <ActionError error={error} />
      {exports.error ? (
        <LoadError error={exports.error} onRetry={reload} />
      ) : latest ? (
        <LatestExport export={latest} screen={screen} />
      ) : null}
    </Modal>
  );
}

const TO_SALES: ReadonlyArray<Outcome["outcome"]> = [
  "no_case",
  "lines_differ",
  "changed",
  "unreadable",
  "differs",
  "several_cases",
  "several_sos",
];

function LatestExport({
  export: e,
  screen,
}: {
  export: Export;
  screen: Screen;
}) {
  const toSales = e.outcomes.filter(
    (o) => TO_SALES.includes(o.outcome) || o.declined,
  );
  return (
    <div className="mt-4 space-y-2" role="status">
      <Typography.Text strong>
        Lần tải gần nhất: {e.file_name} · {formatDateTime(e.uploaded_at)} ·{" "}
        {STATUS[e.status]}
      </Typography.Text>
      {e.status === "failed" ? (
        <Alert type="error" showIcon title={e.error} />
      ) : null}
      {e.status === "read" ? (
        <>
          <Typography.Text>
            {e.outcomes.length - toSales.length} khớp hoặc đã ghi ·{" "}
            {toSales.length} cần Sales xem
            {e.rejected.length
              ? ` · ${e.rejected.length} dòng không đọc được`
              : ""}
          </Typography.Text>
          <Table
            size="small"
            rowKey="key"
            pagination={false}
            dataSource={e.outcomes}
            scroll={{ x: "max-content" }}
            locale={{ emptyText: "Tệp không có dòng nào để đọc." }}
            columns={[
              { title: SCREEN[screen].key, dataIndex: "key" },
              {
                title: "Kết quả",
                dataIndex: "outcome",
                render: (o: Outcome["outcome"], row: Outcome) => (
                  <>
                    <Tag color={OUTCOME[o].color}>{OUTCOME[o].text}</Tag>
                    {row.differences ? (
                      <Tag color="error">{row.differences} chỗ lệch</Tag>
                    ) : null}
                    {row.declined ? (
                      <Tag color="error">Design từ chối</Tag>
                    ) : null}
                  </>
                ),
              },
              {
                title: "Hồ sơ",
                dataIndex: "case_id",
                render: (id: string | null) =>
                  id ? (
                    <Link
                      href={`${SCREEN[screen].caseHref}${id}`}
                      target="_blank"
                    >
                      Mở hồ sơ
                    </Link>
                  ) : (
                    "—"
                  ),
              },
            ]}
          />
        </>
      ) : null}
    </div>
  );
}
