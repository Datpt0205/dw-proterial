"use client";

import { useCallback } from "react";
import type { WorkspaceMember } from "@dw/api-client";
import { apiClient } from "../../../lib/session";
import { useAuth } from "../../../lib/auth/auth-context";
import { useCachedResource } from "../../../lib/use-cached-resource";

export interface Actor {
  name: string;
  /** DW2's service account (or another lane's): a machine acted, not a person. */
  machine: boolean;
}

/**
 * Who a case's stamp names (a principal uuid). The workspace roster owns
 * names and says which member is a service account; an id it does not hold
 * (a member who left, or a viewer without `directory.read`) shows as a short
 * id, never blank.
 */
export function usePeople(): (id: string | null | undefined) => Actor {
  const { hasScope, principalId, displayName } = useAuth();
  const canRead = hasScope("directory.read");
  const roster = useCachedResource<WorkspaceMember[]>(
    `directory/members:${canRead}`,
    useCallback(
      () =>
        canRead ? apiClient().listWorkspaceMembers() : Promise.resolve([]),
      [canRead],
    ),
  );
  return useCallback(
    (id) => {
      if (!id) return { name: "", machine: false };
      if (id === principalId)
        return { name: `${displayName} (bạn)`, machine: false };
      const member = roster.data?.find((m) => m.user_id === id);
      if (member)
        return { name: member.display_name, machine: member.service === true };
      return { name: `Người dùng ${id.slice(0, 8)}`, machine: false };
    },
    [roster.data, principalId, displayName],
  );
}
