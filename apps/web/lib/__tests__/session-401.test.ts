import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The keycloak adapter is not exercised here; keep it from touching the DOM.
vi.mock("../auth/keycloak", () => ({ getKeycloak: () => ({}) }));

/**
 * A missing or unverifiable bearer token is 401 since the platform split it
 * from 403 (platform-runtime/unauthenticated-401). On a 401 the client marks
 * the session ended, which the shell's banner reads to offer signing in again
 * - but only for a request that carried a token, i.e. a session that died. A
 * request sent without one (the login screen's own calls) answering 401 is
 * not a session ending. It never navigates by itself: a page that leaves on
 * its own takes what was being typed with it (ui-quality §4).
 */

let assigned: string[] = [];

beforeEach(() => {
  vi.resetModules();
  assigned = [];
  const location = {
    get href() {
      return "http://localhost/somewhere";
    },
    set href(value: string) {
      assigned.push(value);
    },
  };
  Object.defineProperty(window, "location", {
    value: location,
    configurable: true,
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response("{}", { status: 401 })),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function fetchImpl() {
  const { clientOptions } = await import("../session");
  const impl = clientOptions("http://api.test").fetchImpl;
  if (!impl) throw new Error("clientOptions must supply a fetchImpl");
  return impl;
}

async function ended(): Promise<boolean> {
  const { useSessionEnded } = await import("../session-expiry");
  const { renderHook } = await import("@testing-library/react");
  return renderHook(() => useSessionEnded()).result.current;
}

describe("a 401", () => {
  it("marks a session whose token died as ended, and stays on the page", async () => {
    const impl = await fetchImpl();
    const withToken = { headers: { Authorization: "Bearer expired" } };
    expect(await ended()).toBe(false);

    await Promise.all([
      impl("http://api.test/a", withToken),
      impl("http://api.test/b", withToken),
    ]);

    expect(await ended()).toBe(true);
    expect(assigned).toEqual([]);
  });

  it("is no session ending for a request that carried no token", async () => {
    const impl = await fetchImpl();

    const response = await impl("http://api.test/auth/bootstrap", {});

    expect(response.status).toBe(401);
    expect(await ended()).toBe(false);
    expect(assigned).toEqual([]);
  });

  it("leaves a 403 to the caller", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 403 })),
    );
    const impl = await fetchImpl();

    await impl("http://api.test/a", {
      headers: { Authorization: "Bearer ok" },
    });

    expect(await ended()).toBe(false);
    expect(assigned).toEqual([]);
  });
});
