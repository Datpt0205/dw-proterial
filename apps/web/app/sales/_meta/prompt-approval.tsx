"use client";

import { useCallback } from "react";
import { Skeleton, Typography } from "antd";
import type { Approval } from "@dw/contracts";
import { LoadError } from "../../../components/load-error";
import { useAuth } from "../../../lib/auth/auth-context";
import { salesApi } from "../_lib/api";
import { RULE_STATUS } from "../_lib/rules";
import { useResource } from "../_lib/use-resource";
import { PromptChanges } from "../_components/prompt-changes";
import { SCOPE } from "../_components/sales-frame";

/**
 * A `sales.prompts` approval's version beside the one in force (ticket 43),
 * where the head decides it (`/approvals`): the payload names the version
 * only, so the version is read through `/sales/prompts`, which answers only
 * holders of `sales.rules.approve`; anyone else is told why it is not shown.
 */
export function PromptApprovalChanges({ approval }: { approval: Approval }) {
  const { hasScope } = useAuth();
  const allowed = hasScope(SCOPE.rulesApprove);
  const versionId = String(approval.payload.version_id ?? "");
  const loaded = useResource(
    `sales/prompts/approval/${approval.id}`,
    useCallback(() => salesApi().prompts(), []),
    { enabled: allowed },
  );

  if (!allowed)
    return (
      <Typography.Text>
        Chỉ người có quyền duyệt quy tắc ({SCOPE.rulesApprove}) xem được các
        dòng mẫu của phiên bản này.
      </Typography.Text>
    );
  if (loaded.error)
    return <LoadError error={loaded.error} onRetry={loaded.reload} />;
  if (!loaded.data) return <Skeleton active paragraph={{ rows: 4 }} />;
  const view = loaded.data;
  const version = view.versions.find((v) => v.version_id === versionId);
  if (!version)
    return (
      <Typography.Text>Không tìm thấy phiên bản được đề xuất.</Typography.Text>
    );
  if (version.status !== "proposed")
    return (
      <Typography.Text>
        Phiên bản {version.ref}: {RULE_STATUS[version.status].toLowerCase()}.
      </Typography.Text>
    );
  return <PromptChanges view={view} version={version} />;
}
