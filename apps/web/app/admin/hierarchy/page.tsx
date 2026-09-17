"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Loader2, Network } from "lucide-react";
import type { HierarchyMember } from "@dw/contracts";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@dw/ui";
import { ApiError } from "@dw/api-client";
import { apiClient } from "../../../lib/session";
import { useAuth } from "../../../lib/auth/auth-context";
import { PageHeading } from "../../../components/page-heading";
import { EmptyState } from "../../../components/empty-state";
import { roleLabels } from "../../../lib/nav/roles";

function errorText(error: unknown): string {
  return error instanceof ApiError
    ? error.body.message
    : "Something went wrong";
}

export default function HierarchyPage() {
  const { hasScope } = useAuth();

  if (!hasScope("platform.members.write")) {
    return (
      <EmptyState
        icon={Network}
        title="No access"
        description="You need the member-management permission to view this page."
      />
    );
  }
  return <HierarchyManager />;
}

function HierarchyManager() {
  const [members, setMembers] = useState<HierarchyMember[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setMembers(await apiClient().listHierarchy());
    } catch (e) {
      setMembers([]);
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const setManager = useCallback(
    async (userId: string, managerUserId: string | null) => {
      setSavingId(userId);
      setError(null);
      try {
        await apiClient().setManager(userId, managerUserId);
        await refresh();
      } catch (e) {
        setError(errorText(e));
      } finally {
        setSavingId(null);
      }
    },
    [refresh],
  );

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeading
        icon={Network}
        title="Reporting line"
        description="Who reports to whom in the workspace. Change 'Reports to' to set someone's manager."
      />

      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Reporting chart</CardTitle>
          <CardDescription>
            People with no manager sit at the root; reports are indented beneath
            them.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {members === null ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Loading…
            </div>
          ) : members.length === 0 ? (
            <EmptyState
              icon={Network}
              title="No members yet"
              description="This workspace has no one to arrange into a reporting line."
            />
          ) : (
            <HierarchyTree
              members={members}
              savingId={savingId}
              onSetManager={setManager}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function HierarchyTree({
  members,
  savingId,
  onSetManager,
}: {
  members: HierarchyMember[];
  savingId: string | null;
  onSetManager: (userId: string, managerUserId: string | null) => void;
}) {
  const byId = new Map(members.map((m) => [m.user_id, m]));
  const childrenOf = (managerId: string | null): HierarchyMember[] =>
    members.filter((m) => {
      // A member whose manager is not in this roster is treated as a root, so
      // nobody is dropped from the tree by a dangling reference.
      const parent = m.manager_user_id;
      if (managerId === null) return parent === null || !byId.has(parent);
      return parent === managerId;
    });

  const renderNodes = (
    managerId: string | null,
    depth: number,
    seen: Set<string>,
  ): ReactNode =>
    childrenOf(managerId).map((m) => {
      // Guard against a cycle in the data (the API forbids one, but never trust
      // that a fetched shape is acyclic before recursing on it).
      if (seen.has(m.user_id)) return null;
      const next = new Set(seen).add(m.user_id);
      return (
        <div key={m.user_id}>
          <MemberRow
            member={m}
            others={members.filter((o) => o.user_id !== m.user_id)}
            depth={depth}
            saving={savingId === m.user_id}
            onSetManager={onSetManager}
          />
          {renderNodes(m.user_id, depth + 1, next)}
        </div>
      );
    });

  return (
    <div className="divide-y rounded-md border">
      {renderNodes(null, 0, new Set<string>())}
    </div>
  );
}

function MemberRow({
  member,
  others,
  depth,
  saving,
  onSetManager,
}: {
  member: HierarchyMember;
  others: HierarchyMember[];
  depth: number;
  saving: boolean;
  onSetManager: (userId: string, managerUserId: string | null) => void;
}) {
  return (
    <div
      className="flex items-center justify-between gap-3 px-3 py-2.5 text-sm"
      style={{ paddingLeft: `${depth * 1.5 + 0.75}rem` }}
    >
      <div className="min-w-0">
        <p className="truncate font-medium">{member.display_name}</p>
        <p className="truncate text-xs text-muted-foreground">
          {member.role_keys.length > 0 ? roleLabels(member.role_keys) : "—"}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <label className="text-xs text-muted-foreground">Reports to</label>
        <select
          value={member.manager_user_id ?? ""}
          disabled={saving}
          onChange={(e) =>
            onSetManager(
              member.user_id,
              e.target.value === "" ? null : e.target.value,
            )
          }
          className="rounded-md border bg-background px-2 py-1.5 text-sm"
        >
          <option value="">— (none)</option>
          {others.map((o) => (
            <option key={o.user_id} value={o.user_id}>
              {o.display_name}
            </option>
          ))}
        </select>
        {saving && (
          <Loader2 className="size-4 animate-spin text-muted-foreground" />
        )}
      </div>
    </div>
  );
}
