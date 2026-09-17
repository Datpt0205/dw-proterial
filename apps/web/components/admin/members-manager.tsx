"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronDown,
  Loader2,
  ShieldPlus,
  Trash2,
  UserPlus,
} from "lucide-react";
import type { PlatformUserRef, WorkspaceMember } from "@dw/api-client";
import type { AdminPermissionSet } from "@dw/contracts";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@dw/ui";
import { ApiError } from "@dw/api-client";
import { apiClient } from "../../lib/session";
import { useAuth } from "../../lib/auth/auth-context";
import { roleLabel } from "../../lib/nav/roles";
import { EmailPicker } from "../email-picker";

// Business roles anyone who manages members can hand out. PLUG-IN POINT: a
// bounded context's own tiers join this list once they are in the tenant role
// catalog — the API refuses a key the catalog does not carry.
const BASE_GRANTABLE_ROLES = ["member", "approver"];
// Administrative roles: the API refuses them from a non-platform-admin, so they
// are offered only to a platform admin / operator (see `grantableRoles`). Listing
// them also lets an existing admin member's row show its real role instead of
// falling back to the first business role.
const ADMIN_GRANTABLE_ROLES = ["org_admin", "platform_admin"];

function toRoleOptions(keys: string[]): { key: string; label: string }[] {
  return keys.map((key) => ({ key, label: roleLabel(key) }));
}

export function MembersManager() {
  const { active, roles } = useAuth();
  const workspaceId = active?.workspaceId ?? null;
  // Only the platform_admin ROLE may mint an admin role — the grant handler's
  // _forbid_escalation lets exactly that role through and refuses everyone else,
  // so the UI offers the admin options to the same set and no one it would 403.
  const canGrantAdmin = roles.includes("platform_admin");
  const grantableRoles = useMemo(
    () =>
      toRoleOptions([
        ...BASE_GRANTABLE_ROLES,
        ...(canGrantAdmin ? ADMIN_GRANTABLE_ROLES : []),
      ]),
    [canGrantAdmin],
  );

  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [candidates, setCandidates] = useState<PlatformUserRef[]>([]);
  // The picker is a convenience (the email box works without it), so a load
  // failure shows a small note here rather than being swallowed silently.
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [permissionSets, setPermissionSets] = useState<AdminPermissionSet[]>(
    [],
  );
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(BASE_GRANTABLE_ROLES[0]!);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Per-row role edits, keyed by user id; a row falls back to its stored role
  // until it is touched.
  const [roleEdits, setRoleEdits] = useState<Record<string, string>>({});
  const [savingId, setSavingId] = useState<string | null>(null);
  // Per-row permission-set edits, keyed by user id; a row falls back to its
  // stored keys until it is touched.
  const [setEdits, setSetEdits] = useState<Record<string, string[]>>({});
  const [savingSetsId, setSavingSetsId] = useState<string | null>(null);
  // Permission sets are the exception, not the rule, so the editor stays folded
  // per member and opens only when an admin asks for it. One open at a time.
  const [expandedSetsId, setExpandedSetsId] = useState<string | null>(null);

  // Re-read the pick list on its own so it can refresh when the picker opens:
  // somebody who signs in after this page loaded must appear without a reload.
  const loadCandidates = useCallback(async () => {
    try {
      setCandidates(await apiClient().listGrantCandidates());
      setCandidatesError(null);
    } catch (e) {
      setCandidates([]);
      setCandidatesError(
        e instanceof ApiError
          ? e.body.message
          : "Could not load the suggestions — type the email to grant directly.",
      );
    }
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setMembers(await apiClient().listWorkspaceMembers());
      // Clear pending per-row edits so freshly loaded members show stored state.
      setSetEdits({});
      await loadCandidates();
      // The permission-set catalog is optional decoration; a failure here must
      // not blank the roster.
      try {
        setPermissionSets(await apiClient().listPermissionSets());
      } catch {
        setPermissionSets([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the roster");
    } finally {
      setLoading(false);
    }
  }, [loadCandidates]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function grant() {
    if (!workspaceId || !email.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient().grantMember({
        email: email.trim(),
        workspaceId,
        roleKeys: [role],
      });
      setEmail("");
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.body.message : "Grant failed");
    } finally {
      setBusy(false);
    }
  }

  function currentRole(m: WorkspaceMember): string {
    const edited = roleEdits[m.user_id];
    if (edited !== undefined) return edited;
    const known = m.role_keys.find((k) =>
      grantableRoles.some((r) => r.key === k),
    );
    return known ?? grantableRoles[0]!.key;
  }

  // grant is an upsert, so re-granting with a single role replaces the member's
  // role. Department is passed back so a role change does not reset it.
  async function saveRole(m: WorkspaceMember) {
    if (!workspaceId || !m.email) return;
    setSavingId(m.user_id);
    setError(null);
    try {
      await apiClient().grantMember({
        email: m.email,
        workspaceId,
        roleKeys: [currentRole(m)],
        department: m.department,
      });
      await refresh();
    } catch (e) {
      setError(
        e instanceof ApiError ? e.body.message : "Could not update the role",
      );
    } finally {
      setSavingId(null);
    }
  }

  function checkedSets(m: WorkspaceMember): string[] {
    return setEdits[m.user_id] ?? m.permission_set_keys;
  }

  function toggleSet(m: WorkspaceMember, key: string, on: boolean) {
    const current = checkedSets(m);
    const next = on ? [...current, key] : current.filter((k) => k !== key);
    setSetEdits((prev) => ({ ...prev, [m.user_id]: next }));
  }

  async function savePermissionSets(m: WorkspaceMember) {
    setSavingSetsId(m.user_id);
    setError(null);
    try {
      await apiClient().setMemberPermissionSets(m.user_id, checkedSets(m));
      await refresh();
    } catch (e) {
      setError(
        e instanceof ApiError
          ? e.body.message
          : "Could not update permission sets",
      );
    } finally {
      setSavingSetsId(null);
    }
  }

  async function revoke(userId: string) {
    if (!workspaceId) return;
    setError(null);
    try {
      await apiClient().revokeMember(userId, workspaceId);
      await refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.body.message : "Revoke failed");
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <UserPlus className="size-4" /> Members
        </CardTitle>
        <CardDescription>
          Grant access to anyone who has signed in at least once. A new person
          must sign in themselves before they can be assigned a role.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-2">
          <div className="flex-1 min-w-[12rem]">
            <label className="mb-1 block text-xs text-muted-foreground">
              Email
            </label>
            <EmailPicker
              value={email}
              onChange={setEmail}
              onOpen={() => void loadCandidates()}
              options={candidates.map((c) => ({
                email: c.email ?? "",
                display_name: c.display_name,
              }))}
              placeholder="Pick or type an email…"
            />
            {candidatesError && (
              <p className="mt-1 text-xs text-muted-foreground">
                {candidatesError}
              </p>
            )}
          </div>
          <div>
            <label className="mb-1 block text-xs text-muted-foreground">
              Role
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="rounded-md border bg-background px-3 py-2 text-sm"
            >
              {grantableRoles.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
          <Button onClick={() => void grant()} disabled={busy || !email.trim()}>
            {busy ? <Loader2 className="animate-spin" /> : <UserPlus />}
            Grant
          </Button>
        </div>

        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        <div className="divide-y rounded-md border">
          {loading ? (
            <p className="px-3 py-4 text-sm text-muted-foreground">Loading…</p>
          ) : members.length === 0 ? (
            <p className="px-3 py-4 text-sm text-muted-foreground">
              No members yet.
            </p>
          ) : (
            members.map((m) => (
              <div key={m.user_id} className="px-3 py-2 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{m.display_name}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {m.email ?? "—"} · {m.department}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <select
                      value={currentRole(m)}
                      onChange={(e) =>
                        setRoleEdits((prev) => ({
                          ...prev,
                          [m.user_id]: e.target.value,
                        }))
                      }
                      className="rounded-md border bg-background px-2 py-1.5 text-sm"
                    >
                      {grantableRoles.map((r) => (
                        <option key={r.key} value={r.key}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void saveRole(m)}
                      disabled={!m.email || savingId === m.user_id}
                    >
                      {savingId === m.user_id ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Check className="size-4" />
                      )}
                      Save
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void revoke(m.user_id)}
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </div>

                {permissionSets.length > 0 && (
                  <div className="mt-1.5">
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedSetsId(
                          expandedSetsId === m.user_id ? null : m.user_id,
                        )
                      }
                      className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                    >
                      <ShieldPlus className="size-3.5" /> Permission sets
                      {checkedSets(m).length > 0 && (
                        <span className="rounded-full bg-primary/10 px-1.5 text-[10px] font-medium text-primary">
                          {checkedSets(m).length}
                        </span>
                      )}
                      <ChevronDown
                        className={`size-3 transition-transform ${
                          expandedSetsId === m.user_id ? "rotate-180" : ""
                        }`}
                      />
                    </button>
                    {expandedSetsId === m.user_id && (
                      <div className="mt-2 rounded-md bg-muted/40 px-3 py-2">
                        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
                          {permissionSets.map((ps) => (
                            <label
                              key={ps.key}
                              className="flex items-center gap-1.5 text-xs"
                              title={ps.scopes.join(", ")}
                            >
                              <input
                                type="checkbox"
                                className="size-3.5 accent-primary"
                                checked={checkedSets(m).includes(ps.key)}
                                onChange={(e) =>
                                  toggleSet(m, ps.key, e.target.checked)
                                }
                              />
                              {ps.name}
                            </label>
                          ))}
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          className="mt-2"
                          onClick={() => void savePermissionSets(m)}
                          disabled={savingSetsId === m.user_id}
                        >
                          {savingSetsId === m.user_id ? (
                            <Loader2 className="size-4 animate-spin" />
                          ) : (
                            <Check className="size-4" />
                          )}
                          Save permission sets
                        </Button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
