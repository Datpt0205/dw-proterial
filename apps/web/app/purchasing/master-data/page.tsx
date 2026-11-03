"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Flex,
  Skeleton,
  Table,
  Tooltip,
  Typography,
  Upload,
  type TableColumnsType,
} from "antd";
import { DownloadOutlined, UploadOutlined } from "@ant-design/icons";
import type { PurchasingMasterImport } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { errorMessage } from "../../../lib/error-message";
import { useIdempotencyKeys } from "../../../lib/idempotency";
import { useAuth } from "../../../lib/auth/auth-context";
import { useCachedResource } from "../../../lib/use-cached-resource";
import { purchasingApi } from "../_lib/api";
import {
  changeWords,
  IMPORT_STATUS,
  MAX_WORKBOOK_BYTES,
  submitBlocked,
  toBase64,
  WORKBOOK_ACCEPT,
} from "../_lib/master-data";
import { usePeople } from "../_lib/people";
import { SCOPE } from "../_lib/scopes";
import { purchasingCrumbs, ScopeGate } from "../_components/frame";

// How often a file the worker is still reading is asked about again.
const POLL_MS = 3000;

/**
 * "Dữ liệu chủ": the company's lists DW2 checks a request against (items,
 * suppliers, quotations on file, prices paid, budgets). Who configures DW2
 * downloads the workbook, fills it in Excel and uploads it whole; DW2 reads
 * it, shows what it would change and which rows it refused, and a second
 * person decides it (the head's own applies at once). Nothing is typed here
 * row by row, and nothing applies before it is decided.
 */
export default function MasterDataPage() {
  return (
    <ScopeGate scope={[SCOPE.propose, SCOPE.rulesApprove]}>
      <MasterData />
    </ScopeGate>
  );
}

function MasterData() {
  const page = useCachedResource(
    "purchasing/master-data",
    useCallback(() => purchasingApi().masterData(), []),
  );
  const reading = page.data?.imports.some((i) => i.status === "queued");
  useEffect(() => {
    if (!reading) return;
    const timer = window.setInterval(page.reload, POLL_MS);
    return () => window.clearInterval(timer);
  }, [reading, page.reload]);

  const data = page.data;
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={purchasingCrumbs("Dữ liệu chủ")}
        title="Dữ liệu chủ"
        help="Danh mục vật tư, nhà cung cấp, báo giá, giá đã mua và ngân sách mà DW2 dùng để kiểm yêu cầu mua hàng. Cập nhật bằng một file Excel theo mẫu; người khác duyệt trước khi áp dụng."
      />
      {page.error && !data ? (
        <LoadError error={page.error} onRetry={page.reload} />
      ) : null}
      {data ? (
        <>
          <InForce data={data} />
          {data.can_upload ? <UploadCard onSent={page.reload} /> : null}
          <Imports imports={data.imports} onSent={page.reload} />
        </>
      ) : page.error ? null : (
        <Skeleton active />
      )}
    </div>
  );
}

type Page = NonNullable<
  Awaited<ReturnType<ReturnType<typeof purchasingApi>["masterData"]>>
>;

function InForce({ data }: { data: Page }) {
  const own = data.layer === "tenant";
  return (
    <Card
      size="small"
      title="Đang dùng"
      extra={
        <StatusTag tone={own ? "ok" : "warn"}>
          {own ? "Dữ liệu của công ty" : "Chưa có dữ liệu"}
        </StatusTag>
      }
    >
      {data.waiting ? (
        <Alert
          className="mb-3"
          type="info"
          showIcon
          message={`Bản ${data.waiting} đang chờ Trưởng phòng Mua hàng duyệt.`}
          action={<Link href="/approvals">Mở trang Duyệt</Link>}
        />
      ) : null}
      {own ? null : (
        <Alert
          className="mb-3"
          type="warning"
          showIcon
          message="Chưa có dữ liệu chủ: yêu cầu mua hàng chưa có giá tham chiếu và ngân sách nên đều đi tới bậc duyệt cao nhất."
        />
      )}
      <Descriptions
        size="small"
        column={{ xs: 1, sm: 2, lg: 5 }}
        items={data.lists.map((l) => ({
          key: l.list,
          label: l.sheet,
          children: `${l.rows} dòng`,
        }))}
      />
    </Card>
  );
}

function UploadCard({ onSent }: { onSent: () => void }) {
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [sending, setSending] = useState(false);
  const [downloading, setDownloading] = useState(false);

  async function template() {
    setDownloading(true);
    try {
      const { blob, filename } = await purchasingApi().masterTemplate();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setDownloading(false);
    }
  }

  async function send(file: File) {
    if (file.size > MAX_WORKBOOK_BYTES) {
      message.error("Tệp lớn hơn 10 MB: bỏ cột hoặc dòng không cần dùng.");
      return;
    }
    const payload = {
      name: file.name,
      size: file.size,
      modified: file.lastModified,
    };
    setSending(true);
    try {
      const content = toBase64(new Uint8Array(await file.arrayBuffer()));
      await purchasingApi().uploadMasterData(
        file.name,
        content,
        keys.keyFor("upload", payload),
      );
      keys.settle("upload");
      message.success(`Đã nhận tệp ${file.name}: DW2 đang đọc.`);
      onSent();
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setSending(false);
    }
  }

  return (
    <Card size="small" title="Cập nhật từ Excel">
      <Flex wrap gap="small" align="center">
        <Button
          icon={<DownloadOutlined aria-hidden />}
          loading={downloading}
          onClick={() => void template()}
        >
          Tải file mẫu
        </Button>
        <Upload
          accept={WORKBOOK_ACCEPT}
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
            loading={sending}
          >
            Tải lên file đã điền
          </Button>
        </Upload>
        <Typography.Text>
          Chỉ cần điền trang muốn cập nhật; trang bỏ trống hoặc xoá khỏi tệp giữ
          như đang dùng.
        </Typography.Text>
      </Flex>
    </Card>
  );
}

function Imports({
  imports,
  onSent,
}: {
  imports: PurchasingMasterImport[];
  onSent: () => void;
}) {
  const name = usePeople();
  const columns: TableColumnsType<PurchasingMasterImport> = [
    { title: "Tệp", dataIndex: "file_name", ellipsis: true },
    {
      title: `Tải lên (${TIME_ZONE_LABEL})`,
      render: (_, i) =>
        `${formatDateTime(i.uploaded_at)} · ${name(i.uploaded_by).name}`,
    },
    {
      title: "Trạng thái",
      render: (_, i) => (
        <StatusTag tone={IMPORT_STATUS[i.status].tone}>
          {IMPORT_STATUS[i.status].label}
        </StatusTag>
      ),
    },
    {
      title: "Dòng bị loại",
      align: "right",
      render: (_, i) => i.rejected_total,
    },
  ];
  return (
    <Card size="small" title="Lần tải lên gần đây">
      <Table
        rowKey="import_id"
        size="small"
        pagination={false}
        scroll={{ x: "max-content" }}
        columns={columns}
        dataSource={imports}
        locale={{
          emptyText: "Chưa tải lên tệp nào. Tải file mẫu, điền rồi tải lên.",
        }}
        expandable={{
          expandedRowRender: (i) => <Preview item={i} onSent={onSent} />,
          defaultExpandedRowKeys:
            imports[0] && imports[0].status !== "submitted"
              ? [imports[0].import_id]
              : [],
        }}
      />
    </Card>
  );
}

function Preview({
  item,
  onSent,
}: {
  item: PurchasingMasterImport;
  onSent: () => void;
}) {
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const proposes = useAuth().hasScope(SCOPE.propose);
  const [sending, setSending] = useState(false);
  const blocked = submitBlocked(item, proposes);

  async function submit() {
    setSending(true);
    try {
      const sent = await purchasingApi().submitMasterData(
        item.import_id,
        keys.keyFor("submit", item.import_id),
      );
      keys.settle("submit");
      message.success(
        `Đã gửi ${sent.version_ref}. Nếu bạn không phải Trưởng phòng Mua hàng, bản này chờ duyệt.`,
      );
      onSent();
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setSending(false);
    }
  }

  if (item.status === "queued")
    return <Typography.Text>DW2 đang quét và đọc tệp này…</Typography.Text>;
  return (
    <div className="space-y-3">
      {item.failure ? (
        <Alert type="error" showIcon message={item.failure} />
      ) : null}
      {item.changes.length ? (
        <Descriptions
          size="small"
          column={1}
          title="So với dữ liệu đang dùng"
          items={item.changes.map((c) => ({
            key: c.list,
            label: c.sheet,
            children: changeWords(c),
          }))}
        />
      ) : null}
      {Object.entries(item.dropped).map(([sheet, n]) => (
        <Alert
          key={sheet}
          type="warning"
          showIcon
          message={`${n} dòng ở trang ${sheet} đang dùng sẽ bị bỏ vì vật tư hoặc nhà cung cấp của chúng không còn trong tệp.`}
        />
      ))}
      {item.rejected.length ? (
        <Table
          rowKey={(r) => `${r.sheet}-${r.row ?? "x"}-${r.reason}`}
          size="small"
          pagination={false}
          title={() =>
            item.rejected_total > item.rejected.length
              ? `Dòng bị loại: ${item.rejected_total} (hiện ${item.rejected.length} dòng đầu)`
              : `Dòng bị loại: ${item.rejected_total}`
          }
          columns={[
            { title: "Trang", dataIndex: "sheet" },
            {
              title: "Dòng",
              dataIndex: "row",
              align: "right",
              render: (r) => r ?? "—",
            },
            { title: "Lý do", dataIndex: "reason" },
          ]}
          dataSource={item.rejected}
        />
      ) : null}
      {item.status === "parsed" ? (
        <Flex gap="small" align="center" wrap>
          <Tooltip title={blocked}>
            <Button
              type="primary"
              disabled={blocked !== null}
              loading={sending}
              onClick={() => void submit()}
            >
              Gửi duyệt
            </Button>
          </Tooltip>
          {blocked ? <Typography.Text>{blocked}</Typography.Text> : null}
        </Flex>
      ) : null}
    </div>
  );
}
