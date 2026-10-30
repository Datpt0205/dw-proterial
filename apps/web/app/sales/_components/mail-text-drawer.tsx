"use client";

import { useEffect } from "react";
import { Drawer, Space, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { RegionState } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { FIELD, label } from "../_lib/labels";
import { useResource } from "../_lib/use-resource";

type MessageText = SalesSchemas["MessageTextView"];

/** One value's words in the mail's text, and which value it is. */
export type MailTarget = {
  field: string;
  lineNo: number | null;
  start: number;
  end: number;
};

/**
 * The newest part of the mail a model read a case's values from (a request
 * for quotation, ticket 29; a PO written in the mail, AI item 4), with the
 * words of one value highlighted. It is fetched from its own route when
 * opened, and the server records that this person was served it at this case
 * version: what confirming, preparing or cross-checking a value read from it
 * requires. Its text may state a price, so a caller without
 * `sales.price.read` is told so instead, without asking.
 */
export function MailTextDrawer({
  resourceKey,
  load,
  target,
  mayRead,
  onClose,
  onServed,
}: {
  resourceKey: string;
  load: () => Promise<MessageText>;
  target: MailTarget | null;
  mayRead: boolean;
  onClose: () => void;
  onServed?: (caseVersion: number) => void;
}) {
  const open = target !== null;
  const served = useResource(resourceKey, load, { enabled: open && mayRead });
  const version = served.data?.case_version;
  useEffect(() => {
    if (version !== undefined) onServed?.(version);
  }, [version, onServed]);
  const body = () => {
    if (!mayRead)
      return (
        <Typography.Text>
          Bạn cần quyền xem giá (sales.price.read) để mở nội dung thư: thư có
          thể nêu giá.
        </Typography.Text>
      );
    if (served.loading) return <RegionState kind="loading" />;
    if (served.error)
      return <LoadError error={served.error} onRetry={served.reload} />;
    const text = served.data?.text;
    if (text === undefined || !target) return null;
    return (
      <Space direction="vertical" className="w-full">
        <Typography.Text type="secondary">
          Đoạn mới nhất của thư, như DW1 đã đọc (phần trích dẫn thư cũ đã được
          cắt theo cấu trúc thư).
        </Typography.Text>
        <Typography.Paragraph className="whitespace-pre-wrap">
          {text.slice(0, target.start)}
          <mark>{text.slice(target.start, target.end)}</mark>
          {text.slice(target.end)}
        </Typography.Paragraph>
      </Space>
    );
  };
  return (
    <Drawer
      open={open}
      onClose={onClose}
      size="large"
      title={
        target
          ? `Thư của khách · ${label(FIELD, target.field)}${target.lineNo ? ` · dòng ${target.lineNo}` : ""}`
          : "Thư của khách"
      }
    >
      {body()}
    </Drawer>
  );
}
