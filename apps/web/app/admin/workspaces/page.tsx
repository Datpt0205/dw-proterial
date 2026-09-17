"use client";

import { useCallback, useEffect, useState } from "react";
import { Archive, Building2, Check, Loader2, Pencil, Plus } from "lucide-react";
import type { AdminWorkspace } from "@dw/contracts";
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

// Same rule as the platform CreateTenantCard: derive a URL-safe slug from the
// name; a manual edit takes over. The API validates and enforces uniqueness.
function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export default function WorkspacesPage() {
  const { hasScope } = useAuth();

  if (!hasScope("platform.workspaces.write")) {
    return (
      <EmptyState
        icon={Building2}
        title="No access"
        description="You need the workspace-management permission to view this page."
      />
    );
  }
  return <WorkspacesManager />;
}

function WorkspacesManager() {
  const [workspaces, setWorkspaces] = useState<AdminWorkspace[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      setWorkspaces(await apiClient().listAdminWorkspaces());
    } catch (e) {
      setWorkspaces([]);
      setError(errorText(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeading
        icon={Building2}
        title="Workspaces"
        description="The tenant's workspaces (departments)."
      />

      {error && (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <CreateWorkspaceCard onCreated={refresh} onError={setError} />
      <WorkspacesCard
        workspaces={workspaces}
        onChanged={refresh}
        onError={setError}
      />
    </div>
  );
}

function CreateWorkspaceCard({
  onCreated,
  onError,
}: {
  onCreated: () => void;
  onError: (message: string) => void;
}) {
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!name.trim() || !slug.trim()) return;
    setBusy(true);
    try {
      await apiClient().createWorkspace({
        name: name.trim(),
        slug: slug.trim(),
      });
      setName("");
      setSlug("");
      setSlugEdited(false);
      onCreated();
    } catch (e) {
      onError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Create workspace</CardTitle>
        <CardDescription>
          The slug is generated automatically from the name.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">
            Name
          </span>
          <Input
            className="w-56"
            placeholder="Operations"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!slugEdited) setSlug(slugify(e.target.value));
            }}
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">
            Slug
          </span>
          <Input
            className="w-40"
            placeholder="operations"
            value={slug}
            onChange={(e) => {
              setSlug(e.target.value);
              setSlugEdited(true);
            }}
          />
        </label>
        <Button
          onClick={submit}
          disabled={busy || !name.trim() || !slug.trim()}
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Plus className="size-4" />
          )}
          Create
        </Button>
      </CardContent>
    </Card>
  );
}

function WorkspacesCard({
  workspaces,
  onChanged,
  onError,
}: {
  workspaces: AdminWorkspace[] | null;
  onChanged: () => void;
  onError: (message: string) => void;
}) {
  const [renameFor, setRenameFor] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  const rename = async (workspaceId: string) => {
    if (!newName.trim()) return;
    try {
      await apiClient().renameWorkspace(workspaceId, newName.trim());
      setRenameFor(null);
      setNewName("");
      onChanged();
    } catch (e) {
      onError(errorText(e));
    }
  };

  const archive = async (workspaceId: string) => {
    try {
      await apiClient().archiveWorkspace(workspaceId);
      onChanged();
    } catch (e) {
      onError(errorText(e));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">All workspaces</CardTitle>
      </CardHeader>
      <CardContent>
        {workspaces === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : workspaces.length === 0 ? (
          <EmptyState
            icon={Building2}
            title="No workspaces yet"
            description="Create the first workspace above."
          />
        ) : (
          <div className="divide-y rounded-md border">
            {workspaces.map((w) => (
              <div key={w.workspace_id} className="px-3 py-2.5 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{w.name}</span>
                      {w.archived && (
                        <Badge variant="secondary">archived</Badge>
                      )}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">
                      {w.slug} · {w.member_count} members
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setRenameFor(w.workspace_id);
                        setNewName(w.name);
                      }}
                    >
                      <Pencil className="size-3.5" /> Rename
                    </Button>
                    {!w.archived && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => void archive(w.workspace_id)}
                      >
                        <Archive className="size-3.5" /> Archive
                      </Button>
                    )}
                  </div>
                </div>
                {renameFor === w.workspace_id && (
                  <div className="mt-2 flex items-center gap-2">
                    <Input
                      className="h-8 w-56 py-1"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      placeholder={w.name}
                    />
                    <Button
                      size="sm"
                      onClick={() => void rename(w.workspace_id)}
                    >
                      <Check className="size-3.5" /> Save
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setRenameFor(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
