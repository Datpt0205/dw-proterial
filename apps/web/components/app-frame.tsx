"use client";

import { useEffect, useMemo, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Loader2, LogOut } from "lucide-react";
import { RobotOutlined } from "@ant-design/icons";
import { Avatar, Badge, theme, Typography, type MenuProps } from "antd";
import { AppShell, Button } from "@dw/ui";
import { useAuth } from "../lib/auth/auth-context";
import { useNavBadges } from "../lib/nav/badges";
import { NAV } from "../lib/nav/registry";
import { isNavGroup, type NavEntry, type NavItem } from "../lib/nav/types";
import { currentPage, navPages, visibleNav } from "../lib/nav/visible";
import { LoginScreen } from "./login-screen";
import { NotificationBell } from "./notification-bell";
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

type MenuItems = NonNullable<MenuProps["items"]>;

/** A page as a menu item: its label is the link, so it opens in a new tab,
 * can be copied, and works from the keyboard (antd focuses the link). */
function pageItem(
  page: NavItem,
  current: string | undefined,
  badges: Record<string, number>,
): MenuItems[number] {
  const Icon = page.icon;
  const count = page.badgeKey ? badges[page.badgeKey] : undefined;
  return {
    key: page.href,
    icon: <Icon size={16} aria-hidden />,
    label: (
      <Link
        href={page.href}
        aria-current={page.href === current ? "page" : undefined}
      >
        {page.label}
        {count ? <Badge count={count} size="small" className="ms-2" /> : null}
      </Link>
    ),
  };
}

function menuItems(
  entries: readonly NavEntry[],
  current: string | undefined,
  badges: Record<string, number>,
): MenuItems {
  return entries.map((entry) => {
    if (!isNavGroup(entry)) return pageItem(entry, current, badges);
    const Icon = entry.icon;
    return {
      key: `group:${entry.key}`,
      icon: <Icon size={16} aria-hidden />,
      label: entry.label,
      children: entry.items.map((page) => pageItem(page, current, badges)),
    };
  });
}

/** Auth gate + application shell. Children render only once a workspace is
 * active; every other state gets a dedicated full-screen view. */
export function AppFrame({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const { status, error, logout, active, isPlatformOperator } = auth;
  const pathname = usePathname();
  const router = useRouter();
  const badges = useNavBadges();
  const { token } = theme.useToken();

  // The nav the user can actually reach.
  const nav = useMemo(() => visibleNav(NAV, auth), [auth]);
  const pages = useMemo(() => navPages(nav), [nav]);
  // Where the logo points; the old /feedback page is gone (spec 003 US5).
  const home = pages[0]?.href ?? "/";
  const current = currentPage(pages, pathname)?.href;

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

  useEffect(() => {
    if (redirectTo) router.replace(redirectTo);
  }, [redirectTo, router]);

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
      <AppShell
        brand={
          <Link
            href={home}
            aria-label="Digital Worker"
            className="flex items-center gap-2"
          >
            <Avatar
              shape="square"
              size={32}
              icon={<RobotOutlined />}
              style={{ backgroundColor: token.colorPrimary }}
            />
            <Typography.Text strong className="hidden sm:inline">
              Digital Worker
            </Typography.Text>
          </Link>
        }
        navItems={menuItems(nav, current, badges)}
        selectedKey={current}
        actions={
          <>
            <div className="min-w-0">
              <WorkspaceSwitcher />
            </div>
            <NotificationBell />
            <SessionChip />
          </>
        }
      >
        {children}
      </AppShell>
      {/* Spec 003 US5: feedback is a utility beside the app, pinned to the
          bottom-left corner of every page rather than a line in the nav. */}
      <FeedbackLauncher />
    </>
  );
}
