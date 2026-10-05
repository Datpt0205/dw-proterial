"use client";

import { useMemo, useState, type ReactNode } from "react";
import { MenuOutlined } from "@ant-design/icons";
import { Button, Divider, Drawer, Layout, Menu, type MenuProps } from "antd";

type NavItems = NonNullable<MenuProps["items"]>;

export interface AppShellProps {
  /** The product mark, usually a link home. */
  brand: ReactNode;
  /** The active workspace (and the way to switch it), beside the brand. */
  workspace?: ReactNode;
  /**
   * The pages, as antd menu items whose labels are the links. An item with
   * `children` is a group: a submenu on the bar, a section in the drawer.
   */
  navItems: NavItems;
  /** The key of the item for the page on screen, when it is one. */
  selectedKey?: string;
  /** What sits at the end of the bar: notifications, account. */
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

/** The items without their icons: the bar is words, the drawer keeps both. */
function withoutIcons(items: NavItems): NavItems {
  return items.map((item) => {
    if (!item || !("key" in item)) return item;
    const { icon: _icon, ...rest } = item as { icon?: ReactNode };
    void _icon;
    if ("children" in rest && Array.isArray(rest.children))
      return { ...rest, children: withoutIcons(rest.children as NavItems) };
    return rest;
  }) as NavItems;
}

/**
 * The one shell every screen renders in (CLAUDE.md "Web UI"): a 56px frosted
 * top bar (brand, workspace, the pages as a horizontal menu, then
 * notifications and the account), which moves the pages into a drawer below
 * the `lg` breakpoint. Tailwind's `lg` is antd's `screenLG` (`globals.css`),
 * so the bar and any `lg:` layout on a page switch at the same width.
 */
export function AppShell({
  brand,
  workspace,
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
  const barItems = useMemo(() => withoutIcons(navItems), [navItems]);

  return (
    <Layout className="min-h-dvh">
      <Layout.Header className="sticky top-0 z-30 flex items-center gap-2 border-b backdrop-blur-xl backdrop-saturate-150 sm:gap-3">
        <Button
          type="text"
          className="lg:hidden"
          icon={<MenuOutlined />}
          aria-label="Mở menu"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
        />
        <div className="flex shrink-0 items-center">{brand}</div>
        {workspace ? (
          <>
            <Divider orientation="vertical" className="hidden sm:block" />
            <div className="hidden min-w-0 shrink sm:flex">{workspace}</div>
          </>
        ) : null}
        <nav
          aria-label="Điều hướng chính"
          className="hidden min-w-0 flex-1 self-stretch lg:block"
        >
          <Menu
            mode="horizontal"
            items={barItems}
            selectedKeys={selectedKeys}
            className="h-full border-b-0"
          />
        </nav>
        <div className="ml-auto flex min-w-0 items-center gap-1">{actions}</div>
      </Layout.Header>
      <Drawer
        title="Menu"
        placement="left"
        size="min(20rem, 86vw)"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        {workspace ? <div className="mb-3 sm:hidden">{workspace}</div> : null}
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
      <Layout.Content className="px-4 py-5 sm:px-6 lg:px-10 lg:py-6">
        <div className="mx-auto w-full max-w-[100rem]">{children}</div>
      </Layout.Content>
    </Layout>
  );
}
