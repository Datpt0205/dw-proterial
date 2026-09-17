"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bot, LogIn } from "lucide-react";
import type { DemoUser } from "@dw/contracts";
import { Badge, Button, Card, CardContent } from "@dw/ui";
import { AUTH_MODE } from "../../lib/auth/config";
import { apiClient, loginAsDev } from "../../lib/session";

const ROLE_LABEL: Record<string, string> = {
  member: "Staff",
  approver: "Manager",
  platform_admin: "Admin",
};

/** Dev-only one-click login (host `make dev` without Keycloak). */
export default function DevLoginPage() {
  const router = useRouter();
  const [users, setUsers] = useState<DemoUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  // Demo persona login exists only in dev-auth builds. In OIDC mode (dev and
  // prod both run OIDC) this page must not render or call the demo API — real
  // sign-in is Keycloak. Bounce to the app, which sends the user to Keycloak.
  useEffect(() => {
    if (AUTH_MODE !== "dev") {
      router.replace("/");
      return;
    }
    apiClient()
      .listDemoUsers()
      .then(setUsers)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "could not load"),
      );
  }, [router]);

  if (AUTH_MODE !== "dev") return null;

  async function pick(subject: string) {
    setBusy(subject);
    try {
      await loginAsDev(subject);
      window.location.href = "/";
    } catch (e) {
      setError(e instanceof Error ? e.message : "sign-in failed");
      setBusy(null);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 p-6">
      <div className="flex items-center gap-3">
        <span className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
          <Bot className="size-5" />
        </span>
        <div>
          <h1 className="text-xl font-semibold">Sign in (dev mode)</h1>
          <p className="text-sm text-muted-foreground">
            Pick a demo account to enter quickly.
          </p>
        </div>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="grid gap-3 sm:grid-cols-2">
        {users?.map((u) => (
          <Card key={u.subject}>
            <CardContent className="flex flex-col gap-3 pt-5">
              <div>
                <p className="font-medium">{u.display_name}</p>
                <p className="text-xs text-muted-foreground">{u.tenant_name}</p>
              </div>
              <div className="flex flex-wrap gap-1">
                {u.roles.map((r) => (
                  <Badge key={r} variant="secondary">
                    {ROLE_LABEL[r] ?? r}
                  </Badge>
                ))}
              </div>
              <Button
                size="sm"
                disabled={busy === u.subject}
                onClick={() => void pick(u.subject)}
              >
                <LogIn /> {busy === u.subject ? "Entering…" : "Sign in"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
