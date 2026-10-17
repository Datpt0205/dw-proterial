import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { AppShell, UiProvider } from "@dw/ui";

beforeAll(() => {
  // antd's responsive helpers ask for media queries jsdom does not implement.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(cleanup);

const page = (href: string, label: string) => ({
  key: href,
  label: <a href={href}>{label}</a>,
});

/** The shape `app-frame.tsx` hands the shell for a Sales PIC (ticket 39). */
const ITEMS = [
  page("/sales", "Việc cần làm"),
  page("/sales/inbox", "Hộp thư"),
  {
    key: "group:sales-cases",
    label: "Hồ sơ",
    children: [
      page("/sales/orders", "Đơn hàng"),
      page("/sales/quotes", "Báo giá"),
    ],
  },
  {
    key: "group:sales-manage",
    label: "Quản lý",
    children: [
      page("/sales/layouts", "Mẫu PO"),
      page("/sales/overview", "Tổng quan quy trình"),
    ],
  },
];

function shell(selectedKey: string) {
  return render(
    <UiProvider>
      <AppShell brand="DW" navItems={ITEMS} selectedKey={selectedKey}>
        <p>Trang</p>
      </AppShell>
    </UiProvider>,
  );
}

/** The submenu titled `label` on the bar (the horizontal menu). */
function barSubmenu(label: string): HTMLElement {
  const bar = document.querySelector(".ant-menu-horizontal") as HTMLElement;
  const title = within(bar).getByText(label);
  return title.closest(".ant-menu-submenu") as HTMLElement;
}

describe("the shell's submenus (sales ticket 39)", () => {
  it("marks the submenu holding the page on screen, and only that one", () => {
    shell("/sales/orders");
    expect(barSubmenu("Hồ sơ").className).toContain(
      "ant-menu-submenu-selected",
    );
    expect(barSubmenu("Quản lý").className).not.toContain(
      "ant-menu-submenu-selected",
    );
  });

  it("reaches a submenu by keyboard: it is a focusable menuitem that says it opens", () => {
    shell("/sales");
    const title = barSubmenu("Hồ sơ").querySelector(
      ".ant-menu-submenu-title",
    ) as HTMLElement;
    expect(title.getAttribute("role")).toBe("menuitem");
    expect(title.getAttribute("aria-haspopup")).toBe("true");
    expect(title.getAttribute("tabindex")).not.toBeNull();
  });

  it("lists every page in the drawer, every section open", () => {
    shell("/sales");
    fireEvent.click(screen.getByRole("button", { name: "Mở menu" }));
    const drawer = screen.getByRole("dialog");
    for (const label of [
      "Việc cần làm",
      "Hộp thư",
      "Đơn hàng",
      "Báo giá",
      "Mẫu PO",
      "Tổng quan quy trình",
    ]) {
      expect(within(drawer).getByRole("link", { name: label })).toBeTruthy();
    }
  });
});
