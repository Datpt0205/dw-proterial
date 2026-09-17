"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, ScrollText } from "lucide-react";
import type { AuditEvent } from "@dw/contracts";
import {
  Badge,
  Button,
  Card,
  CardContent,
  Input,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@dw/ui";
import { PageHeading } from "../../components/page-heading";
import { formatDateTime } from "../../lib/dates";
import { memberName, useWorkspaceMembers } from "../../lib/directory";
import { apiClient } from "../../lib/session";

const ACTION_VARIANTS: Record<
  string,
  "secondary" | "warning" | "success" | "default"
> = {
  "run.started": "default",
  "run.waiting_approval": "warning",
  "run.resumed": "default",
  "run.completed": "success",
  "approval.decided": "success",
  "tool.executed": "secondary",
};

const ACTION_LABELS: Record<string, string> = {
  "run.started": "Run started",
  "run.waiting_approval": "Awaiting approval",
  "run.resumed": "Run resumed",
  "run.completed": "Run completed",
  "approval.decided": "Approval decided",
  "tool.executed": "Tool executed",
  // PLUG-IN POINT: a bounded context adds its own actions here. An unmapped
  // action still shows, as "System activity" — a row is never dropped.
};

export default function AuditPage() {
  const members = useWorkspaceMembers();
  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setEvents((await apiClient().listAuditEvents({ limit: 200 })).items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown error");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const visible = events?.filter(
    (event) =>
      !filter ||
      event.action.includes(filter) ||
      event.resource_type.includes(filter) ||
      event.resource_id.includes(filter) ||
      (memberName(members, event.actor_id) ?? "")
        .toLowerCase()
        .includes(filter.toLowerCase()),
  );

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeading
        icon={ScrollText}
        title="Audit log"
        description="History is recorded continuously and cannot be edited, even by an administrator."
        actions={
          <>
            <Input
              className="w-56"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Search actions or records…"
            />
            <Button
              variant="outline"
              size="icon"
              onClick={() => void refresh()}
            >
              <RefreshCw />
            </Button>
          </>
        }
      />
      {error && <p className="text-sm text-destructive">{error}</p>}
      {events === null && !error && <Skeleton className="h-64 w-full" />}
      {visible?.length === 0 && (
        <p className="text-sm text-muted-foreground">No matching events.</p>
      )}

      {visible && visible.length > 0 && (
        <Card className="overflow-hidden">
          <CardContent className="pt-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>When</TableHead>
                  <TableHead>Who</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Resource</TableHead>
                  <TableHead>Policy decision</TableHead>
                  <TableHead>Trace id</TableHead>
                  <TableHead>Details</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((event, index) => (
                  <TableRow key={index} className="align-top">
                    <TableCell className="whitespace-nowrap font-mono text-xs">
                      {formatDateTime(event.occurred_at)}
                    </TableCell>
                    <TableCell className="text-xs">
                      {/* A name, falling back to a short id when the roster has
                          no such member - somebody who has since left still has
                          to be attributable. */}
                      {memberName(members, event.actor_id) ?? "—"}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={ACTION_VARIANTS[event.action] ?? "secondary"}
                      >
                        {ACTION_LABELS[event.action] ?? "System activity"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-xs text-muted-foreground">
                        {event.resource_type}
                      </span>
                      <p className="font-mono text-xs">{event.resource_id}</p>
                    </TableCell>
                    <TableCell className="text-xs">
                      {event.policy_decision ?? "—"}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {event.trace_id ?? "—"}
                    </TableCell>
                    <TableCell className="max-w-64 truncate text-xs text-muted-foreground">
                      {Object.keys(event.details).length > 0
                        ? JSON.stringify(event.details)
                        : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
