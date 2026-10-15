import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { AppShell, UiProvider } from "@dw/ui";

/** jsdom's `navigator.onLine` is a fixed true; the browser's flips. */
let online = true;
function goOffline(value: boolean) {
  online = !value;
  act(() => {
    window.dispatchEvent(new Event(value ? "offline" : "online"));
  });
}

beforeAll(() => {
  Object.defineProperty(window.navigator, "onLine", {
    configurable: true,
    get: () => online,
  });
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

afterEach(() => {
  cleanup();
  online = true;
});

const BANNER = /^Mất kết nối mạng\. Các thao tác thay đổi dữ liệu tạm khóa/;

describe("the shell's offline banner (ui-quality §4)", () => {
  it("shows while the browser has no network, as a status, and goes when it is back", () => {
    render(
      <UiProvider>
        <AppShell brand="DW" navItems={[]}>
          <p>Trang</p>
        </AppShell>
      </UiProvider>,
    );
    expect(screen.queryByText(BANNER)).toBeNull();

    goOffline(true);
    const banner = screen.getByText(BANNER).closest("[role='status']");
    expect(banner).not.toBeNull();
    // The page under it stays: nothing typed is thrown away.
    expect(screen.getByText("Trang")).toBeTruthy();

    goOffline(false);
    expect(screen.queryByText(BANNER)).toBeNull();
  });

  it("is drawn on a page opened while already offline", () => {
    online = false;
    render(
      <UiProvider>
        <AppShell brand="DW" navItems={[]}>
          <p>Trang</p>
        </AppShell>
      </UiProvider>,
    );
    expect(screen.getByText(BANNER)).toBeTruthy();
  });
});
