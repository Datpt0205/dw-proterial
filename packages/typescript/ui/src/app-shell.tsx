"use client";

import { useMemo, useState, type ReactNode } from "react";
import { MenuOutlined } from "@ant-design/icons";
import { Button, Drawer, Layout, Menu, type MenuProps } from "antd";

type NavItems = NonNullable<MenuProps["items"]>;

export interface AppShellProps {
  /** The product mark, usually a link home. */
  brand: ReactNode;
  /**
   * The pages, as antd menu items whose labels are the links. An item with
   * `children` is a group: a submenu on the bar, a section in the drawer.
   */
  navItems: NavItems;
  /** The key of the item for the page on screen, when it is one. */
  selectedKey?: string;
  /** What sits at the end of the bar: workspace, notifications, account. */
  actions?: ReactNode;
  children: ReactNode;
}

/** The groups holding `key`, so the drawer opens on the current page's section. */
function groupsHolding(items: NavItems, key: string | undefined): string[] {
  if (!key) return [];
  const keys: string[] = [];
  for (const item of items) {
    if (
      item &&
      "children" in item &&
      item.children?.some((child) => child?.key === key)
    ) {
      keys.push(String(item.key));
    }
  }
  return keys;
}

/**
 * The one shell every screen renders in (CLAUDE.md "Web UI"): a top bar with
 * the pages as a horizontal menu, which moves into a drawer below the `lg`
 * breakpoint. Tailwind's `lg` is antd's `screenLG` (`globals.css`), so the bar
 * and any `lg:` layout on a page switch at the same width.
 */
export function AppShell({
  brand,
  navItems,
  selectedKey,
  actions,
  children,
}: AppShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const selectedKeys = selectedKey ? [selectedKey] : [];
  const openKeys = useMemo(
    () => groupsHolding(navItems, selectedKey),
    [navItems, selectedKey],
  );

  return (
    <Layout className="min-h-dvh">
      <Layout.Header className="sticky top-0 z-30 flex items-center gap-2 border-b px-3 sm:gap-3 sm:px-4">
        <Button
          type="text"
          className="lg:hidden"
          icon={<MenuOutlined />}
          aria-label="Mở menu"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
        />
        <div className="flex shrink-0 items-center">{brand}</div>
        <nav
          aria-label="Điều hướng chính"
          className="hidden min-w-0 flex-1 lg:block"
        >
          <Menu
            mode="horizontal"
            items={navItems}
            selectedKeys={selectedKeys}
            className="border-b-0"
          />
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-2">{actions}</div>
      </Layout.Header>
      <Drawer
        title="Menu"
        placement="left"
        size="min(20rem, 86vw)"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        <nav aria-label="Điều hướng chính">
          <Menu
            mode="inline"
            items={navItems}
            selectedKeys={selectedKeys}
            defaultOpenKeys={openKeys}
            onClick={() => setDrawerOpen(false)}
            className="border-e-0"
          />
        </nav>
      </Drawer>
      <Layout.Content className="px-3 py-4 sm:px-4 sm:py-5">
        <div className="mx-auto w-full max-w-[100rem]">{children}</div>
      </Layout.Content>
    </Layout>
  );
}
