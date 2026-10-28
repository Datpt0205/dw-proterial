import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../auth/keycloak", () => ({ getKeycloak: () => ({}) }));

/**
 * Identical reads in flight at once share one request (2026-10-28: a page
 * load read `sales/inbox` three times). Only while in flight, only a GET, and
 * keyed by what makes it a different request.
 */

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.resetModules();
  window.localStorage.clear();
  fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
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

const asAn = { headers: { Authorization: "Bearer an" } };

describe("identical reads in flight", () => {
  it("share one request, and each caller reads its own body", async () => {
    const impl = await fetchImpl();
    const [a, b] = await Promise.all([
      impl("http://api.test/api/v1/sales/inbox", asAn),
      impl("http://api.test/api/v1/sales/inbox", asAn),
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(await a.json()).toEqual({ ok: true });
    expect(await b.json()).toEqual({ ok: true });
  });

  it("ask the server again once the first one has answered", async () => {
    const impl = await fetchImpl();
    await impl("http://api.test/api/v1/sales/inbox", asAn);
    await impl("http://api.test/api/v1/sales/inbox", asAn);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("are never shared for a write, another person or another workspace", async () => {
    const impl = await fetchImpl();
    await Promise.all([
      impl("http://api.test/api/v1/sales/x", {
        ...asAn,
        method: "POST",
        body: "{}",
      }),
      impl("http://api.test/api/v1/sales/x", {
        ...asAn,
        method: "POST",
        body: "{}",
      }),
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(2);

    await Promise.all([
      impl("http://api.test/api/v1/sales/inbox", asAn),
      impl("http://api.test/api/v1/sales/inbox", {
        headers: { Authorization: "Bearer binh" },
      }),
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(4);

    window.localStorage.setItem("dw.active.tenantId", "t-1");
    window.localStorage.setItem("dw.active.workspaceId", "w-1");
    const first = impl("http://api.test/api/v1/sales/inbox", asAn);
    window.localStorage.setItem("dw.active.workspaceId", "w-2");
    const second = impl("http://api.test/api/v1/sales/inbox", asAn);
    await Promise.all([first, second]);
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });
});
