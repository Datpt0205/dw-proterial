"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { API_BASE_URL, AUTH_MODE } from "./config";
import { getKeycloak } from "./keycloak";
import {
  clearActiveWorkspace,
  clearDevToken,
  devToken,
  purgeLegacyDemoTokens,
  setActiveWorkspace,
} from "../session";

export interface Membership {
  tenantId: string;
  tenantSlug: string;
  tenantName: string;
  workspaceId: string;
  workspaceSlug: string;
  workspaceName: string;
  roles: string[];
  scopes: string[];
}

export type AuthStatus =
  "loading" | "unauthenticated" | "no-workspace" | "error" | "ready";

interface AuthContextValue {
  mode: typeof AUTH_MODE;
  status: AuthStatus;
  error: string | null;
  subject: string | null;
  /** The platform user id every CRM record stores as owner or assignee. */
  principalId: string | null;
  displayName: string;
  email: string | null;
  memberships: Membership[];
  active: Membership | null;
  roles: string[];
  scopes: string[];
  /** ADR-002: a global provisioning authority. May hold no tenant membership. */
  isPlatformOperator: boolean;
  hasScope: (scope: string) => boolean;
  hasRole: (role: string) => boolean;
  login: () => void;
  register: () => void;
  logout: () => void;
  selectWorkspace: (workspaceId: string) => void;
  refreshDevSession: () => void;
}

interface BootstrapMembership {
  tenant_id: string;
  tenant_slug: string;
  tenant_name: string;
  workspace_id: string;
  workspace_slug: string;
  workspace_name: string;
  roles: string[];
  scopes: string[];
}

interface BootstrapResponse {
  principal_id: string;
  subject: string;
  email: string | null;
  display_name: string;
  memberships: BootstrapMembership[];
  is_platform_operator?: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function mapMembership(m: BootstrapMembership): Membership {
  return {
    tenantId: m.tenant_id,
    tenantSlug: m.tenant_slug,
    tenantName: m.tenant_name,
    workspaceId: m.workspace_id,
    workspaceSlug: m.workspace_slug,
    workspaceName: m.workspace_name,
    roles: m.roles,
    scopes: m.scopes,
  };
}

async function fetchBootstrap(token: string): Promise<BootstrapResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/auth/bootstrap`, {
    headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`bootstrap failed (HTTP ${res.status})`);
  }
  return (await res.json()) as BootstrapResponse;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [subject, setSubject] = useState<string | null>(null);
  const [principalId, setPrincipalId] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState<string | null>(null);
  const [memberships, setMemberships] = useState<Membership[]>([]);
  const [active, setActive] = useState<Membership | null>(null);
  const [isPlatformOperator, setIsPlatformOperator] = useState(false);
  const initStarted = useRef(false);

  const activate = useCallback(
    (m: Membership, identity: { subject: string; displayName: string }) => {
      setActive(m);
      setActiveWorkspace({
        tenantId: m.tenantId,
        workspaceId: m.workspaceId,
        subject: identity.subject,
        displayName: identity.displayName,
        tenantName: m.tenantName,
        roles: m.roles,
        scopes: m.scopes,
      });
    },
    [],
  );

  const applyBootstrap = useCallback(
    (data: BootstrapResponse) => {
      const list = data.memberships.map(mapMembership);
      setSubject(data.subject);
      setPrincipalId(data.principal_id);
      setDisplayName(data.display_name);
      setEmail(data.email);
      setMemberships(list);
      const operator = data.is_platform_operator ?? false;
      setIsPlatformOperator(operator);
      if (list.length === 0) {
        // A Platform Operator commonly holds no tenant membership (ADR-002);
        // still let them in so they can reach /platform. Everyone else lands
        // on the "no workspace, contact an admin" screen.
        setStatus(operator ? "ready" : "no-workspace");
        return;
      }
      const previous =
        typeof window !== "undefined"
          ? window.localStorage.getItem("dw.active.workspaceId")
          : null;
      const chosen = list.find((m) => m.workspaceId === previous) ?? list[0]!;
      activate(chosen, {
        subject: data.subject,
        displayName: data.display_name,
      });
      setStatus("ready");
    },
    [activate],
  );

  const loadDevSession = useCallback(() => {
    const token = devToken();
    if (!token) {
      setStatus("unauthenticated");
      return;
    }
    setStatus("loading");
    fetchBootstrap(token)
      .then(applyBootstrap)
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "bootstrap error");
        setStatus("error");
      });
  }, [applyBootstrap]);

  useEffect(() => {
    if (initStarted.current) return;
    initStarted.current = true;

    if (AUTH_MODE === "dev") {
      loadDevSession();
      return;
    }

    // Browsers that used the removed demo account switcher still hold its
    // tokens in localStorage; drop them before any auth decision is made.
    purgeLegacyDemoTokens();

    const kc = getKeycloak();
    // `login-required`: an unauthenticated visit goes straight to the Keycloak
    // page (which carries the Google/Microsoft buttons) — no in-app stopover.
    kc.init({
      onLoad: "login-required",
      pkceMethod: "S256",
      checkLoginIframe: false,
    })
      .then(async (authenticated) => {
        if (!authenticated || !kc.token) {
          // login-required is already redirecting; this renders only for the
          // moment before the browser leaves (or if the redirect is blocked).
          setStatus("unauthenticated");
          return;
        }
        kc.onTokenExpired = () => {
          // Refresh in place; when the SSO session itself has expired, fall
          // back to a full sign-in instead of limping on with a dead token.
          kc.updateToken(30).catch(() => {
            clearActiveWorkspace();
            void kc.login({ redirectUri: window.location.href });
          });
        };
        try {
          applyBootstrap(await fetchBootstrap(kc.token));
        } catch (e) {
          setError(e instanceof Error ? e.message : "bootstrap error");
          setStatus("error");
        }
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "keycloak init failed");
        setStatus("error");
      });
  }, [applyBootstrap, loadDevSession]);

  const login = useCallback(() => {
    if (AUTH_MODE === "dev") {
      window.location.href = "/dev-login";
      return;
    }
    void getKeycloak().login({ redirectUri: window.location.origin });
  }, []);

  const register = useCallback(() => {
    if (AUTH_MODE === "dev") {
      window.location.href = "/dev-login";
      return;
    }
    void getKeycloak().register({ redirectUri: window.location.origin });
  }, []);

  const logout = useCallback(() => {
    clearActiveWorkspace();
    if (AUTH_MODE === "dev") {
      clearDevToken();
      window.location.href = "/dev-login";
      return;
    }
    void getKeycloak().logout({ redirectUri: window.location.origin });
  }, []);

  const selectWorkspace = useCallback(
    (workspaceId: string) => {
      const m = memberships.find((x) => x.workspaceId === workspaceId);
      if (!m) return;
      activate(m, { subject: subject ?? "", displayName });
      setStatus("ready");
    },
    [memberships, activate, subject, displayName],
  );

  const value = useMemo<AuthContextValue>(() => {
    const roles = active?.roles ?? [];
    const scopes = active?.scopes ?? [];
    return {
      mode: AUTH_MODE,
      status,
      error,
      subject,
      principalId,
      displayName,
      email,
      memberships,
      active,
      roles,
      scopes,
      isPlatformOperator,
      hasScope: (scope: string) =>
        roles.includes("platform_admin") || scopes.includes(scope),
      hasRole: (role: string) => roles.includes(role),
      login,
      register,
      logout,
      selectWorkspace,
      refreshDevSession: loadDevSession,
    };
  }, [
    status,
    error,
    subject,
    principalId,
    displayName,
    email,
    memberships,
    active,
    isPlatformOperator,
    login,
    register,
    logout,
    selectWorkspace,
    loadDevSession,
  ]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within <AuthProvider>");
  }
  return ctx;
}
