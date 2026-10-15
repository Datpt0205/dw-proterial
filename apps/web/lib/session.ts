"use client";

import { ApiClient, type ApiClientOptions } from "@dw/api-client";
import { API_BASE_URL, AUTH_MODE } from "./auth/config";
import { getKeycloak } from "./auth/keycloak";
import { noteServerDate } from "./server-clock";
import { markSessionEnded } from "./session-expiry";
import {
  endSupportGrant,
  openSupportGrant,
  SUPPORT_GRANT_ENDED,
  SUPPORT_GRANT_HEADER,
  SUPPORT_MFA_REQUIRED,
} from "./support/session";

/**
 * Session bridge. The access token is never persisted: in `oidc` mode it lives
 * in the keycloak-js instance (in memory), in `dev` mode it is a local HS256
 * token. Only the *active workspace* (tenant/workspace ids + a display profile)
 * is kept in localStorage — those are not secrets. The backend re-verifies every
 * request, so this is convenience, never authorization.
 */

const KEYS = {
  tenant: "dw.active.tenantId",
  workspace: "dw.active.workspaceId",
  profile: "dw.active.profile",
  devToken: "dw.dev.token",
  quickAccounts: "dw.quick.accounts",
  quickActive: "dw.quick.active",
} as const;

/** The demo fast-account switcher stored An/Binh/Chi tokens under these keys.
 * The switcher is gone; auth init calls this so a browser that used it does
 * not keep dormant credentials in localStorage. */
export function purgeLegacyDemoTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(KEYS.quickActive);
  window.localStorage.removeItem(KEYS.quickAccounts);
}

export interface Session {
  tenantId: string;
  workspaceId: string;
  subject?: string;
  displayName?: string;
  tenantName?: string;
  roles?: string[];
  scopes?: string[];
}

export interface ActiveWorkspace {
  tenantId: string;
  workspaceId: string;
  subject?: string;
  displayName?: string;
  tenantName?: string;
  roles: string[];
  scopes: string[];
}

export function loadSession(): Session | null {
  if (typeof window === "undefined") return null;
  const tenantId = window.localStorage.getItem(KEYS.tenant);
  const workspaceId = window.localStorage.getItem(KEYS.workspace);
  if (!tenantId || !workspaceId) return null;
  const session: Session = { tenantId, workspaceId };
  const raw = window.localStorage.getItem(KEYS.profile);
  if (raw) {
    try {
      Object.assign(session, JSON.parse(raw) as Partial<Session>);
    } catch {
      // ignore a corrupt profile blob — core fields still work
    }
  }
  return session;
}

export function setActiveWorkspace(active: ActiveWorkspace): void {
  window.localStorage.setItem(KEYS.tenant, active.tenantId);
  window.localStorage.setItem(KEYS.workspace, active.workspaceId);
  const { subject, displayName, tenantName, roles, scopes } = active;
  window.localStorage.setItem(
    KEYS.profile,
    JSON.stringify({ subject, displayName, tenantName, roles, scopes }),
  );
}

export function clearActiveWorkspace(): void {
  window.localStorage.removeItem(KEYS.tenant);
  window.localStorage.removeItem(KEYS.workspace);
  window.localStorage.removeItem(KEYS.profile);
  purgeLegacyDemoTokens();
}

/** Dev-mode only: store the local bearer token. */
export function setDevToken(token: string): void {
  window.localStorage.setItem(KEYS.devToken, token);
}

export function devToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(KEYS.devToken);
}

export function clearDevToken(): void {
  window.localStorage.removeItem(KEYS.devToken);
}

/** Dev-mode one-click login: exchange a roster subject for a local token.
 * The active workspace + scopes are then resolved via /auth/bootstrap. */
export async function loginAsDev(subject: string): Promise<void> {
  const info = await apiClient().createDevSession(subject);
  setDevToken(info.token);
}

async function currentAccessToken(): Promise<string | null> {
  if (AUTH_MODE === "dev") {
    return typeof window === "undefined"
      ? null
      : window.localStorage.getItem(KEYS.devToken);
  }
  const kc = getKeycloak();
  if (!kc.authenticated) return null;
  try {
    await kc.updateToken(30);
  } catch {
    return null;
  }
  return kc.token ?? null;
}

export function apiClient(): ApiClient {
  return new ApiClient(clientOptions(API_BASE_URL));
}

/**
 * PLUG-IN POINT: a bounded context running in its own service exports its own
 * client factory here, built on the same `clientOptions` so it inherits the
 * tenant headers and the 401 handling.
 */
export function clientOptions(baseUrl: string): ApiClientOptions {
  return {
    baseUrl,
    getAccessToken: currentAccessToken,
    fetchImpl: async (input, init) => {
      const headers = new Headers(init?.headers);
      const grant = openSupportGrant();
      if (grant) {
        // Under a support grant the grant names the tenant and workspace,
        // never the switcher: the server builds the context from the grant
        // (support-access ticket 03).
        headers.set(SUPPORT_GRANT_HEADER, grant.id);
        headers.set("X-Tenant-Id", grant.tenantId);
        headers.set("X-Workspace-Id", grant.workspaceId);
      } else if (typeof window !== "undefined") {
        const tenantId = window.localStorage.getItem(KEYS.tenant);
        const workspaceId = window.localStorage.getItem(KEYS.workspace);
        if (tenantId && workspaceId) {
          headers.set("X-Tenant-Id", tenantId);
          headers.set("X-Workspace-Id", workspaceId);
        }
      }
      const res = await fetch(input, { ...init, headers });
      // Every answer carries the server's clock; relative labels count by it.
      noteServerDate(res.headers.get("Date"));
      // The grant expired, was revoked or lost its granter, or the sign-in
      // has no second factor: close it here, so the next request is made as
      // the person again, not refused again; /support says why.
      if (grant && res.status === 403) {
        const reason = await refusalReason(res);
        if (reason === SUPPORT_GRANT_ENDED) endSupportGrant();
        if (reason === SUPPORT_MFA_REQUIRED)
          endSupportGrant({ mfaRequired: true });
      }
      // 401 = the session is no longer authenticated (token died mid-use).
      // The shell's banner says so and offers to sign in again, instead of
      // leaving the user staring at a failed action; it does not navigate on
      // its own, which would throw away what was typed (ui-quality §4).
      // (403 = permission, handled per-call.) Only for a request that carried
      // a token: one sent without any (the login screen's own calls) also
      // answers 401 since the API split 401 from 403.
      if (res.status === 401 && headers.has("Authorization")) {
        markSessionEnded();
      }
      return res;
    },
  };
}

/** The support refusal a 403 names (`details.reason_code`), if any. */
async function refusalReason(res: Response): Promise<unknown> {
  try {
    const body: unknown = await res.clone().json();
    return (body as { details?: { reason_code?: unknown } } | null)?.details
      ?.reason_code;
  } catch {
    return undefined;
  }
}

/**
 * UI permission helper mirroring the backend rule: `platform_admin` bypasses
 * scope checks; otherwise the scope must be present. This only hides/disables
 * controls for clarity — the API is the sole authority.
 */
export function hasScope(session: Session | null, scope: string): boolean {
  if (!session) return false;
  if (session.roles?.includes("platform_admin")) return true;
  return session.scopes?.includes(scope) ?? false;
}

export function hasRole(session: Session | null, role: string): boolean {
  return session?.roles?.includes(role) ?? false;
}
