"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, Scale } from "lucide-react";
import type { AdminSodRule } from "@dw/contracts";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Textarea,
} from "@dw/ui";
import { ApiError } from "@dw/api-client";
import { apiClient } from "../../../lib/session";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime } from "../../../lib/dates";
import { PageHeading } from "../../../components/page-heading";
import { EmptyState } from "../../../components/empty-state";

function errorText(error: unknown): string {
  return error instanceof ApiError
    ? error.body.message
    : "Something went wrong";
}

export default function SeparationOfDutiesPage() {
  const { hasScope } = useAuth();

  if (!hasScope("platform.roles.read")) {
    return (
      <EmptyState
        icon={Scale}
        title="No access"
        description="You need the role-catalog permission to view this page."
      />
    );
  }
  return <RuleList canDecide={hasScope("platform.sod_waivers.write")} />;
}

function RuleList({ canDecide }: { canDecide: boolean }) {
  const [rules, setRules] = useState<AdminSodRule[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiClient()
      .listSeparationOfDuties()
      .then(setRules)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  useEffect(load, [load]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeading
        icon={Scale}
        title="Separation of duties"
        description="Pairs of duties no single person may hold. A company too small to staff both sides may waive a rule that allows it, with a reason. Every waiver and revocation is recorded in the audit log."
      />

      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {rules === null ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading…
        </div>
      ) : rules.length === 0 ? (
        <EmptyState
          icon={Scale}
          title="No rules"
          description="No separation-of-duty rule is installed."
        />
      ) : (
        rules.map((rule) => (
          <RuleCard
            key={rule.key}
            rule={rule}
            canDecide={canDecide}
            onDecided={() => {
              setError(null);
              load();
            }}
          />
        ))
      )}
    </div>
  );
}

function RuleCard({
  rule,
  canDecide,
  onDecided,
}: {
  rule: AdminSodRule;
  canDecide: boolean;
  onDecided: () => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const waived = rule.waiver !== null;

  const decide = async () => {
    if (!reason.trim()) return;
    setBusy(true);
    setError(null);
    try {
      if (waived) {
        await apiClient().revokeSeparationOfDutiesWaiver(rule.key, reason);
      } else {
        await apiClient().waiveSeparationOfDutiesRule(rule.key, reason);
      }
      setReason("");
      onDecided();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-3 text-base">
          {rule.description}
          {waived ? (
            <Badge variant="warning">Waived</Badge>
          ) : rule.waivable ? (
            <Badge variant="secondary">Enforced</Badge>
          ) : (
            <Badge variant="outline">Always enforced</Badge>
          )}
        </CardTitle>
        <CardDescription className="font-mono text-xs">
          {rule.key}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="grid gap-2 sm:grid-cols-2">
          <ScopeList title="One side" scopes={rule.left_scopes} />
          <ScopeList title="Other side" scopes={rule.right_scopes} />
        </div>

        {rule.waiver && (
          <p className="rounded-md bg-muted px-3 py-2">
            Waived on {formatDateTime(rule.waiver.granted_at)}:{" "}
            {rule.waiver.reason}
          </p>
        )}

        {!rule.waivable && (
          <p className="text-xs text-muted-foreground">
            The platform does not let any tenant waive this rule.
          </p>
        )}

        {canDecide && (rule.waivable || waived) && (
          <div className="space-y-2">
            <Textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder={
                waived
                  ? "Why the waiver is no longer needed"
                  : "Why this company cannot keep these duties apart"
              }
              rows={2}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button
              variant={waived ? "outline" : "destructive"}
              onClick={() => void decide()}
              disabled={busy || !reason.trim()}
            >
              {busy && <Loader2 className="size-4 animate-spin" />}
              {waived ? "Revoke waiver" : "Waive for this tenant"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ScopeList({ title, scopes }: { title: string; scopes: string[] }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      <div className="flex flex-wrap gap-1">
        {scopes.map((scope) => (
          <Badge key={scope} variant="outline" className="font-mono text-xs">
            {scope}
          </Badge>
        ))}
      </div>
    </div>
  );
}
