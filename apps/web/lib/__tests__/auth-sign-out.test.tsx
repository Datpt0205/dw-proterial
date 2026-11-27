import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Sales ticket 78: signing out ends this device's pushes before anything
 * else, while the workspace and the token that call needs are still stored;
 * only then is the workspace forgotten and Keycloak told. A second press
 * during the wait signs out once. keycloak-js and `lib/push.ts` are fakes.
 */

const kc = {
  token: "access",
  tokenParsed: { exp: 2_000 } as { exp?: number } | undefined,
  refreshTokenParsed: { exp: 3_000 } as { exp?: number } | undefined,
  init: vi.fn(async () => true),
  updateToken: vi.fn<(min: number) => Promise<boolean>>(),
  login: vi.fn(),
  logout: vi.fn(async () => undefined),
  onTokenExpired: undefined as undefined | (() => void),
  onAuthRefreshSuccess: undefined as undefined | (() => void),
};
const steps: string[] = [];
let release: () => void = () => undefined;
const endPushOnSignOut = vi.fn(
  () =>
    new Promise<void>((done) => {
      steps.push(
        `push:${window.localStorage.getItem("dw.active.workspaceId") ?? "none"}`,
      );
      release = done;
    }),
);

vi.mock("../auth/config", () => ({
  AUTH_MODE: "oidc",
  API_BASE_URL: "http://api.test",
}));
vi.mock("../auth/keycloak", () => ({ getKeycloak: () => kc }));
vi.mock("../push", () => ({ endPushOnSignOut }));

beforeEach(() => {
  vi.resetModules();
  steps.length = 0;
  endPushOnSignOut.mockClear();
  kc.logout.mockReset();
  kc.logout.mockImplementation(async () => {
    steps.push(
      `keycloak:${window.localStorage.getItem("dw.active.workspaceId") ?? "none"}`,
    );
  });
  window.localStorage.setItem("dw.active.tenantId", "t-1");
  window.localStorage.setItem("dw.active.workspaceId", "w-1");
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
  window.localStorage.clear();
});

async function mount() {
  const { AuthProvider, useAuth } = await import("../auth/auth-context");
  const seen: { auth?: ReturnType<typeof useAuth> } = {};
  function Probe() {
    seen.auth = useAuth();
    return <p>{seen.auth.status}</p>;
  }
  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
  await screen.findByText("ready");
  // Init may have rewritten the active workspace: sign-out starts from one.
  window.localStorage.setItem("dw.active.workspaceId", "w-1");
  return seen;
}

describe("signing out", () => {
  it("ends the device's pushes while the workspace is stored, then signs out", async () => {
    const seen = await mount();

    act(() => seen.auth!.logout());
    expect(steps).toEqual(["push:w-1"]);
    expect(kc.logout).not.toHaveBeenCalled();

    await act(async () => release());

    expect(steps).toEqual(["push:w-1", "keycloak:none"]);
    expect(window.localStorage.getItem("dw.active.tenantId")).toBeNull();
  });

  it("signs out once however often the button is pressed meanwhile", async () => {
    const seen = await mount();

    act(() => {
      seen.auth!.logout();
      seen.auth!.logout();
    });
    await act(async () => release());
    act(() => seen.auth!.logout());

    expect(endPushOnSignOut).toHaveBeenCalledOnce();
    expect(kc.logout).toHaveBeenCalledOnce();
  });
});
