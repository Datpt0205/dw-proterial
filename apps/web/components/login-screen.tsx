"use client";

import { Bot, LogIn } from "lucide-react";
import { Button } from "@dw/ui";
import { useAuth } from "../lib/auth/auth-context";

/**
 * Shown while an unauthenticated visit is being redirected to the Keycloak
 * sign-in page (which carries every configured identity provider). Normally it
 * flashes for a moment; the button is the manual way through if the automatic
 * redirect was blocked.
 */
export function LoginScreen() {
  const { login, error } = useAuth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-md rounded-2xl border bg-card p-8 shadow-sm">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <span className="flex size-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Bot className="size-6" />
          </span>
          <div>
            <h1 className="text-xl font-semibold">Digital Worker Platform</h1>
            <p className="text-sm text-muted-foreground">
              Taking you to the sign-in page…
            </p>
          </div>
        </div>

        {error && (
          <p className="mb-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        )}

        <Button size="lg" className="w-full" onClick={login}>
          <LogIn /> Sign in
        </Button>
      </div>
    </div>
  );
}
