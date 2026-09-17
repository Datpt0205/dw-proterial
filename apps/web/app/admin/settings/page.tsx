"use client";

import { useEffect, useState } from "react";
import { Check, Loader2, Settings } from "lucide-react";
import type { AdminTenant } from "@dw/contracts";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
} from "@dw/ui";
import { ApiError } from "@dw/api-client";
import { apiClient } from "../../../lib/session";
import { useAuth } from "../../../lib/auth/auth-context";
import { PageHeading } from "../../../components/page-heading";
import { EmptyState } from "../../../components/empty-state";

function errorText(error: unknown): string {
  return error instanceof ApiError
    ? error.body.message
    : "Something went wrong";
}

export default function SettingsPage() {
  const { hasScope } = useAuth();

  if (!hasScope("platform.tenant.settings.write")) {
    return (
      <EmptyState
        icon={Settings}
        title="No access"
        description="You need the tenant-settings permission to view this page."
      />
    );
  }
  return <TenantSettingsForm />;
}

type RecordVisibility = "open" | "restricted";

function TenantSettingsForm() {
  const [tenant, setTenant] = useState<AdminTenant | null>(null);
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [locale, setLocale] = useState("");
  const [recordVisibility, setRecordVisibility] =
    useState<RecordVisibility>("open");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apply = (t: AdminTenant) => {
    setTenant(t);
    setName(t.name);
    setTimezone(t.timezone ?? "");
    setLocale(t.locale ?? "");
    setRecordVisibility(
      t.record_visibility === "restricted" ? "restricted" : "open",
    );
  };

  useEffect(() => {
    apiClient()
      .getTenantSettings()
      .then(apply)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  const save = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await apiClient().updateTenantSettings({
        name: name.trim(),
        timezone: timezone.trim(),
        locale: locale.trim(),
        record_visibility: recordVisibility,
      });
      apply(updated);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <PageHeading
        icon={Settings}
        title="Tenant settings"
        description="Tenant name, timezone and language."
      />

      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      {tenant === null ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Loading…
        </div>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between gap-3 text-base">
              {tenant.slug}
              <Badge variant="secondary">{tenant.status}</Badge>
            </CardTitle>
            <CardDescription>
              Slug and status are fixed; only the name, timezone and language
              can be changed.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-muted-foreground">
                Name
              </span>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-muted-foreground">
                Timezone
              </span>
              <Input
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                placeholder="Asia/Ho_Chi_Minh"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-muted-foreground">
                Language
              </span>
              <Input
                value={locale}
                onChange={(e) => setLocale(e.target.value)}
                placeholder="en-US"
              />
            </label>
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-muted-foreground">
                Record visibility
              </span>
              <select
                value={recordVisibility}
                onChange={(e) =>
                  setRecordVisibility(e.target.value as RecordVisibility)
                }
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value="open">
                  Open — everyone in the workspace sees all
                </option>
                <option value="restricted">
                  Restricted — a manager sees only their team
                </option>
              </select>
              <span className="mt-1 block text-xs text-muted-foreground">
                {recordVisibility === "restricted"
                  ? "The dashboard is scoped to the reporting line: each manager sees only their own and their reports' numbers (leadership still sees everything)."
                  : "Every member of the workspace sees all data, with no scoping by reporting line."}
              </span>
            </label>
            <Button onClick={() => void save()} disabled={busy || !name.trim()}>
              {busy ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Check className="size-4" />
              )}
              Save
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
