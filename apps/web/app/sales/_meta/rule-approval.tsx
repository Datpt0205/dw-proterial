"use client";

import { useCallback } from "react";
import { Flex, Skeleton, Typography } from "antd";
import type { Approval } from "@dw/contracts";
import { LoadError } from "../../../components/load-error";
import { useAuth } from "../../../lib/auth/auth-context";
import { salesApi } from "../_lib/api";
import { RULE_KEY, RULE_STATUS, startOptions, type RuleKey } from "../_lib/rules";
import { readSchema, type JsonSchema } from "../_lib/rule-schema";
import { useResource } from "../_lib/use-resource";
import { RuleDiffView } from "../_components/rule-diff-view";
import { SCOPE } from "../_components/sales-frame";

function isRuleKey(value: unknown): value is RuleKey {
  return typeof value === "string" && value in RULE_KEY;
}

/**
 * A `sales.rules` approval's changes, field by field against the version in
 * force (ticket 40), where the head decides it (`/approvals`). The payload
 * names the key and the version only, never the document (ticket 38), so the
 * document is read through the rules routes, which answer only holders of
 * `sales.rules.propose` (the head holds it); anyone else is told why it is
 * not shown, and the payload above stays what they see.
 */
export function RuleApprovalChanges({ approval }: { approval: Approval }) {
  const { hasScope } = useAuth();
  const allowed = hasScope(SCOPE.rulesPropose);
  const key = approval.payload.key;
  const versionId = String(approval.payload.version_id ?? "");
  const known = isRuleKey(key);
  const loaded = useResource(
    `sales/rules/approval/${approval.id}`,
    useCallback(async () => {
      if (!isRuleKey(key)) throw new Error("unknown rule key");
      const api = salesApi();
      const [view, schema, platform] = await Promise.all([
        api.rules(),
        api.ruleSchema(key),
        api.rulePlatformDocuments(key),
      ]);
      return { view, schema, platform };
    }, [key]),
    { enabled: allowed && known },
  );

  if (!known) return null;
  if (!allowed)
    return (
      <Typography.Text>
        Chỉ người có quyền đề xuất quy tắc ({SCOPE.rulesPropose}) xem được tài
        liệu và các thay đổi của phiên bản này.
      </Typography.Text>
    );
  if (loaded.error)
    return <LoadError error={loaded.error} onRetry={loaded.reload} />;
  if (!loaded.data) return <Skeleton active paragraph={{ rows: 4 }} />;

  const { view, schema, platform } = loaded.data;
  const version = view.versions.find((v) => v.version_id === versionId);
  if (!version)
    return <Typography.Text>Không tìm thấy phiên bản được đề xuất.</Typography.Text>;
  if (version.status !== "proposed")
    return (
      <Typography.Text>
        Phiên bản {version.ref}: {RULE_STATUS[version.status].toLowerCase()}.
      </Typography.Text>
    );
  const inForce = startOptions(view, key, platform).find((o) => o.inForce);
  if (!inForce)
    return <Typography.Text>Không đọc được phiên bản đang áp dụng.</Typography.Text>;
  return (
    <Flex vertical gap="small">
      <Typography.Text strong>
        {RULE_KEY[key]}: thay đổi so với bản đang áp dụng
      </Typography.Text>
      <RuleDiffView
        ruleKey={key}
        root={readSchema(schema.json_schema as unknown as JsonSchema)}
        before={inForce.document}
        after={version.document}
        beforeRef={inForce.ref}
        afterRef={version.ref}
      />
    </Flex>
  );
}
