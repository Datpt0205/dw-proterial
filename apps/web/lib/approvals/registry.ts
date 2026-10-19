import type { ComponentType } from "react";
import type { ApiClient } from "@dw/api-client";
import type { Approval } from "@dw/contracts";
import { salesApprovalHost } from "../../app/sales/_meta/approvals";
import { apiClient } from "../session";
import type { ApprovalHost, ApprovalInbox } from "./types";

/**
 * Which context owns an approval — the ONLY place that mapping is made: the
 * service that decides it, and the inbox it is decided in when that is not
 * `/approvals`.
 *
 * PLUG-IN POINT: a context ships a manifest in its route folder and adds one
 * import plus one entry here. A context hosted by the platform API with no
 * inbox of its own needs no entry.
 */
const HOSTS: ApprovalHost[] = [salesApprovalHost];

/** The host whose prefix the approval type carries: one prefix test, here. */
export function findHost(
  hosts: readonly ApprovalHost[],
  approvalType: string,
): ApprovalHost | undefined {
  return hosts.find((host) => approvalType.startsWith(host.prefix));
}

export function clientFor(
  hosts: readonly ApprovalHost[],
  approvalType: string,
): ApiClient {
  const host = findHost(hosts, approvalType);
  return host?.client ? host.client() : apiClient();
}

/** An in-app path; `//host` is another origin and is refused. */
function inApp(href: string): boolean {
  return /^\/(?!\/)/.test(href);
}

export function inboxFor(
  hosts: readonly ApprovalHost[],
  approval: Approval,
): ApprovalInbox | null {
  const inbox = findHost(hosts, approval.approval_type)?.inbox;
  if (!inbox) return null;
  const href = inbox.href(approval);
  // The host says this type has no inbox of its own: decided here.
  if (href === null) return null;
  // A host that points outside the app is a configuration error. Showing the
  // platform's decision instead would open the second door this exists to
  // close, so it fails closed: no link, no decision (failure-modes #7).
  if (!inApp(href)) return { kind: "misconfigured" };
  return { kind: "link", label: inbox.label, href };
}

/** The client deciding an approval of this type. */
export function approvalClient(approvalType: string): ApiClient {
  return clientFor(HOSTS, approvalType);
}

/** What the approval's context draws about it, if anything. */
export function detailFor(
  hosts: readonly ApprovalHost[],
  approval: Approval,
): ComponentType<{ approval: Approval }> | null {
  return findHost(hosts, approval.approval_type)?.detail?.(approval) ?? null;
}

export function approvalDetail(
  approval: Approval,
): ComponentType<{ approval: Approval }> | null {
  return detailFor(HOSTS, approval);
}

/** Where this approval is decided, when its context has its own inbox. */
export function approvalInbox(approval: Approval): ApprovalInbox | null {
  return inboxFor(HOSTS, approval);
}
