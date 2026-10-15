import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The keycloak adapter is not exercised here; keep it from touching the DOM.
vi.mock("../auth/keycloak", () => ({ getKeycloak: () => ({}) }));

const HOUR = 3_600_000;

beforeEach(() => {
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** An HTTP date `ms` from this device's now, as a server would write it. */
function httpDate(ms: number): string {
  return new Date(Date.now() + ms).toUTCString();
}

describe("the server's clock (ui-quality §8)", () => {
  it("is this device's clock until a response says otherwise", async () => {
    const { serverNow } = await import("../server-clock");
    expect(Math.abs(serverNow() - Date.now())).toBeLessThan(50);
  });

  it("follows the Date header of a response, and ignores one it cannot read", async () => {
    const { noteServerDate, serverNow } = await import("../server-clock");
    noteServerDate(httpDate(2 * HOUR));
    expect(Math.abs(serverNow() - (Date.now() + 2 * HOUR))).toBeLessThan(1500);
    noteServerDate("not a date");
    noteServerDate(null);
    expect(Math.abs(serverNow() - (Date.now() + 2 * HOUR))).toBeLessThan(1500);
  });

  it("is read off every API answer, and is what useNow counts with", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("{}", {
            status: 200,
            headers: { Date: httpDate(-3 * HOUR) },
          }),
      ),
    );
    const { clientOptions } = await import("../session");
    await clientOptions("http://api.test").fetchImpl!("http://api.test/a", {});

    const { useNow } = await import("../use-now");
    const now = renderHook(() => useNow()).result.current;
    expect(Math.abs(now - (Date.now() - 3 * HOUR))).toBeLessThan(1500);
  });
});
