import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { App, Button, Drawer, theme } from "antd";
import { afterEach, describe, expect, it, vi } from "vitest";
import { UiProvider } from "@dw/ui";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

/** A screen's way to give feedback: the holder `App.useApp()` reads. */
function SaveButton() {
  const { message } = App.useApp();
  return <Button onClick={() => message.success("Đã lưu")}>Lưu</Button>;
}

function MotionReading() {
  const { token } = theme.useToken();
  return <output>{String(token.motion)}</output>;
}

function reducedMotion(matches: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: matches && query === "(prefers-reduced-motion: reduce)",
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }) as MediaQueryList,
  );
}

describe("UiProvider", () => {
  it("gives a screen App.useApp() feedback, in the theme", async () => {
    render(
      <UiProvider>
        <SaveButton />
      </UiProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Lưu" }));
    expect(await screen.findByText("Đã lưu")).toBeTruthy();
  });

  it("speaks Vietnamese in antd's own labels", () => {
    render(
      <UiProvider>
        <Drawer open title="Bộ lọc" />
      </UiProvider>,
    );
    expect(screen.getByRole("button", { name: "Đóng" })).toBeTruthy();
  });

  it("turns antd's motion off when the person asked for reduced motion", () => {
    reducedMotion(true);
    render(
      <UiProvider>
        <MotionReading />
      </UiProvider>,
    );
    expect(screen.getByRole("status").textContent).toBe("false");
  });

  it("keeps antd's motion otherwise", () => {
    reducedMotion(false);
    render(
      <UiProvider>
        <MotionReading />
      </UiProvider>,
    );
    expect(screen.getByRole("status").textContent).toBe("true");
  });
});
