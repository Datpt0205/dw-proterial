import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  onTestFinished,
  vi,
} from "vitest";

// The keycloak adapter is not exercised here; keep it from touching the DOM.
vi.mock("../../auth/keycloak", () => ({ getKeycloak: () => ({}) }));

/**
 * Support-access ticket 03: while a support grant is open, every request
 * carries `X-DW-Support-Grant` and the grant's own tenant and workspace,
 * never the switcher's; a refusal saying the grant ended closes it; and a
 * browser whose storage throws has no grant open and keeps working.
 */

const GRANT = {
  id: "11111111-1111-4111-8111-111111111111",
  code: "SG-0012",
  tenantId: "aaaaaaaa-0000-4000-8000-000000000001",
  workspaceId: "aaaaaaaa-0000-4000-8000-000000000002",
  resourceType: "workspace",
  resourceId: null,
  scopeSetKey: "sales.case_support",
  scopes: ["sales.case.read", "sales.overview.read"],
  expiresAt: "2026-10-14T03:00:00Z",
};

let sent: Headers[] = [];

function answer(status: number, body: unknown = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      sent.push(new Headers(init?.headers));
      return new Response(JSON.stringify(body), { status });
    }),
  );
}

beforeEach(() => {
  vi.resetModules();
  sent = [];
  window.sessionStorage.clear();
  window.localStorage.clear();
  // The workspace the switcher shows: not the grant's.
  window.localStorage.setItem("dw.active.tenantId", "own-tenant");
  window.localStorage.setItem("dw.active.workspaceId", "own-workspace");
  answer(200);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function call(path = "/api/v1/sales/orders") {
  const { clientOptions } = await import("../../session");
  const impl = clientOptions("http://api.test").fetchImpl;
  if (!impl) throw new Error("clientOptions must supply a fetchImpl");
  return impl(`http://api.test${path}`, {
    headers: { Authorization: "Bearer ok" },
  });
}

describe("requests under a support grant", () => {
  it("send the grant and its tenant and workspace while one is open", async () => {
    const { startSupportGrant } = await import("../session");
    startSupportGrant(GRANT);

    await call();

    const headers = sent[0]!;
    expect(headers.get("X-DW-Support-Grant")).toBe(GRANT.id);
    expect(headers.get("X-Tenant-Id")).toBe(GRANT.tenantId);
    expect(headers.get("X-Workspace-Id")).toBe(GRANT.workspaceId);
  });

  it("send no grant, and the switcher's workspace, when none is open", async () => {
    await call();

    const headers = sent[0]!;
    expect(headers.has("X-DW-Support-Grant")).toBe(false);
    expect(headers.get("X-Tenant-Id")).toBe("own-tenant");
    expect(headers.get("X-Workspace-Id")).toBe("own-workspace");
  });

  it("close the grant when the server says it ended", async () => {
    const { startSupportGrant, openSupportGrant } = await import("../session");
    startSupportGrant(GRANT);
    answer(403, {
      code: "permission_denied",
      message: "the support grant has ended",
      details: { reason_code: "support_grant_ended", ended_reason: "revoked" },
    });

    await call();

    expect(openSupportGrant()).toBeNull();
    answer(200);
    await call();
    expect(sent[1]!.has("X-DW-Support-Grant")).toBe(false);
  });

  it("keep the grant on any other refusal", async () => {
    const { startSupportGrant, openSupportGrant } = await import("../session");
    startSupportGrant(GRANT);
    answer(403, {
      code: "permission_denied",
      message: "not allowed",
      details: { reason_code: "support_context_not_allowed" },
    });

    await call();

    expect(openSupportGrant()?.id).toBe(GRANT.id);
  });

  it("close the grant and say why when the sign-in has no second factor", async () => {
    const { startSupportGrant, openSupportGrant, supportMfaRequired } =
      await import("../session");
    startSupportGrant(GRANT);
    answer(403, { details: { reason_code: "support_mfa_required" } });

    await call();

    expect(openSupportGrant()).toBeNull();
    expect(supportMfaRequired()).toBe(true);
  });

  it("keep working, with no grant open, when sessionStorage throws", async () => {
    const { startSupportGrant, openSupportGrant } = await import("../session");
    // A private window or blocked site data: every access throws.
    const refused = () => {
      throw new DOMException("blocked", "SecurityError");
    };
    const real = window.sessionStorage;
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      value: {
        getItem: refused,
        setItem: refused,
        removeItem: refused,
        clear: refused,
      },
    });
    onTestFinished(() => {
      Object.defineProperty(window, "sessionStorage", {
        configurable: true,
        value: real,
      });
    });

    expect(() => startSupportGrant(GRANT)).not.toThrow();
    expect(openSupportGrant()).toBeNull();
    const response = await call();
    expect(response.status).toBe(200);
    expect(sent[0]!.has("X-DW-Support-Grant")).toBe(false);
  });

  it("ignore a stored value that is not a grant", async () => {
    const { openSupportGrant } = await import("../session");
    window.sessionStorage.setItem("dw.support.grant", '{"id": "x"}');
    expect(openSupportGrant()).toBeNull();
    window.sessionStorage.setItem("dw.support.grant", "not json");
    expect(openSupportGrant()).toBeNull();
  });
});
