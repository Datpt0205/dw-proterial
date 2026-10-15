import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The Keycloak side of the session end (ui-quality §4): a refresh that fails
 * marks the session ended and does NOT send the browser to sign in, which
 * would throw away what was being typed; asking for more time reports whether
 * the end moved. keycloak-js is replaced by a fake with the same surface the
 * provider uses.
 */

const kc = {
  token: "access",
  tokenParsed: { exp: 2_000 } as { exp?: number } | undefined,
  refreshTokenParsed: { exp: 3_000 } as { exp?: number } | undefined,
  init: vi.fn(async () => true),
  updateToken: vi.fn<(min: number) => Promise<boolean>>(),
  login: vi.fn(),
  onTokenExpired: undefined as undefined | (() => void),
  onAuthRefreshSuccess: undefined as undefined | (() => void),
};

vi.mock("../auth/config", () => ({
  AUTH_MODE: "oidc",
  API_BASE_URL: "http://api.test",
}));
vi.mock("../auth/keycloak", () => ({ getKeycloak: () => kc }));

beforeEach(() => {
  vi.resetModules();
  kc.updateToken.mockReset();
  kc.login.mockReset();
  kc.refreshTokenParsed = { exp: 3_000 };
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            principal_id: "p",
            subject: "s",
            email: null,
            display_name: "Lan",
            memberships: [],
            is_platform_operator: true,
          }),
          { status: 200 },
        ),
    ),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function mount() {
  const { AuthProvider, useAuth } = await import("../auth/auth-context");
  const { useSessionEnded } = await import("../session-expiry");
  const seen: { auth?: ReturnType<typeof useAuth>; ended?: boolean } = {};
  function Probe() {
    seen.auth = useAuth();
    seen.ended = useSessionEnded();
    return <p>{seen.auth.status}</p>;
  }
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  await screen.findByText("ready");
  return seen;
}

describe("the Keycloak session end", () => {
  it("knows when the sign-in ends: the refresh token's expiry", async () => {
    const seen = await mount();
    expect(seen.auth!.sessionExpiresAt).toBe(3_000_000);
  });

  it("marks the session ended when the refresh fails, and stays on the page", async () => {
    const seen = await mount();
    kc.updateToken.mockRejectedValue(new Error("session expired"));

    act(() => kc.onTokenExpired!());

    await waitFor(() => expect(seen.ended).toBe(true));
    expect(kc.login).not.toHaveBeenCalled();
  });

  it("clears a 401's end when a refresh then works", async () => {
    // An access token that expired while its refresh was on the way: the API
    // answers 401, then the refresh succeeds and every later call works.
    const seen = await mount();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 401 })),
    );
    const { clientOptions } = await import("../session");
    await act(async () => {
      await clientOptions("http://api.test").fetchImpl!("http://api.test/a", {
        headers: { Authorization: "Bearer access" },
      });
    });
    await waitFor(() => expect(seen.ended).toBe(true));

    act(() => kc.onAuthRefreshSuccess!());

    await waitFor(() => expect(seen.ended).toBe(false));
  });

  it("reports whether asking for more time moved the end", async () => {
    const seen = await mount();
    kc.updateToken.mockImplementation(async () => {
      kc.refreshTokenParsed = { exp: 4_000 };
      return true;
    });
    let moved = false;
    await act(async () => {
      moved = await seen.auth!.extendSession();
    });
    expect(moved).toBe(true);
    expect(seen.auth!.sessionExpiresAt).toBe(4_000_000);

    // At the session's longest life the end no longer moves.
    kc.updateToken.mockResolvedValue(true);
    await act(async () => {
      moved = await seen.auth!.extendSession();
    });
    expect(moved).toBe(false);
  });
});
