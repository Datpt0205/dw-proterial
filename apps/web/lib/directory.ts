"use client";

import { useEffect, useState } from "react";
import type { WorkspaceMember } from "@dw/contracts";
import { apiClient } from "./session";

/**
 * The workspace roster, fetched once per page load and shared.
 *
 * Actors and owners are stored as bare user ids, and several screens render at
 * least one of them, so a per-component fetch would mean the same request
 * several times on a single page. The cache is a module-level promise rather
 * than a store: the roster changes when somebody joins the workspace, not while
 * a page is open, and a full reload is the honest way to pick that up.
 */

let rosterPromise: Promise<WorkspaceMember[]> | null = null;

function loadRoster(): Promise<WorkspaceMember[]> {
  rosterPromise ??= apiClient()
    .listWorkspaceMembers()
    .catch(() => {
      // A missing roster degrades the UI to raw ids; it must never take a page
      // down, so the failure is swallowed here and retried on the next mount.
      rosterPromise = null;
      return [] as WorkspaceMember[];
    });
  return rosterPromise;
}

export function useWorkspaceMembers(): WorkspaceMember[] {
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  useEffect(() => {
    let cancelled = false;
    void loadRoster().then((roster) => {
      if (!cancelled) setMembers(roster);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return members;
}

/** The person's name, or a short id when the roster has no such member. */
export function memberName(
  members: WorkspaceMember[],
  userId: string | null | undefined,
): string | null {
  if (!userId) return null;
  const match = members.find((member) => member.user_id === userId);
  return match ? match.display_name : `${userId.slice(0, 8)}…`;
}
