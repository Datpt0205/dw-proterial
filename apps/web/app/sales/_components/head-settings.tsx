"use client";

import { useCallback, useMemo } from "react";
import { Button, Card, Skeleton, Table, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import { salesApi } from "../_lib/api";
import { describeValue, fieldWords } from "../_lib/rule-labels";
import {
  labelPath,
  parseLoc,
  readSchema,
  type JsonSchema,
  type RuleNode,
} from "../_lib/rule-schema";
import {
  startOptions,
  valueAt,
  type PlatformDocument,
  type RuleKey,
} from "../_lib/rules";
import { useResource, type Resource } from "../_lib/use-resource";
import { useIsPhone } from "./list-parts";

type Head = SalesSchemas["HeadSettingView"];
type RulesView = SalesSchemas["RulesInForceView"];

interface KeyDocs {
  root: RuleNode;
  /** What applies to the company now, and what the platform ships. */
  current: unknown;
  shipped: unknown;
}

/**
 * "Thiết lập chính" (ticket 35): the Sales head's short list for DW1, on one
 * screen, each setting as its one sentence with what applies now and the
 * platform's value beside it. The list, its order and its sentences are the
 * server's (`process_settings.HEAD_SETTINGS`); a key the caller may not read
 * is not served, so it is never asked for here. "Sửa thiết lập chính" opens
 * the same drawer every status opens, limited to these fields: a change is a
 * proposal of the key, approved as any other.
 */
export function HeadSettings({
  settings,
  rules,
  onEdit,
}: {
  settings: Head[];
  rules: Resource<RulesView>;
  onEdit: () => void;
}) {
  const keys = useMemo(
    () => [...new Set(settings.map((s) => s.key))].sort(),
    [settings],
  );
  const docs = useResource(
    `sales/rules/head/${keys.join(",")}`,
    useCallback(
      () =>
        Promise.all(
          keys.map(async (key) => {
            const [schema, platform] = await Promise.all([
              salesApi().ruleSchema(key),
              salesApi().rulePlatformDocuments(key),
            ]);
            return { key, schema, platform };
          }),
        ),
      [keys],
    ),
  );
  const byKey = useMemo(() => {
    const found = new Map<RuleKey, KeyDocs>();
    if (!docs.data || !rules.data) return found;
    const view = rules.data;
    for (const { key, schema, platform } of docs.data) {
      const root = readSchema(schema.json_schema as unknown as JsonSchema);
      const shippedRef = view.platform.find((p) => p.key === key)?.ref;
      found.set(key, {
        root,
        current: startOptions(view, key, platform).find((o) => o.inForce)
          ?.document,
        shipped: platform.find((p: PlatformDocument) => p.ref === shippedRef)
          ?.document,
      });
    }
    return found;
  }, [docs.data, rules.data]);

  const phone = useIsPhone();
  const loading = docs.loading || rules.loading;
  const shown = (head: Head, which: "current" | "shipped") => {
    const found = byKey.get(head.key);
    if (!found) return loading ? <Skeleton.Input size="small" active /> : "";
    const document = found[which];
    if (document === undefined) return "Chưa đọc được";
    const path = parseLoc(head.path);
    const value = valueAt(document, head.path);
    const unit = fieldWords(head.key, labelPath(found.root, path)).unit;
    const words = describeValue(head.key, found.root, path, value);
    const scalar =
      value !== null && ["number", "string"].includes(typeof value);
    return scalar && unit ? `${words} ${unit}` : words;
  };

  return (
    <Card
      size="small"
      title="Thiết lập chính"
      extra={
        <Button data-node="head" onClick={onEdit} disabled={!settings.length}>
          Sửa thiết lập chính
        </Button>
      }
    >
      {docs.error || rules.error ? (
        <LoadError
          error={docs.error ?? rules.error}
          onRetry={docs.error ? docs.reload : rules.reload}
          compact
        />
      ) : null}
      <Table<Head>
        size="small"
        rowKey={(h) => `${h.key}:${h.path}`}
        dataSource={settings}
        pagination={false}
        locale={{
          emptyText: "Bạn không xem được thiết lập chính nào của DW1.",
        }}
        columns={[
          {
            title: "Thiết lập",
            key: "sentence",
            render: (_, h) => (
              <span className="flex flex-col">
                <Typography.Text data-head={`${h.key}:${h.path}`}>
                  {h.sentence}
                </Typography.Text>
                {/* A phone has no room for the two value columns. */}
                {phone ? (
                  <span>
                    Đang dùng: {shown(h, "current")} · Mặc định:{" "}
                    {shown(h, "shipped")}
                  </span>
                ) : null}
              </span>
            ),
          },
          ...(phone
            ? []
            : [
                {
                  title: "Đang dùng",
                  key: "current",
                  render: (_: unknown, h: Head) => shown(h, "current"),
                },
                {
                  title: "Mặc định",
                  key: "shipped",
                  render: (_: unknown, h: Head) => shown(h, "shipped"),
                },
              ]),
        ]}
      />
    </Card>
  );
}
