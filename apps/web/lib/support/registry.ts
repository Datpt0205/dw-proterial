import type { ComponentType } from "react";
import { salesSupportHost } from "../../app/sales/_meta/support";
import type { OpenSupportGrant } from "./session";

/**
 * What a bounded context plugs into support access (support-access ticket 03):
 * where a grant of one of its scope sets opens, and, optionally, its own
 * banner for the shell's support slot. The platform knows no context's
 * resources; the context names them.
 *
 * PLUG-IN POINT: a context ships a manifest in its route folder and adds one
 * import plus one entry to `HOSTS`, like `lib/approvals/registry.ts`.
 */
export interface SupportHost {
  /** The scope set keys the context registered (`SupportScopeCatalog`). */
  scopeSetKeys: readonly string[];
  /** The page a grant opens on: an in-app path. */
  landing: (resourceType: string, resourceId: string | null) => string;
  /** The context's own banner; the platform's is drawn when absent. */
  Banner?: ComponentType<{ grant: OpenSupportGrant; onExit: () => void }>;
}

const HOSTS: SupportHost[] = [salesSupportHost];

/** An in-app path; `//host` is another origin and is refused. */
function inApp(href: string): boolean {
  return /^\/(?!\/)/.test(href);
}

export function findSupportHost(
  hosts: readonly SupportHost[],
  scopeSetKey: string,
): SupportHost | undefined {
  return hosts.find((host) => host.scopeSetKeys.includes(scopeSetKey));
}

/**
 * Where a grant opens: the matching context's landing page, or `/` when no
 * context claims the scope set or its page is not in this app (failing
 * closed: the home page asks the server like any other).
 */
export function landingFor(
  hosts: readonly SupportHost[],
  resourceType: string,
  scopeSetKey: string,
  resourceId: string | null,
): string {
  const host = findSupportHost(hosts, scopeSetKey);
  if (!host) return "/";
  const href = host.landing(resourceType, resourceId);
  return inApp(href) ? href : "/";
}

/** The page the open grant lands on, from the contexts this app ships. */
export function supportLanding(
  resourceType: string,
  scopeSetKey: string,
  resourceId: string | null,
): string {
  return landingFor(HOSTS, resourceType, scopeSetKey, resourceId);
}

/** The banner the context of ``grant`` draws, if it ships one. */
export function supportBanner(
  grant: OpenSupportGrant,
): SupportHost["Banner"] | undefined {
  return findSupportHost(HOSTS, grant.scopeSetKey)?.Banner;
}
