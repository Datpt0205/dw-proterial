"use client";

import { useSyncExternalStore } from "react";

/**
 * The support grant a support staff member has open (support-access ticket 03).
 *
 * While one is open, every API request carries `X-DW-Support-Grant` and the
 * grant's own tenant and workspace (`lib/session.ts`), never the workspace the
 * switcher shows: the server builds the support context from the grant, and a
 * request naming another workspace would only be refused. Kept in
 * `sessionStorage`, so it ends with the tab; cleared by "Thoát quyền hỗ trợ"
 * or the moment the API answers `support_grant_ended`.
 *
 * Not authorization: the server checks the grant on every request (expiry,
 * revocation, MFA). A browser that cannot store it (private mode, a blocked
 * storage) simply has no grant open; every read and write is wrapped.
 */
export interface OpenSupportGrant {
  id: string;
  code: string;
  tenantId: string;
  workspaceId: string;
  resourceType: string;
  resourceId: string | null;
  scopeSetKey: string;
  /** The scopes stamped on the grant: what the server lets a request under it do. */
  scopes: string[];
  /** ISO instant, or null for a grant with no end the server reported. */
  expiresAt: string | null;
}

const KEY = "dw.support.grant";
const MFA_KEY = "dw.support.mfa_required";
const EVENT = "dw-support-grant";

function isGrant(value: unknown): value is OpenSupportGrant {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  const text = (key: string) => typeof v[key] === "string" && v[key] !== "";
  return (
    text("id") &&
    text("code") &&
    text("tenantId") &&
    text("workspaceId") &&
    text("resourceType") &&
    text("scopeSetKey") &&
    Array.isArray(v.scopes) &&
    (v.scopes as unknown[]).every((s) => typeof s === "string") &&
    (v.resourceId === null || typeof v.resourceId === "string") &&
    (v.expiresAt === null || typeof v.expiresAt === "string")
  );
}

// The last raw value read and what it parsed to, so `useSyncExternalStore`
// gets the same object back while nothing changed.
let cachedRaw: string | null = null;
let cachedGrant: OpenSupportGrant | null = null;

/** The open grant, or null (none, unreadable, or storage unavailable). */
export function openSupportGrant(): OpenSupportGrant | null {
  if (typeof window === "undefined") return null;
  let raw: string | null;
  try {
    raw = window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
  if (raw === cachedRaw) return cachedGrant;
  cachedRaw = raw;
  cachedGrant = null;
  if (raw) {
    try {
      const parsed: unknown = JSON.parse(raw);
      cachedGrant = isGrant(parsed) ? parsed : null;
    } catch {
      cachedGrant = null;
    }
  }
  return cachedGrant;
}

function announce(): void {
  try {
    window.dispatchEvent(new Event(EVENT));
  } catch {
    // no window events (a test environment without them): nothing listens
  }
}

/** Open ``grant``: from now on every request is made under it. */
export function startSupportGrant(grant: OpenSupportGrant): void {
  try {
    window.sessionStorage.removeItem(MFA_KEY);
    window.sessionStorage.setItem(KEY, JSON.stringify(grant));
  } catch {
    // storage refused: no grant is open, and the requests say so
  }
  announce();
}

/**
 * Close the open grant ("Thoát quyền hỗ trợ", or the server ended it). With
 * ``mfaRequired`` the server refused the sign-in itself (no second factor):
 * /support then shows why instead of the list.
 */
export function endSupportGrant({
  mfaRequired = false,
}: { mfaRequired?: boolean } = {}): void {
  try {
    window.sessionStorage.removeItem(KEY);
    if (mfaRequired) window.sessionStorage.setItem(MFA_KEY, "1");
  } catch {
    // nothing stored, or storage refused: nothing open either way
  }
  announce();
}

/** Whether a request under a grant was refused for want of a second factor. */
export function supportMfaRequired(): boolean {
  try {
    return window.sessionStorage.getItem(MFA_KEY) === "1";
  } catch {
    return false;
  }
}

/** Forget the refusal (the person signs in again, or opens another grant). */
export function clearSupportMfaRequired(): void {
  try {
    window.sessionStorage.removeItem(MFA_KEY);
  } catch {
    // storage refused: nothing was kept
  }
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/**
 * The grant open in this tab, or null: what a context reads to hide its own
 * actions while a support staff member works under a grant.
 */
export function useSupportGrant(): OpenSupportGrant | null {
  return useSyncExternalStore(subscribe, openSupportGrant, () => null);
}

/** The error code a request under an ended grant is refused with (ticket 02). */
export const SUPPORT_GRANT_ENDED = "support_grant_ended";
/** A token without a second factor, refused for a support context. */
export const SUPPORT_MFA_REQUIRED = "support_mfa_required";
export const SUPPORT_GRANT_HEADER = "X-DW-Support-Grant";
