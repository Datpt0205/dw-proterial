"use client";

import { useCallback } from "react";
import { Skeleton, Typography } from "antd";
import type { Approval } from "@dw/contracts";
import { LoadError } from "../../../components/load-error";
import { useAuth } from "../../../lib/auth/auth-context";
import { salesApi } from "../_lib/api";
import { RULE_STATUS } from "../_lib/rules";
import { useResource } from "../_lib/use-resource";
import { SkillChanges } from "../_components/skill-changes";
import { SCOPE } from "../_components/sales-frame";

/**
 * A `sales.skills` approval's version beside the skill in force under its key
 * (ticket 40), where the head decides it (`/approvals`): the payload names the
 * version only, so it is read through `/sales/skills/versions/{id}`, which
 * holds a customer's SalesOrder skill's version too (ticket 41) and answers
 * only holders of `sales.rules.propose` (the head holds it); anyone else is
 * told why it is not shown.
 */
export function SkillApprovalChanges({ approval }: { approval: Approval }) {
  const { hasScope } = useAuth();
  const allowed = hasScope(SCOPE.rulesPropose);
  const versionId = String(approval.payload.version_id ?? "");
  const loaded = useResource(
    `sales/skills/approval/${approval.id}`,
    useCallback(() => salesApi().skillVersion(versionId), [versionId]),
    { enabled: allowed },
  );

  if (!allowed)
    return (
      <Typography.Text>
        Chỉ người có quyền đề xuất quy tắc ({SCOPE.rulesPropose}) xem được lời
        của phiên bản kỹ năng này.
      </Typography.Text>
    );
  if (loaded.error)
    return <LoadError error={loaded.error} onRetry={loaded.reload} />;
  if (!loaded.data) return <Skeleton active paragraph={{ rows: 4 }} />;
  const { skill, version } = loaded.data;
  if (version.status !== "proposed")
    return (
      <Typography.Text>
        Phiên bản {version.ref}: {RULE_STATUS[version.status].toLowerCase()}.
      </Typography.Text>
    );
  return <SkillChanges skill={skill} version={version} />;
}
