"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Alert,
  App,
  Button,
  DatePicker,
  Drawer,
  Flex,
  Form,
  Typography,
  Upload,
} from "antd";
import { UploadOutlined } from "@ant-design/icons";
import type { Dayjs } from "dayjs";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, fromPickerDay } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { toBase64 } from "../_lib/catalog";
import { ActionError } from "../_lib/errors";
import { nextVersion } from "../_lib/rules";
import {
  MAX_EXAMPLE_BYTES,
  submitBlocked,
  type SalesOrderExample,
} from "../_lib/salesorder-examples";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { GuardedButton } from "../_components/guarded-button";
import { SalesOrderPairs } from "../_components/salesorder-pairs";
import { SalesOrderReplay } from "../_components/salesorder-replay";

// How often an example the worker is still reading is asked about again.
const POLL_MS = 3000;
const KEY = "sales_salesorder_rules";

/**
 * A customer's SalesOrder rules learned from one worked example (ticket 38,
 * dw_sales ADR 0013), on the customer's row of the master data: the person
 * uploads the customer's PO and the SalesOrder file the PIC made from it,
 * with the day the PO came in; DW reads both, proposes the rules and replays
 * them on the PO cell by cell. "Gửi duyệt" opens only when nothing differs
 * (the server refuses otherwise), and the head decides on `/approvals`,
 * never the person who sent it.
 */
export function SalesOrderLearning({
  customerCode,
  onClose,
}: {
  customerCode: string;
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [po, setPo] = useState<File | null>(null);
  const [salesorder, setSalesorder] = useState<File | null>(null);
  const [received, setReceived] = useState<Dayjs | null>(null);
  const [sentApproval, setSentApproval] = useState<string | null>(null);
  const examples = useResource(
    `sales/salesorder-examples/${customerCode}`,
    useCallback(
      () => salesApi().salesOrderExamples(customerCode),
      [customerCode],
    ),
  );
  const latest: SalesOrderExample | undefined = examples.data?.[0];

  // An example the worker has not learned yet: asked about again until it has.
  useEffect(() => {
    if (latest?.status !== "queued") return;
    const timer = window.setInterval(examples.reload, POLL_MS);
    return () => window.clearInterval(timer);
  }, [latest?.status, examples.reload]);

  const pick = (set: (file: File | null) => void) => (file: File) => {
    if (file.size > MAX_EXAMPLE_BYTES) {
      void message.error("Tệp lớn hơn 5 MB.");
      return false;
    }
    set(file);
    return false;
  };

  const encoded = async (file: File) => ({
    file_name: file.name,
    content_b64: toBase64(new Uint8Array(await file.arrayBuffer())),
  });

  const learn = async () => {
    const day = fromPickerDay(received);
    if (!po || !salesorder || !day) return;
    setError(null);
    const body = {
      received_on: day,
      po: await encoded(po),
      salesorder: await encoded(salesorder),
    };
    const result = await run(
      `learn/${customerCode}`,
      {
        customerCode,
        po: [po.name, po.size],
        so: [salesorder.name, salesorder.size],
        day,
      },
      (key) => salesApi().requestSalesOrderExample(customerCode, body, key),
      "Đã nhận hai tệp: DW đang đọc và chạy lại, kết quả hiện ở đây.",
    );
    if (result.ok) examples.reload();
    else setError(result.error);
  };

  const submit = async (example: SalesOrderExample) => {
    setError(null);
    const result = await run(
      `submit/${example.example_id}`,
      { example: example.example_id },
      async (key) => {
        const rules = await salesApi().rules();
        const refs = [
          rules.in_force[KEY] ?? "",
          ...rules.versions.filter((v) => v.key === KEY).map((v) => v.ref),
          ...rules.platform.filter((p) => p.key === KEY).map((p) => p.ref),
        ].filter(Boolean);
        return salesApi().submitSalesOrderExample(
          example.example_id,
          { version: nextVersion(refs) },
          key,
        );
      },
      "Đã gửi duyệt. Trưởng bộ phận Sales quyết trên trang Duyệt.",
    );
    if (result.ok) {
      setSentApproval(result.value.approval_id ?? null);
      examples.reload();
    } else setError(result.error);
  };

  const missing = !po
    ? "Chọn tệp PO gốc của khách."
    : !salesorder
      ? "Chọn tệp SalesOrder PIC đã làm từ PO đó."
      : !received
        ? "Chọn ngày nhận PO."
        : null;

  return (
    <Drawer
      open
      onClose={onClose}
      title={`Quy tắc SalesOrder của khách ${customerCode}`}
      size="large"
    >
      <Flex vertical gap="middle">
        <Typography.Paragraph className="!mb-0">
          Tải một PO gốc của khách và tệp SalesOrder PIC đã làm từ PO đó. DW đề
          xuất quy tắc từng cột rồi chạy lại trên chính PO đó; chỉ gửi duyệt
          được khi mọi ô khớp tệp của PIC.
        </Typography.Paragraph>
        <Form layout="vertical" requiredMark onFinish={() => void learn()}>
          <Form.Item label="Ngày nhận PO" required>
            <DatePicker
              format="DD/MM/YYYY"
              value={received}
              onChange={setReceived}
              aria-label="Ngày nhận PO"
            />
          </Form.Item>
          <Form.Item label="PO gốc của khách (.xlsx, .xls, .pdf)" required>
            <Upload
              accept=".xlsx,.xls,.pdf"
              maxCount={1}
              showUploadList={false}
              beforeUpload={pick(setPo)}
            >
              <Button icon={<UploadOutlined aria-hidden />}>
                {po ? po.name : "Chọn tệp PO"}
              </Button>
            </Upload>
          </Form.Item>
          <Form.Item label="Tệp SalesOrder PIC đã làm (.xlsx)" required>
            <Upload
              accept=".xlsx"
              maxCount={1}
              showUploadList={false}
              beforeUpload={pick(setSalesorder)}
            >
              <Button icon={<UploadOutlined aria-hidden />}>
                {salesorder ? salesorder.name : "Chọn tệp SalesOrder"}
              </Button>
            </Upload>
          </Form.Item>
          <GuardedButton
            type="primary"
            htmlType="submit"
            reason={missing}
            loading={pending === `learn/${customerCode}`}
          >
            Học quy tắc
          </GuardedButton>
        </Form>
        <ActionError error={error} />
        {examples.error ? (
          <LoadError error={examples.error} onRetry={examples.reload} />
        ) : latest ? (
          <Flex vertical gap="small">
            <Typography.Title level={5} className="!mb-0">
              Ví dụ gần nhất: {latest.po_file_name} ·{" "}
              {formatDateTime(latest.requested_at)}
            </Typography.Title>
            <SalesOrderReplay example={latest} />
            <Flex wrap gap="small" align="center">
              <GuardedButton
                type="primary"
                reason={submitBlocked(latest)}
                loading={pending === `submit/${latest.example_id}`}
                onClick={() => void submit(latest)}
              >
                Gửi duyệt
              </GuardedButton>
              {sentApproval ? (
                <Link href={`/approvals/${sentApproval}`}>
                  Mở yêu cầu duyệt
                </Link>
              ) : null}
            </Flex>
          </Flex>
        ) : examples.loading ? null : (
          <Alert
            type="info"
            showIcon
            title="Khách này chưa có ví dụ nào: tệp SalesOrder theo mẫu tệp nhập của công ty."
          />
        )}
        <SalesOrderPairs customerCode={customerCode} />
      </Flex>
    </Drawer>
  );
}
