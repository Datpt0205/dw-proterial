"use client";

import { useCallback } from "react";
import type { WorkspaceMember } from "@dw/api-client";
import { apiClient } from "../../../lib/session";
import { useAuth } from "../../../lib/auth/auth-context";
import { label, SALES_ROLE } from "./labels";
import { useResource } from "./use-resource";

/** DW1's own events carry this actor kind instead of a person. */
const WORKER_ID = /^(dw1|worker|service:)/i;

/**
 * A person's name for an actor id the case stamped (a principal uuid). The
 * workspace roster is the owner of names; an id it does not hold (a member
 * who left, or a viewer without `directory.read`) shows as a short id, never
 * as blank, so "who did this" always has an answer.
 */
export function usePeople() {
  const { hasScope, principalId, displayName } = useAuth();
  const roster = useResource<WorkspaceMember[]>(
    "directory/members",
    useCallback(() => apiClient().listWorkspaceMembers(), []),
    { enabled: hasScope("directory.read") },
  );
  return useCallback(
    (id: string | null | undefined): string => {
      if (!id) return "";
      if (id === principalId) return `${displayName} (bạn)`;
      if (WORKER_ID.test(id)) return "DW1";
      const member = roster.data?.find(
        (m) => m.user_id === id || m.email?.toLowerCase() === id.toLowerCase(),
      );
      if (member) return member.display_name;
      if (id.startsWith("role:"))
        return `Cả nhóm ${label(SALES_ROLE, id.slice("role:".length))}`;
      return id.includes("@") ? id : `Người dùng ${id.slice(0, 8)}`;
    },
    [roster.data, principalId, displayName],
  );
}
