"use client";

import { useEffect, useMemo, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Badge,
  Button,
  Card,
  Flex,
  Grid,
  Spin,
  theme,
  Typography,
  type GlobalToken,
  type MenuProps,
} from "antd";
import { LogoutOutlined } from "@ant-design/icons";
import { AppShell } from "@dw/ui";
import { useAuth } from "../lib/auth/auth-context";
import { useNavBadges } from "../lib/nav/badges";
import { NAV } from "../lib/nav/registry";
import { isNavGroup, type NavEntry, type NavItem } from "../lib/nav/types";
import {
  barNav,
  currentPage,
  navPages,
  visibleNav,
} from "../lib/nav/visibility";
import { LoginScreen } from "./login-screen";
import { NotificationBell } from "./notification-bell";
import { SessionChip } from "./session-chip";
import { WorkspaceSwitcher } from "./workspace-switcher";
import { BrandMark, ContextSwitcher } from "./context-switcher";
import { FeedbackLauncher } from "./feedback/launcher";
import { SessionExpiryBanner } from "./session-expiry-banner";
import { SupportBannerSlot } from "./support-banner";
import { useSupportGrant } from "../lib/support/session";

function CenteredCard({ children }: { children: ReactNode }) {
  return (
    <Flex align="center" justify="center" className="min-h-screen p-6">
      <Card className="w-full max-w-md text-center">{children}</Card>
    </Flex>
  );
}

function FullScreenSpin({ tip }: { tip: string }) {
  return (
    <Flex
      align="center"
      justify="center"
      gap="small"
      className="min-h-screen"
      role="status"
    >
      <Spin />
      <Typography.Text type="secondary">{tip}</Typography.Text>
    </Flex>
  );
}

type MenuItems = NonNullable<MenuProps["items"]>;

/** A page as a menu item: its label is the link, so it opens in a new tab,
 * can be copied, and works from the keyboard (antd focuses the link). A count
 * is the prototype's grey pill, with its meaning in the link's name. */
function pageItem(
  page: NavItem,
  current: string | undefined,
  badges: Record<string, number>,
  token: GlobalToken,
): MenuItems[number] {
  const Icon = page.icon;
  const count = page.badgeKey ? badges[page.badgeKey] : undefined;
  return {
    key: page.href,
    icon: <Icon className="size-4" aria-hidden />,
    label: (
      <Link
        href={page.href}
        aria-current={page.href === current ? "page" : undefined}
        aria-label={count ? `${page.label} (${count})` : undefined}
      >
        {page.label}
        {count ? (
          <Badge
            count={count}
            overflowCount={99}
            className="ms-1.5"
            style={{
              backgroundColor: token.colorFill,
              color: token.colorTextSecondary,
              boxShadow: "none",
              fontWeight: token.fontWeightStrong,
            }}
          />
        ) : null}
      </Link>
    ),
  };
}

function menuItems(
  entries: readonly NavEntry[],
  current: string | undefined,
  badges: Record<string, number>,
  token: GlobalToken,
): MenuItems {
  return entries.map((entry) => {
    if (!isNavGroup(entry)) return pageItem(entry, current, badges, token);
    const Icon = entry.icon;
    return {
      key: `group:${entry.key}`,
      icon: <Icon className="size-4" aria-hidden />,
      label: entry.label,
      // A group may hold groups (sales ticket 39): a submenu inside it.
      children: menuItems(entry.items, current, badges, token),
    };
  });
}

/** Auth gate + application shell. Children render only once a workspace is
 * active; every other state gets a dedicated full-screen view. */
export function AppFrame({ children }: { children: ReactNode }) {
  const auth = useAuth();
  const { status, error, logout, active, isPlatformOperator, isSupportStaff } =
    auth;
  const pathname = usePathname();
  const router = useRouter();
  const badges = useNavBadges();
  // A grant open in this tab: its pages are reached through it.
  const grant = useSupportGrant();
  const { token } = theme.useToken();
  // Below md the feedback button joins the bar's actions instead of floating
  // over the page; while the width is not known yet, it floats as before.
  const phone = Grid.useBreakpoint().md === false;

  // The nav the user can actually reach, and the bar drawn from it: a
  // context's own pages for someone whose work is that context alone.
  const bar = useMemo(
    () => barNav(visibleNav(NAV, auth), auth, pathname),
    [auth, pathname],
  );
  const nav = bar.entries;
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
    // A support staff member with no membership of their own (ADR 0024)
    // works only through the grants listed on /support.
    if (
      !active &&
      !isPlatformOperator &&
      isSupportStaff &&
      !grant &&
      !pathname.startsWith("/support")
    ) {
      return "/support";
    }
    return null;
  }, [status, active, isPlatformOperator, isSupportStaff, grant, pathname]);

  useEffect(() => {
    if (redirectTo) router.replace(redirectTo);
  }, [redirectTo, router]);

  // The dev-login page renders outside the gate (it is how you authenticate).
  if (pathname === "/dev-login") return <>{children}</>;

  if (status === "loading") return <FullScreenSpin tip="Đang tải…" />;

  if (status === "unauthenticated") return <LoginScreen />;

  if (status === "error") {
    return (
      <CenteredCard>
        <Typography.Title level={4}>
          Không kết nối được máy chủ
        </Typography.Title>
        <Typography.Paragraph type="secondary">{error}</Typography.Paragraph>
        <Flex justify="center" gap="small">
          <Button type="primary" onClick={() => window.location.reload()}>
            Thử lại
          </Button>
          <Button onClick={logout}>Đăng xuất</Button>
        </Flex>
      </CenteredCard>
    );
  }

  if (status === "no-workspace") {
    return (
      <CenteredCard>
        <Typography.Title level={4}>
          Bạn chưa thuộc workspace nào
        </Typography.Title>
        <Typography.Paragraph type="secondary">
          Bạn đã đăng nhập nhưng chưa được thêm vào workspace nào. Hãy nhờ quản
          trị viên của công ty cấp quyền.
        </Typography.Paragraph>
        <Button icon={<LogoutOutlined aria-hidden />} onClick={logout}>
          Đăng xuất
        </Button>
      </CenteredCard>
    );
  }

  // status === "ready". While a redirect is pending, hold a loader instead of
  // mounting a page the user can't use — that is what stops its data calls from
  // firing a 403 (and a toast) before the redirect lands.
  if (redirectTo) return <FullScreenSpin tip="Đang chuyển…" />;
  return (
    <>
      <AppShell
        brand={
          bar.contexts.length > 1 ? (
            <ContextSwitcher
              contexts={bar.contexts}
              active={bar.context}
              onPick={(href) => router.push(href)}
            />
          ) : (
            <Link
              href={home}
              aria-label={
                bar.context
                  ? `Digital Worker · ${bar.context.context!.product}, về trang đầu`
                  : "Digital Worker, về trang đầu"
              }
              className="flex items-center gap-2"
            >
              <BrandMark product={bar.context?.context?.product} />
            </Link>
          )
        }
        workspace={<WorkspaceSwitcher />}
        navItems={menuItems(nav, current, badges, token)}
        selectedKey={current}
        banner={
          <>
            <SessionExpiryBanner />
            <SupportBannerSlot />
          </>
        }
        actions={
          <>
            {phone ? <FeedbackLauncher placement="bar" /> : null}
            <NotificationBell />
            <SessionChip
              contextPrefix={bar.context?.context?.roleKeyPrefix ?? null}
            />
          </>
        }
      >
        {/* Room under the page for the floating feedback button (md and up),
            so the end of a page scrolls clear of it. A region sized to the
            window keeps the same 80 px (`use-fill-height.ts` BOTTOM_GAP). */}
        <div data-feedback-room className="md:pb-20">
          {children}
        </div>
      </AppShell>
      {/* Feedback is a utility beside the app, pinned to the bottom-left
          corner of every page from md up rather than a line in the nav. */}
      {phone ? null : <FeedbackLauncher placement="float" />}
    </>
  );
}
