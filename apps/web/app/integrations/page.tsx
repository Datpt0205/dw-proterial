"use client";

import { useEffect, useState } from "react";
import { PlugZap } from "lucide-react";
import type { Integration } from "@dw/contracts";
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
} from "@dw/ui";
import { EmptyState } from "../../components/empty-state";
import { PageHeading } from "../../components/page-heading";
import { apiClient } from "../../lib/session";

export default function IntegrationsPage() {
  const [integrations, setIntegrations] = useState<Integration[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient()
      .listIntegrations()
      .then(setIntegrations)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "unknown error"),
      );
  }, []);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeading
        icon={PlugZap}
        title="Integrations & connectors"
        description="The capability catalogue the tool executor runs under the current release's policies, scopes and limits."
      />
      {error && <p className="text-sm text-red-600">{error}</p>}
      {integrations === null && !error && (
        <Skeleton className="h-56 rounded-2xl" />
      )}
      {integrations?.length === 0 && (
        <EmptyState
          icon={PlugZap}
          title="No connectors yet"
          description="The list appears once a connector is registered."
        />
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {integrations?.map((integration) => (
          <Card key={`${integration.tool}@${integration.version}`}>
            <CardHeader>
              <CardTitle>
                {integration.tool}{" "}
                <span className="font-mono text-xs text-slate-500">
                  v{integration.version}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>{integration.description}</p>
              <div className="flex flex-wrap gap-1.5 text-xs">
                <Badge variant="destructive">
                  side-effect: {integration.side_effect_level}
                </Badge>
                <Badge variant="warning">
                  approval: {integration.approval_policy}
                </Badge>
                {integration.idempotent && (
                  <Badge variant="success">idempotent</Badge>
                )}
                <Badge variant="secondary">
                  timeout {integration.timeout_seconds}s
                </Badge>
              </div>
              <p className="text-xs text-slate-500">
                scopes: {integration.required_scopes.join(", ") || "—"}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
