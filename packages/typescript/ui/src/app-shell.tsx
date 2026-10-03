"use client";

import { useEffect, useState, type ReactNode } from "react";
import { MenuOutlined } from "@ant-design/icons";
import { Button, Drawer, Grid, Layout, Menu, type MenuProps } from "antd";

export interface AppShellItem {
  key: string;
  /** What the item shows. The app passes its router's link here, so the
   * shell imports no framework, and so a pointer can open it in a new tab.
   * Give the link `tabIndex={-1}`: the menu is one tab stop with arrow keys
   * inside it, and an item that overflowed into "…" is hidden by opacity
   * alone, so its link would otherwise keep an invisible tab stop. */
  label: ReactNode;
  icon?: ReactNode;
}

export interface AppShellProps {
  /** Left of the header, and the drawer's title. */
  brand: ReactNode;
  items: AppShellItem[];
  /** Go to an item chosen from the keyboard (Enter on a menu item). A click
   * lands on the label's link, which navigates by itself, so this is not
   * called for it. */
  onNavigate: (key: string) => void;
  /** The item for the page on screen: highlighted and `aria-current="page"`. */
  selectedKey?: string;
  /** Right of the header. */
  extra?: ReactNode;
  /** Accessible name of the navigation landmark. */
  navLabel: string;
  /** Accessible name of the button that opens the navigation below `lg`. */
  menuLabel: string;
  children: ReactNode;
}

/**
 * The top-navbar shell: a sticky header with the brand, a horizontal menu and
 * a right-hand slot. Below antd's `lg` (992px) the menu moves into a drawer
 * opened from a button, with the same items.
 */
export function AppShell({
  brand,
  items,
  onNavigate,
  selectedKey,
  extra,
  navLabel,
  menuLabel,
  children,
}: AppShellProps) {
  const screens = Grid.useBreakpoint();
  // `lg` is unknown until antd's first layout effect; that render counts as
  // wide, so a desktop never flashes the drawer button.
  const wide = screens.lg !== false;
  const [drawerOpen, setDrawerOpen] = useState(false);

  // A route change (a link, the back button) or a resize past `lg` closes it.
  useEffect(() => setDrawerOpen(false), [selectedKey, wide]);

  const menuItems: MenuProps["items"] = items.map(({ key, label, icon }) => ({
    key,
    label,
    icon,
    ...(key === selectedKey ? { "aria-current": "page" as const } : {}),
  }));
  const selectedKeys = selectedKey ? [selectedKey] : [];
  const choose: NonNullable<MenuProps["onClick"]> = ({ key, domEvent }) => {
    // A click (or Enter) on the label's link was the link's to handle: a
    // client-side navigation, or a new tab with a modifier key.
    if (domEvent.target instanceof Element && domEvent.target.closest("a")) {
      return;
    }
    onNavigate(key);
  };

  return (
    <Layout className="min-h-dvh">
      <Layout.Header className="sticky top-0 z-30 flex items-center gap-3 border-b px-3 sm:px-4">
        {!wide && (
          <Button
            type="text"
            icon={<MenuOutlined />}
            aria-label={menuLabel}
            onClick={() => setDrawerOpen(true)}
          />
        )}
        <div className="flex shrink-0 items-center">{brand}</div>
        {wide && (
          <nav aria-label={navLabel} className="min-w-0 flex-1">
            {/* The header draws the bottom rule across its whole width. */}
            <Menu
              mode="horizontal"
              className="border-b-0"
              items={menuItems}
              selectedKeys={selectedKeys}
              onClick={choose}
            />
          </nav>
        )}
        <div className="ml-auto flex min-w-0 items-center gap-2">{extra}</div>
      </Layout.Header>
      <Drawer
        placement="left"
        size="min(19rem, 86vw)"
        title={brand}
        open={!wide && drawerOpen}
        onClose={() => setDrawerOpen(false)}
        classNames={{ body: "p-2" }}
      >
        <nav aria-label={navLabel}>
          <Menu
            mode="inline"
            items={menuItems}
            selectedKeys={selectedKeys}
            onClick={(info) => {
              choose(info);
              setDrawerOpen(false);
            }}
          />
        </nav>
      </Drawer>
      <Layout.Content className="px-3 py-4 sm:px-4 sm:py-5">
        <div className="mx-auto w-full max-w-[100rem]">{children}</div>
      </Layout.Content>
    </Layout>
  );
}
