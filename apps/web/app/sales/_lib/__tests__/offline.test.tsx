import { useState } from "react";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { App } from "antd";
import { OFFLINE_REASON } from "@dw/ui";
import { GuardedButton } from "../../_components/guarded-button";
import { useAction } from "../use-action";

let online = true;
function setOnline(value: boolean) {
  online = value;
  act(() => {
    window.dispatchEvent(new Event(value ? "online" : "offline"));
  });
}

beforeAll(() => {
  Object.defineProperty(window.navigator, "onLine", {
    configurable: true,
    get: () => online,
  });
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
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

afterEach(() => {
  cleanup();
  online = true;
});

describe("a Sales step while the browser is offline", () => {
  it("disables a GuardedButton, and gives it back online", () => {
    render(<GuardedButton reason={null}>Chuẩn bị</GuardedButton>);
    const button = () =>
      screen.getByRole("button", { name: "Chuẩn bị" }) as HTMLButtonElement;
    expect(button().disabled).toBe(false);

    setOnline(false);
    expect(button().disabled).toBe(true);
    // Said once by the shell's banner, not under every button.
    expect(screen.queryByRole("note")).toBeNull();

    setOnline(true);
    expect(button().disabled).toBe(false);
  });

  it("keeps a step's own reason first", () => {
    online = false;
    render(
      <GuardedButton reason="Còn 2 cờ chưa quyết định">Chuẩn bị</GuardedButton>,
    );
    expect(screen.getByRole("note").textContent).toContain(
      "Còn 2 cờ chưa quyết định",
    );
  });

  it("sends nothing from useAction and says why", async () => {
    const call = vi.fn(async () => "ok");
    function Probe() {
      const { run } = useAction();
      const [said, setSaid] = useState("");
      return (
        <>
          <button
            onClick={async () => {
              const result = await run("prepare", { v: 1 }, call, "Xong");
              setSaid(
                result.ok ? "ok" : String((result.error as Error).message),
              );
            }}
          >
            Gửi
          </button>
          <p>{said}</p>
        </>
      );
    }
    online = false;
    render(
      <App>
        <Probe />
      </App>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await screen.findByText(OFFLINE_REASON);
    expect(call).not.toHaveBeenCalled();

    setOnline(true);
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await waitFor(() => expect(call).toHaveBeenCalledTimes(1));
  });
});
