"use client";

import { Check, ShieldCheck } from "lucide-react";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@dw/ui";
import { PageHeading } from "../../components/page-heading";
import { MembersManager } from "../../components/admin/members-manager";
import { useAuth } from "../../lib/auth/auth-context";

/**
 * Access reference page. Identity is managed by Keycloak; business permissions
 * (roles → scopes) live in the platform database. New accounts join the demo
 * workspace as `member`; an admin adjusts roles from here in a later milestone.
 */

const ROLE_CATALOG: {
  key: string;
  label: string;
  summary: string;
  scopes: string[];
}[] = [
  {
    key: "member",
    label: "Staff",
    summary:
      "Creates and tracks business records. Cannot make approval decisions.",
    scopes: ["approvals.read", "knowledge.read", "memory.read"],
  },
  {
    key: "approver",
    label: "Manager",
    summary:
      "Everything staff can do, plus approval decisions. No admin rights.",
    scopes: [
      "approvals.read",
      "approvals.decide",
      "knowledge.read",
      "knowledge.write",
      "memory.read",
    ],
  },
  {
    key: "platform_admin",
    label: "Tenant admin",
    summary: "Manages members, roles and every function in the workspace.",
    scopes: ["platform.admin", "(bypasses every scope)"],
  },
];

const SCOPE_LABELS: Record<string, string> = {
  "approvals.read": "View approval requests",
  "approvals.decide": "Decide approvals",
  "knowledge.read": "View the document library",
  "memory.read": "View processing history",
  "platform.admin": "Administer the whole platform",
  "(bypasses every scope)": "Full access",
};

function scopeLabel(scope: string) {
  return SCOPE_LABELS[scope] ?? scope;
}

function roleLabel(role: string) {
  return ROLE_CATALOG.find((item) => item.key === role)?.label ?? role;
}

export default function AdminPage() {
  const { displayName, active, roles, scopes, hasScope } = useAuth();
  const canManageMembers = hasScope("platform.members.write");

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeading
        icon={ShieldCheck}
        title="Roles & permissions"
        description="Access is granted by each member's role in the workspace."
      />

      {canManageMembers && <MembersManager />}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="size-4 text-success" /> Your access
          </CardTitle>
          <CardDescription>
            {displayName}
            {active ? ` · ${active.workspaceName}` : ""}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">Roles:</span>
            {roles.length > 0 ? (
              roles.map((r) => (
                <Badge key={r} variant="secondary">
                  {roleLabel(r)}
                </Badge>
              ))
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">Granted scopes:</span>
            {scopes.length > 0 ? (
              scopes.map((s) => (
                <span key={s} className="rounded bg-muted px-2 py-1 text-xs">
                  {scopeLabel(s)}
                </span>
              ))
            ) : (
              <span className="text-muted-foreground">Full admin access</span>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-3">
        {ROLE_CATALOG.map((role) => {
          const mine = roles.includes(role.key);
          return (
            <Card key={role.key} className={mine ? "border-primary" : ""}>
              <CardHeader>
                <CardTitle className="flex items-start justify-between gap-3 text-sm">
                  {role.label}
                  {mine && <Check className="size-4 text-primary" />}
                </CardTitle>
                <CardDescription>{role.summary}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-1">
                {role.scopes.map((s) => (
                  <span
                    key={s}
                    className="rounded bg-muted px-2 py-1 text-[11px]"
                  >
                    {scopeLabel(s)}
                  </span>
                ))}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground">
        Newly registered accounts automatically join the demo workspace as{" "}
        <strong>Staff</strong>. An administrator changes roles as needed.
      </p>
    </div>
  );
}
