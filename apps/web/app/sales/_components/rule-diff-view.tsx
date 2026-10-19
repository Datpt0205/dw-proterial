"use client";

import { Table, Typography } from "antd";
import { StatusTag } from "@dw/ui";
import type { RuleKey } from "../_lib/rules";
import { diffDocuments, type Change } from "../_lib/rule-diff";
import { describeValue, pathLabel } from "../_lib/rule-labels";
import type { RuleNode } from "../_lib/rule-schema";

const KIND: Record<
  Change["kind"],
  { label: string; tone: "warn" | "ok" | "err" }
> = {
  changed: { label: "Đổi", tone: "warn" },
  added: { label: "Thêm", tone: "ok" },
  removed: { label: "Bỏ", tone: "err" },
};

interface Row {
  key: string;
  field: string;
  change: Change;
  before: string;
  after: string;
}

function Value({ text }: { text: string }) {
  return (
    <Typography.Paragraph className="m-0! whitespace-pre-wrap break-words">
      {text}
    </Typography.Paragraph>
  );
}

/**
 * What a version changes against another, one row per field (ticket 40):
 * the proposer reads it before sending, and the head reads the same rows on
 * the approval. The kind of change is a word on a tag, never colour alone.
 */
export function RuleDiffView({
  ruleKey,
  root,
  before,
  after,
  beforeRef,
  afterRef,
}: {
  ruleKey: RuleKey;
  root: RuleNode;
  before: unknown;
  after: unknown;
  /** `id@version` of each side, for the column headers. */
  beforeRef: string;
  afterRef: string;
}) {
  const changes = diffDocuments(before, after);
  const rows: Row[] = changes.map((change, i) => ({
    key: `${i}:${change.path.join(".")}`,
    field: pathLabel(ruleKey, root, change.path),
    change,
    before:
      change.kind === "added"
        ? ""
        : describeValue(ruleKey, root, change.path, change.before),
    after:
      change.kind === "removed"
        ? ""
        : describeValue(ruleKey, root, change.path, change.after),
  }));
  return (
    <div className="space-y-2">
      <Typography.Text role="status">
        {rows.length === 0
          ? `Không có thay đổi nào so với ${beforeRef}.`
          : `${rows.length} thay đổi so với ${beforeRef}.`}
      </Typography.Text>
      {rows.length ? (
        <Table<Row>
          size="small"
          rowKey="key"
          dataSource={rows}
          pagination={false}
          scroll={{ x: "max-content" }}
          footer={() => `${rows.length} thay đổi`}
          columns={[
            {
              title: "Trường",
              key: "field",
              render: (_, row) => (
                <span className="flex flex-col gap-1">
                  <Typography.Text strong>{row.field}</Typography.Text>
                  <span>
                    <StatusTag tone={KIND[row.change.kind].tone}>
                      {KIND[row.change.kind].label}
                    </StatusTag>
                  </span>
                </span>
              ),
            },
            {
              title: `Đang áp dụng (${beforeRef})`,
              key: "before",
              render: (_, row) => <Value text={row.before} />,
            },
            {
              title: `Đề xuất (${afterRef})`,
              key: "after",
              render: (_, row) => <Value text={row.after} />,
            },
          ]}
        />
      ) : null}
    </div>
  );
}
