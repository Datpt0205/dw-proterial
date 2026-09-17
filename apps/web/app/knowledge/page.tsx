"use client";

import { useCallback, useEffect, useState } from "react";
import { Library, Loader2, RefreshCw, Trash2, Upload } from "lucide-react";
import type { IngestJob, KnowledgeDocument } from "@dw/contracts";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Select,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@dw/ui";
import { EmptyState } from "../../components/empty-state";
import { Modal } from "../../components/modal";
import { PageHeading } from "../../components/page-heading";
import { useAuth } from "../../lib/auth/auth-context";
import { formatDateTime } from "../../lib/dates";
import { apiClient } from "../../lib/session";

// The ingest job is polled rather than pushed: the worker picks it off a queue
// and a parse takes seconds, not milliseconds. Five minutes at this interval is
// long enough for a 50 MB file and short enough to give up honestly.
const POLL_MS = 2_000;
const POLL_ATTEMPTS = 150;

const JOB_BADGE: Record<
  string,
  "secondary" | "warning" | "success" | "destructive"
> = {
  queued: "secondary",
  running: "warning",
  done: "success",
  failed: "destructive",
};

export default function KnowledgePage() {
  const { hasScope, hasRole } = useAuth();
  const [documents, setDocuments] = useState<KnowledgeDocument[] | null>(null);
  // Jobs this browser started. The API exposes a job by id, not a list, so the
  // page follows the ones it queued rather than inventing a history it cannot
  // read back after a reload.
  const [jobs, setJobs] = useState<IngestJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [domain, setDomain] = useState("shared");
  const [scope, setScope] = useState<"tenant" | "global">("tenant");

  const canWrite = hasScope("knowledge.write");
  // Publishing across tenants is a platform-admin act; the API refuses it from
  // anyone else, so the option is offered to exactly the same set.
  const canPublishGlobal = hasRole("platform_admin");

  const refresh = useCallback(async () => {
    try {
      setDocuments((await apiClient().listKnowledgeDocuments()).items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown error");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function trackJob(job: IngestJob) {
    setJobs((current) => [
      job,
      ...current.filter((item) => item.job_id !== job.job_id),
    ]);
  }

  /** Follow one job to a terminal state, refreshing the list when it lands. */
  async function pollJob(jobId: string): Promise<void> {
    for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
      const job = await apiClient().getIngestJob(jobId);
      trackJob(job);
      if (job.status === "done" || job.status === "failed") {
        await refresh();
        return;
      }
    }
  }

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file || !title.trim()) return;
    setBusy(true);
    try {
      const job = await apiClient().uploadKnowledgeDocument(file, {
        title: title.trim(),
        domain,
        scope,
      });
      trackJob(job);
      setError(null);
      setFormOpen(false);
      setTitle("");
      // The dialog unmounts when it closes, so the file input resets itself.
      setFile(null);
      void pollJob(job.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown error");
    } finally {
      setBusy(false);
    }
  }

  async function remove(document: KnowledgeDocument) {
    setBusy(true);
    try {
      await apiClient().deleteKnowledgeDocument(document.document_id);
      setError(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "unknown error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeading
        icon={Library}
        title="Knowledge"
        description="The documents workers retrieve from. Every one carries a scope and a version, and retrieval is filtered by the tenant the reader belongs to."
        actions={
          <>
            {canWrite && (
              <Button onClick={() => setFormOpen(true)}>
                <Upload /> Add document
              </Button>
            )}
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
      {documents === null && !error && <Skeleton className="h-64 w-full" />}
      {documents?.length === 0 && (
        <EmptyState
          icon={Library}
          title="No documents yet"
          description="Upload the first document to give the workers something to retrieve from."
        />
      )}

      {documents && documents.length > 0 && (
        <Card className="overflow-hidden">
          <CardContent className="pt-5">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Domain</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Classification</TableHead>
                  <TableHead>Chunks</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Added</TableHead>
                  {canWrite && <TableHead />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {documents.map((document) => (
                  <TableRow key={document.document_id} className="align-top">
                    <TableCell className="text-sm font-medium">
                      {document.title}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {document.domain}
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          document.scope === "global" ? "warning" : "secondary"
                        }
                      >
                        {document.scope}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {document.classification}
                    </TableCell>
                    <TableCell className="text-xs tabular-nums">
                      {document.chunk_count}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {/* Source version is what the uploader stamped; index
                          version is what the retrieval index was built with. */}
                      {document.source_version}
                      {document.index_version
                        ? ` · ${document.index_version}`
                        : ""}
                    </TableCell>
                    <TableCell className="whitespace-nowrap font-mono text-xs">
                      {formatDateTime(document.created_at)}
                    </TableCell>
                    {canWrite && (
                      <TableCell>
                        {(document.scope !== "global" || canPublishGlobal) && (
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Remove document"
                            disabled={busy}
                            onClick={() => void remove(document)}
                            className="text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          >
                            <Trash2 />
                          </Button>
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {jobs.length > 0 && (
        <Card className="overflow-hidden">
          <CardHeader>
            <CardTitle className="text-base">Ingest jobs</CardTitle>
            <CardDescription>
              Uploads queued from this browser. A document only becomes
              retrievable once its job reports done.
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-1">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Queued</TableHead>
                  <TableHead>File</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Attempts</TableHead>
                  <TableHead>Chunks</TableHead>
                  <TableHead>Notes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {jobs.map((job) => (
                  <TableRow key={job.job_id} className="align-top">
                    <TableCell className="whitespace-nowrap font-mono text-xs">
                      {formatDateTime(job.created_at)}
                    </TableCell>
                    <TableCell className="text-xs">
                      <p className="font-medium">{job.title}</p>
                      <p className="text-muted-foreground">{job.filename}</p>
                    </TableCell>
                    <TableCell>
                      <Badge variant={JOB_BADGE[job.status] ?? "secondary"}>
                        {job.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs tabular-nums">
                      {job.attempts}
                    </TableCell>
                    <TableCell className="text-xs tabular-nums">
                      {job.chunk_count ?? "—"}
                    </TableCell>
                    <TableCell className="max-w-64 text-xs text-muted-foreground">
                      {/* A warning means the file was indexed but not read
                          whole — the uploader is the only person who can do
                          anything about it, so it is never swallowed. */}
                      {job.error ??
                        (job.warnings.length > 0
                          ? job.warnings.join(" · ")
                          : "—")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {canWrite && (
        <Modal
          open={formOpen}
          onClose={() => {
            if (!busy) setFormOpen(false);
          }}
          title="Add document"
          subtitle="The file is staged to object storage and parsed by the worker; nothing is retrievable until its job reports done."
          footerActions={
            <>
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => setFormOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                form="knowledge-upload"
                disabled={busy || !file || !title.trim()}
              >
                {busy ? <Loader2 className="animate-spin" /> : <Upload />}
                {busy ? "Uploading…" : "Upload"}
              </Button>
            </>
          }
        >
          <form id="knowledge-upload" onSubmit={upload} className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">File</span>
              <Input
                type="file"
                onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-sm font-medium">Title</span>
              <Input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="How this document will be listed"
              />
            </label>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">Domain</span>
                <Input
                  value={domain}
                  onChange={(event) => setDomain(event.target.value)}
                  placeholder="shared"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-medium">Scope</span>
                <Select
                  value={scope}
                  onChange={(event) =>
                    setScope(event.target.value as "tenant" | "global")
                  }
                >
                  <option value="tenant">This tenant only</option>
                  <option value="global" disabled={!canPublishGlobal}>
                    Every tenant
                    {canPublishGlobal ? "" : " — platform admin only"}
                  </option>
                </Select>
              </label>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
