"use client";

import { useState } from "react";
import {
  DownloadOutlined,
  PrinterOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { Alert, Button, Card, Flex, Typography, Upload } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../../lib/auth/auth-context";
import { formatDateTime } from "../../../../lib/dates";
import { errorMessage } from "../../../../lib/error-message";
import { saveBlob } from "../../_components/artifacts-panel";
import { GuardedButton } from "../../_components/guarded-button";
import { salesApi } from "../../_lib/api";
import { base64, SCAN_ACCEPT, SCAN_MAX_BYTES } from "../../_lib/files";
import { usePeople } from "../../_lib/people";
import { useAction } from "../../_lib/use-action";

type Quote = SalesSchemas["QuoteCaseView"];
type Artifact = SalesSchemas["ArtifactView"];

/** The statuses a quotation is signed in (`SIGNABLE`). */
export const SIGNABLE = new Set(["approved", "sent", "master_list_recorded"]);

/**
 * Q8–Q10 without an electronic signature (Đạt, 2026-10-28): once the
 * quotation is approved, the PIC downloads it to print and have it signed, or
 * sends it as it is. The signed copy may come back as a scan or a photo, kept
 * with the case and attached to the send draft drawn after it; or the PIC
 * signs and sends it themselves, and DW1 keeps nothing more.
 */
export function SendPanel({
  quote,
  artifacts,
  onChanged,
}: {
  quote: Quote;
  artifacts: Artifact[];
  onChanged: () => void;
}) {
  const { hasScope } = useAuth();
  const name = usePeople();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const finals = artifacts.filter(
    (a) => a.kind === "quotation_final" && a.downloadable,
  );
  const pdf = finals.find((a) => a.content_type === "application/pdf");
  const signed = artifacts.find(
    (a) =>
      a.kind === "quote_signed" &&
      a.artifact_id === quote.signed_copy?.artifact_id,
  );
  const reason =
    hasScope("sales.quote.prepare") && hasScope("sales.price.read")
      ? null
      : "Tải lên bản đã ký cần vai Sales phụ trách và quyền xem giá.";

  const download = async (artifact: Artifact) => {
    try {
      saveBlob(
        await salesApi().downloadArtifact(
          "quote",
          quote.case_id,
          artifact.artifact_id,
        ),
        artifact.file_name,
      );
    } catch (failure) {
      setError(failure);
    }
  };

  // The browser's own PDF viewer prints it: a new tab, not a hidden frame a
  // popup blocker or a missing plugin would swallow without a word.
  const print = async (artifact: Artifact) => {
    try {
      const blob = await salesApi().downloadArtifact(
        "quote",
        quote.case_id,
        artifact.artifact_id,
      );
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (failure) {
      setError(failure);
    }
  };

  const upload = async (file: File) => {
    if (file.size > SCAN_MAX_BYTES) {
      setError(new Error("Bản đã ký phải nhỏ hơn 10 MB."));
      return;
    }
    const content = await base64(file);
    const result = await run(
      `signed/${quote.case_id}`,
      { size: file.size, name: file.name, version: quote.case_version },
      (key) =>
        salesApi().uploadSignedQuote(
          quote.case_id,
          quote.case_version,
          content,
          key,
        ),
      "Đã lưu bản báo giá đã ký vào hồ sơ",
    );
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };

  return (
    <Card size="small" title="Gửi báo giá cho khách">
      <Flex vertical gap={12}>
        <Typography.Text>
          Báo giá đã được duyệt. Tải tài liệu để in trình ký, hoặc gửi thẳng cho
          khách. DW1 không dùng chữ ký điện tử.
        </Typography.Text>

        <Flex vertical gap={6}>
          <Typography.Text strong>1. Tài liệu báo giá</Typography.Text>
          {finals.length ? (
            <Flex wrap gap={8}>
              {finals.map((a) => (
                <Button
                  key={a.artifact_id}
                  icon={<DownloadOutlined aria-hidden />}
                  onClick={() => void download(a)}
                >
                  {a.content_type === "application/pdf"
                    ? "Tải PDF"
                    : "Tải Excel"}
                </Button>
              ))}
              {pdf ? (
                <Button
                  icon={<PrinterOutlined aria-hidden />}
                  onClick={() => void print(pdf)}
                >
                  Mở bản PDF để in
                </Button>
              ) : null}
            </Flex>
          ) : (
            <Typography.Text>
              Chưa soạn tài liệu báo giá: bấm “Soạn Tài liệu báo giá (bản đã
              duyệt)” ở khung “Tệp và thư nháp DW1 soạn” bên dưới.
            </Typography.Text>
          )}
        </Flex>

        <Flex vertical gap={6}>
          <Typography.Text strong>2. Bản đã ký (nếu có)</Typography.Text>
          {quote.signed_copy ? (
            <Flex wrap gap={8} align="center">
              <Typography.Text>
                Đã tải lên: {name(quote.signed_copy.uploaded_by)} lúc{" "}
                {formatDateTime(quote.signed_copy.uploaded_at)}.
              </Typography.Text>
              {signed ? (
                <Button
                  icon={<DownloadOutlined aria-hidden />}
                  onClick={() => void download(signed)}
                >
                  Tải bản đã ký
                </Button>
              ) : null}
            </Flex>
          ) : (
            <Typography.Text>
              Sau khi trưởng bộ phận ký, quét hoặc chụp bản ký (PDF, JPG, PNG)
              và tải lên để lưu cùng hồ sơ. Không bắt buộc.
            </Typography.Text>
          )}
          <Upload
            accept={SCAN_ACCEPT}
            showUploadList={false}
            disabled={reason !== null}
            beforeUpload={(file) => {
              void upload(file);
              return false;
            }}
          >
            <GuardedButton
              reason={reason}
              icon={<UploadOutlined aria-hidden />}
              loading={pending === `signed/${quote.case_id}`}
            >
              {quote.signed_copy ? "Tải lên bản khác" : "Tải lên bản đã ký"}
            </GuardedButton>
          </Upload>
        </Flex>

        {quote.status === "approved" ? (
          <Flex vertical gap={6}>
            <Typography.Text strong>3. Gửi khách</Typography.Text>
            <Typography.Text>
              Soạn “Thư gửi báo giá (nháp)” ở khung bên dưới (thư nháp đính kèm
              bản đã ký nếu đã tải lên), rồi bấm “Gửi cho khách từ hộp thư của
              bạn”: hồ sơ tự chuyển “Đã gửi khách” khi thư đi. Hoặc tải tệp
              .eml, tự gửi, rồi bấm “Đã gửi khách” ở “Bước tiếp theo”.
            </Typography.Text>
          </Flex>
        ) : null}

        {error ? (
          <Alert type="error" showIcon title={errorMessage(error)} />
        ) : null}
      </Flex>
    </Card>
  );
}
