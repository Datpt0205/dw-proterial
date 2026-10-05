"use client";

import { useCallback, useMemo } from "react";
import type { WorkspaceMember } from "@dw/api-client";
import { useAuth } from "../../../lib/auth/auth-context";
import { apiClient } from "../../../lib/session";
import type { Viewer } from "./order-actions";
import { useResource } from "./use-resource";

/**
 * The scopes each Sales permission set adds to a `sales_pic` membership, as
 * the sales migration declares them (`_PERMISSION_SETS` in
 * `db/migrations/versions/68305ebe4a83_*.py`).
 *
 * INTERIM, display only. `/auth/bootstrap` lists a membership's ROLE scopes
 * and leaves its permission sets' scopes out, so the session cannot tell that
 * An may acknowledge NOC/ESF or that Khoa may approve a quote, while the API,
 * which resolves both, lets them. Until bootstrap answers with the effective
 * scopes, the screen adds a set's scopes from this table for the sets the
 * roster says the viewer holds. `__tests__/viewer.test.ts` reads the
 * migration and fails the day the two differ. The server decides either way.
 */
export const PERMISSION_SET_SCOPES: Record<string, readonly string[]> = {
  sales_price_evidence: ["sales.price.other_customers.read"],
  sales_quote_approver: ["sales.quote.approve"],
  sales_export_control: ["sales.compliance.ack"],
};

/** The signed-in person as the Sales screens test them. */
export function useSalesViewer(): Viewer {
  const { principalId, hasScope } = useAuth();
  const roster = useResource<WorkspaceMember[]>(
    "directory/members",
    useCallback(() => apiClient().listWorkspaceMembers(), []),
    { enabled: hasScope("directory.read") },
  );
  const extra = useMemo(() => {
    const me = roster.data?.find((m) => m.user_id === principalId);
    return new Set(
      (me?.permission_set_keys ?? []).flatMap(
        (key) => PERMISSION_SET_SCOPES[key] ?? [],
      ),
    );
  }, [roster.data, principalId]);
  return useMemo(
    () => ({
      principalId,
      hasScope: (scope: string) => hasScope(scope) || extra.has(scope),
    }),
    [principalId, hasScope, extra],
  );
}
