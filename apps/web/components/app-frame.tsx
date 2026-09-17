"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Bot, Loader2, LogOut, Menu, X } from "lucide-react";
import { Button } from "@dw/ui";
import { useAuth } from "../lib/auth/auth-context";
import { NAV_ITEMS } from "../lib/nav/registry";
import { hasAnyRole } from "../lib/nav/roles";
import { LoginScreen } from "./login-screen";
import { NavLinks } from "./nav-links";
import { SessionChip } from "./session-chip";
import { WorkspaceSwitcher } from "./workspace-switcher";
import { FeedbackLauncher } from "./feedback/launcher";

function CenteredCard({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border bg-card p-8 text-center shadow-sm">
        {children}
      </div>
    </div>
  );
}

/** Auth gate + application shell. Children render only once a workspace is
 * active; every other state gets a dedicated full-screen view. */
export function AppFrame({ children }: { children: ReactNode }) {
  const { status, error, logout, active, isPlatformOperator, hasScope, roles } =
    useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const [navigationOpen, setNavigationOpen] = useState(false);

  // The nav the user can actually reach — the same filter NavLinks applies.
  const visibleNav = useMemo(
    () =>
      NAV_ITEMS.filter(
        (item) =>
          (!item.operatorOnly || isPlatformOperator) &&
          (!item.scope || hasScope(item.scope)) &&
          (!item.roles || hasAnyRole(roles, item.roles)),
      ),
    [isPlatformOperator, hasScope, roles],
  );
  // Where the logo points; the old /feedback page is gone (spec 003 US5).
  const home = visibleNav[0]?.href ?? "/";

  // Where to send the user when the page they are on isn't one they can use.
  const redirectTo = useMemo(() => {
    if (status !== "ready") return null;
    // A Platform Operator with no tenant membership (ADR-002) belongs on the
    // provisioning area — every other page needs a workspace context.
    if (!active && isPlatformOperator && !pathname.startsWith("/platform")) {
      return "/platform";
    }
    return null;
  }, [status, active, isPlatformOperator, pathname]);

  useEffect(() => setNavigationOpen(false), [pathname]);
  useEffect(() => {
    if (redirectTo) router.replace(redirectTo);
  }, [redirectTo, router]);
  useEffect(() => {
    document.body.style.overflow = navigationOpen ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [navigationOpen]);

  // The dev-login page renders outside the gate (it is how you authenticate).
  if (pathname === "/dev-login") return <>{children}</>;

  if (status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 size-5 animate-spin" /> Loading…
      </div>
    );
  }

  if (status === "unauthenticated") return <LoginScreen />;

  if (status === "error") {
    return (
      <CenteredCard>
        <h1 className="text-lg font-semibold">Could not reach the server</h1>
        <p className="mt-2 text-sm text-muted-foreground">{error}</p>
        <div className="mt-5 flex justify-center gap-2">
          <Button onClick={() => window.location.reload()}>Retry</Button>
          <Button variant="outline" onClick={logout}>
            Sign out
          </Button>
        </div>
      </CenteredCard>
    );
  }

  if (status === "no-workspace") {
    return (
      <CenteredCard>
        <h1 className="text-lg font-semibold">No workspace yet</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          You are signed in but not assigned to any workspace yet. Contact an
          administrator to be granted access.
        </p>
        <Button className="mt-5" variant="outline" onClick={logout}>
          <LogOut /> Sign out
        </Button>
      </CenteredCard>
    );
  }

  // status === "ready". While a redirect is pending, hold a loader instead of
  // mounting a page the user can't use — that is what stops its data calls from
  // firing a 403 (and a toast) before the redirect lands.
  if (redirectTo) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        <Loader2 className="mr-2 size-5 animate-spin" /> Đang chuyển…
      </div>
    );
  }
  return (
    <>
      <div className="flex min-h-dvh bg-background">
        {navigationOpen && (
          <button
            aria-label="Close menu"
            className="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-[2px] lg:hidden"
            onClick={() => setNavigationOpen(false)}
          />
        )}
        {/* The rule lives on the blocks, not on the whole rail: the brand sits
            in the same band as the header and shares its bottom line, while
            only the nav below carries the vertical divider. */}
        <aside
          className={`fixed inset-y-0 left-0 z-50 flex w-[min(19rem,86vw)] flex-col bg-white/95 shadow-2xl backdrop-blur-xl transition-transform duration-300 lg:sticky lg:top-0 lg:z-auto lg:h-dvh lg:w-[11rem] lg:translate-x-0 lg:shadow-none ${navigationOpen ? "translate-x-0" : "-translate-x-full"}`}
        >
          <Link
            href={home}
            className="flex h-16 shrink-0 items-center gap-2.5 border-b px-5"
          >
            <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-[#123f67] to-[#071f38] text-primary-foreground shadow-lg shadow-primary/15">
              <Bot className="size-4" />
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-bold leading-tight tracking-wide">
                Digital Worker
              </span>
              <span className="block text-[9px] font-semibold uppercase tracking-[0.18em] text-slate-400">
                Platform
              </span>
            </span>
            <button
              type="button"
              aria-label="Close menu"
              className="ml-auto rounded-lg p-2 text-muted-foreground hover:bg-muted lg:hidden"
              onClick={(event) => {
                event.preventDefault();
                setNavigationOpen(false);
              }}
            >
              <X className="size-5" />
            </button>
          </Link>
          <div className="flex-1 overflow-y-auto border-r px-3 py-4">
            <NavLinks />
          </div>
        </aside>
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 border-b bg-white/95 backdrop-blur-xl">
            <div className="flex h-16 items-center justify-between gap-2 px-3 sm:px-4">
              <div className="flex min-w-0 items-center gap-3">
                <button
                  type="button"
                  aria-label="Open menu"
                  onClick={() => setNavigationOpen(true)}
                  className="flex size-10 shrink-0 items-center justify-center rounded-xl border bg-white text-foreground shadow-sm lg:hidden"
                >
                  <Menu className="size-5" />
                </button>
                <WorkspaceSwitcher />
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <SessionChip />
              </div>
            </div>
          </header>
          <main className="flex-1 px-3 py-4 sm:px-4 sm:py-5">
            <div className="mx-auto w-full max-w-[100rem]">{children}</div>
          </main>
        </div>
      </div>
      {/* Spec 003 US5: feedback is a utility beside the app, pinned to the
          bottom-left corner of every page rather than a line in the nav. */}
      <FeedbackLauncher />
    </>
  );
}
