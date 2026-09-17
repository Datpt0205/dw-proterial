"use client";

import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Building,
  Loader2,
  Lock,
  LockOpen,
  Pencil,
  ShieldPlus,
  Trash2,
} from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  cn,
} from "@dw/ui";
import {
  ApiError,
  type PlatformOperator,
  type PlatformTenant,
  type PlatformUserRef,
} from "@dw/api-client";
import { apiClient } from "../../lib/session";
import { useAuth } from "../../lib/auth/auth-context";
import { PageHeading } from "../../components/page-heading";
import { EmptyState } from "../../components/empty-state";
import { EmailPicker, type EmailOption } from "../../components/email-picker";

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong.";
}

export default function PlatformPage() {
  const { isPlatformOperator } = useAuth();

  if (!isPlatformOperator) {
    return (
      <EmptyState
        icon={Building}
        title="Operators only"
        description="This area is for platform operators. Ask one to add you."
      />
    );
  }
  return <PlatformConsole />;
}

function PlatformConsole() {
  const [tenants, setTenants] = useState<PlatformTenant[] | null>(null);
  const [operators, setOperators] = useState<PlatformOperator[] | null>(null);
  const [users, setUsers] = useState<PlatformUserRef[]>([]);
  const emailOptions: EmailOption[] = users.map((u) => ({
    email: u.email ?? "",
    display_name: u.display_name,
  }));

  const loadTenants = useCallback(() => {
    apiClient()
      .listTenants()
      .then(setTenants)
      .catch((error) => {
        setTenants([]);
        toast.error(errorText(error));
      });
  }, []);
  const loadOperators = useCallback(() => {
    apiClient()
      .listOperators()
      .then(setOperators)
      .catch(() => setOperators([]));
  }, []);

  useEffect(() => {
    loadTenants();
    loadOperators();
    // The email pickers; a failure just leaves them empty, boxes still typeable.
    apiClient()
      .listPlatformUsers()
      .then(setUsers)
      .catch(() => setUsers([]));
  }, [loadTenants, loadOperators]);

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeading icon={Building} title="Platform" />
      <CreateTenantCard onCreated={loadTenants} />
      <TenantsCard
        tenants={tenants}
        emailOptions={emailOptions}
        onChanged={loadTenants}
      />
      <OperatorsCard
        operators={operators}
        emailOptions={emailOptions}
        onChanged={loadOperators}
      />
    </div>
  );
}

// Slug is a URL-safe unique handle. Derive it from the name so nobody has to
// think about it; a manual edit takes over. The API validates + enforces
// uniqueness regardless.
function slugify(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "") // strip Vietnamese accents
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function CreateTenantCard({ onCreated }: { onCreated: () => void }) {
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [name, setName] = useState("");
  // Plans are not enforced yet (basic/pro/enterprise behave the same), so the
  // picker is hidden and every new tenant gets the default plan silently.
  const planId = "professional";
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!slug.trim() || !name.trim()) return;
    setBusy(true);
    try {
      await apiClient().createTenant({
        slug: slug.trim(),
        name: name.trim(),
        planId,
      });
      setSlug("");
      setName("");
      setSlugEdited(false);
      toast.success(`Tenant "${name.trim()}" created.`);
      onCreated();
    } catch (error) {
      toast.error(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="mt-3">
      <CardHeader>
        <CardTitle>New tenant (company)</CardTitle>
        <CardDescription>
          Creates the tenant with a default “main” workspace and a plan.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">
            Slug
          </span>
          <Input
            className="w-40"
            placeholder="fis"
            value={slug}
            onChange={(e) => {
              setSlug(e.target.value);
              setSlugEdited(true);
            }}
          />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">
            Name
          </span>
          <Input
            className="w-56"
            placeholder="FPT IS"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (!slugEdited) setSlug(slugify(e.target.value));
            }}
          />
        </label>
        <Button
          onClick={submit}
          disabled={busy || !slug.trim() || !name.trim()}
        >
          {busy ? <Loader2 className="size-4 animate-spin" /> : null}
          Create
        </Button>
      </CardContent>
    </Card>
  );
}

function TenantsCard({
  tenants,
  emailOptions,
  onChanged,
}: {
  tenants: PlatformTenant[] | null;
  emailOptions: EmailOption[];
  onChanged: () => void;
}) {
  const [assignFor, setAssignFor] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [renameFor, setRenameFor] = useState<string | null>(null);
  const [newName, setNewName] = useState("");

  const rename = async (tenantId: string) => {
    if (!newName.trim()) return;
    try {
      const t = await apiClient().renameTenant(tenantId, newName.trim());
      toast.success(`Renamed to "${t.name}".`);
      setRenameFor(null);
      setNewName("");
      onChanged();
    } catch (error) {
      toast.error(errorText(error));
    }
  };

  const toggleLock = async (t: PlatformTenant) => {
    try {
      await apiClient().setTenantLocked(t.id, t.status !== "locked");
      toast.success(
        `${t.name} ${t.status === "locked" ? "unlocked" : "locked"}.`,
      );
      onChanged();
    } catch (error) {
      toast.error(errorText(error));
    }
  };

  const assign = async (tenantId: string) => {
    if (!email.trim()) return;
    try {
      const ref = await apiClient().assignOrgAdmin(tenantId, email.trim());
      toast.success(`${ref.display_name} is now an org admin.`);
      setAssignFor(null);
      setEmail("");
      onChanged();
    } catch (error) {
      toast.error(errorText(error));
    }
  };

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Tenants</CardTitle>
        <CardDescription>Every company on the platform.</CardDescription>
      </CardHeader>
      <CardContent>
        {tenants === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : tenants.length === 0 ? (
          <EmptyState
            icon={Building}
            title="No tenants yet"
            description="Create the first company above."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[42rem] text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-3 py-2 font-medium">Company</th>
                  <th className="px-3 py-2 font-medium">Workspaces</th>
                  <th className="px-3 py-2 font-medium">Members</th>
                  <th className="px-3 py-2 font-medium">Status</th>
                  <th className="px-3 py-2 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tenants.map((t) => (
                  <tr key={t.id} className="border-b last:border-0">
                    <td className="px-3 py-2.5">
                      <div className="font-semibold">{t.name}</div>
                      <div className="text-xs text-muted-foreground">
                        {t.slug}
                      </div>
                      {assignFor === t.id && (
                        <div className="mt-2 flex items-center gap-2">
                          <div className="w-56">
                            <EmailPicker
                              value={email}
                              onChange={setEmail}
                              options={emailOptions}
                              placeholder="Chọn hoặc gõ email…"
                              className="h-8 py-1"
                            />
                          </div>
                          <Button size="sm" onClick={() => assign(t.id)}>
                            Assign
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setAssignFor(null)}
                          >
                            Cancel
                          </Button>
                        </div>
                      )}
                      {renameFor === t.id && (
                        <div className="mt-2 flex items-center gap-2">
                          <Input
                            className="h-8 w-56 py-1"
                            value={newName}
                            onChange={(e) => setNewName(e.target.value)}
                            placeholder={t.name}
                          />
                          <Button size="sm" onClick={() => rename(t.id)}>
                            Save
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
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      {t.workspace_count}
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      {t.member_count}
                    </td>
                    <td className="px-3 py-2.5">
                      <Badge
                        variant={
                          t.status === "locked" ? "destructive" : "secondary"
                        }
                      >
                        {t.status}
                      </Badge>
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setAssignFor(t.id);
                            setEmail("");
                          }}
                        >
                          <ShieldPlus className="size-3.5" /> Org admin
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setRenameFor(t.id);
                            setNewName(t.name);
                          }}
                        >
                          <Pencil className="size-3.5" /> Rename
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => toggleLock(t)}
                        >
                          {t.status === "locked" ? (
                            <LockOpen className="size-3.5" />
                          ) : (
                            <Lock className="size-3.5" />
                          )}
                          {t.status === "locked" ? "Unlock" : "Lock"}
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function OperatorsCard({
  operators,
  emailOptions,
  onChanged,
}: {
  operators: PlatformOperator[] | null;
  emailOptions: EmailOption[];
  onChanged: () => void;
}) {
  const { principalId } = useAuth();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);

  const add = async () => {
    if (!email.trim()) return;
    setBusy(true);
    try {
      const ref = await apiClient().addOperator(email.trim());
      toast.success(`${ref.display_name} is now a platform operator.`);
      setEmail("");
      onChanged();
    } catch (error) {
      toast.error(errorText(error));
    } finally {
      setBusy(false);
    }
  };

  const remove = async (userId: string) => {
    try {
      await apiClient().removeOperator(userId);
      toast.success("Operator removed.");
      onChanged();
    } catch (error) {
      toast.error(errorText(error));
    }
  };

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Platform operators</CardTitle>
        <CardDescription>
          Who may provision tenants. Operators read no tenant business data.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-end gap-2">
          <div className="w-64">
            <EmailPicker
              value={email}
              onChange={setEmail}
              options={emailOptions}
              placeholder="Chọn hoặc gõ email…"
            />
          </div>
          <Button onClick={add} disabled={busy || !email.trim()}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : null}
            Add operator
          </Button>
        </div>
        {operators === null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> Loading…
          </div>
        ) : operators.length === 0 ? (
          <p className="text-sm text-muted-foreground">No operators listed.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {operators.map((o) => (
              <li
                key={o.user_id}
                className="flex items-center justify-between gap-2 px-3 py-2"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">
                    {o.display_name}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {o.email ?? o.user_id}
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className={cn(o.user_id === principalId && "invisible")}
                  onClick={() => remove(o.user_id)}
                >
                  <Trash2 className="size-4 text-destructive" />
                </Button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
