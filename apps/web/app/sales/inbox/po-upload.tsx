"use client";

import { useCallback, useMemo, useState } from "react";
import { Alert, Form, Modal, Select, Typography, Upload } from "antd";
import type { UploadFile } from "antd";
import { InboxOutlined, UploadOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { base64 } from "../_lib/files";
import { messageRef } from "../_lib/messages";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { GuardedButton } from "../_components/guarded-button";

type Uploaded = SalesSchemas["PoUploadView"];

/** At most this many files in one upload (`MAX_UPLOAD_FILES`; the API
 * refuses more and says so). */
const MAX_FILES = 10;

/**
 * "Tải PO lên" (ticket 18): a customer that sends no PO by mail puts it on
 * its portal; the person downloads it, picks the customer here and drops the
 * file. The API stores it as one message whose sender is the person and
 * whose customer is the one picked, scanned and read like any mail, and
 * queues it for DW1. The same file uploaded twice is stored once.
 */
export function PoUpload({
  reason,
  onUploaded,
}: {
  /** Why the person may not upload now (no right, DW1 paused); null if they may. */
  reason: string | null;
  onUploaded: () => void;
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
        Tải PO lên
      </GuardedButton>
      {open ? (
        <UploadDialog
          onClose={() => setOpen(false)}
          onUploaded={() => {
            setOpen(false);
            onUploaded();
          }}
        />
      ) : null}
    </>
  );
}

function UploadDialog({
  onClose,
  onUploaded,
}: {
  onClose: () => void;
  onUploaded: () => void;
}) {
  const customers = useResource(
    "sales/master-data/customers",
    useCallback(() => salesApi().customers(), []),
  );
  const options = useMemo(
    () =>
      (customers.data?.items ?? []).map((c) => ({
        value: c.code,
        label: `${c.code} · ${c.name}`,
      })),
    [customers.data],
  );
  const [customer, setCustomer] = useState<string | null>(null);
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [again, setAgain] = useState<Uploaded | null>(null);
  const { run, pending } = useAction();

  const send = async () => {
    if (!customer) return;
    setError(null);
    setAgain(null);
    const body = {
      customer_code: customer,
      files: await Promise.all(
        files.map(async (f) => ({
          file_name: f.name,
          content_b64: await base64(f.originFileObj as File),
        })),
      ),
    };
    const result = await run(
      "inbox/upload",
      body,
      (key) => salesApi().uploadPo(body, key),
      "Đã lưu PO và xếp cho DW1 xử lý",
    );
    if (!result.ok) {
      setError(result.error);
      return;
    }
    if (result.value.already_stored) {
      // Stored once already: nothing new is queued, and the dialog says so.
      setAgain(result.value);
      return;
    }
    onUploaded();
  };

  const missing = !customer
    ? "Chọn khách hàng của PO."
    : files.length === 0
      ? "Thả hoặc chọn ít nhất một tệp."
      : null;

  return (
    <Modal
      open
      title="Tải PO lên"
      onCancel={onClose}
      footer={
        <GuardedButton
          type="primary"
          reason={missing}
          loading={pending === "inbox/upload"}
          onClick={() => void send()}
        >
          Tải lên
        </GuardedButton>
      }
    >
      <Typography.Paragraph>
        Tệp PO bạn tải từ cổng của khách. DW1 quét mã độc, đọc như PO gửi qua
        thư, và ghi bạn là người tải lên cho khách bạn chọn.
      </Typography.Paragraph>
      <Form layout="vertical">
        <Form.Item label="Khách hàng" required>
          <Select
            showSearch
            optionFilterProp="label"
            options={options}
            loading={customers.loading}
            value={customer}
            onChange={setCustomer}
            placeholder="Chọn khách trong dữ liệu chủ"
            notFoundContent={
              customers.error
                ? "Không tải được danh sách khách."
                : "Không có khách nào khớp."
            }
            aria-label="Khách hàng"
          />
        </Form.Item>
        <Form.Item label="Tệp PO" required>
          <Upload.Dragger
            multiple
            maxCount={MAX_FILES}
            fileList={files}
            beforeUpload={() => false}
            onChange={({ fileList }) => setFiles(fileList)}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined aria-hidden />
            </p>
            <p className="ant-upload-text">Thả tệp vào đây hoặc bấm để chọn</p>
            <p className="ant-upload-hint">
              Tệp CSV, Excel hoặc PDF tải từ cổng khách, tối đa {MAX_FILES} tệp.
            </p>
          </Upload.Dragger>
        </Form.Item>
      </Form>
      {again ? (
        <Alert
          type="info"
          showIcon
          title={`Tệp này đã được tải lên trước đó (thư ${messageRef(again.message_id)}, khách ${again.customer_code}): DW1 không lưu lần nữa.`}
        />
      ) : null}
      <ActionError error={error} />
    </Modal>
  );
}
