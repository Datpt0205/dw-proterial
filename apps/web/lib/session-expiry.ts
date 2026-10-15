"use client";

import { useSyncExternalStore } from "react";

/**
 * When the sign-in ends, and what the shell says about it (ui-quality §4,
 * WCAG 2.2.1): a warning a few minutes ahead with a way to stay signed in,
 * and, once it has ended, a banner with the way back that the person presses
 * when they are ready. Nothing here navigates on its own, because a page
 * that leaves by itself takes what was being typed with it.
 */

/** How long before the end the warning shows. */
export const WARN_BEFORE_MS = 5 * 60_000;

export type SessionPhase = "fresh" | "ending" | "ended";

/** Where the session stands at `now`; no known end is never a warning. */
export function sessionPhase(
  expiresAt: number | null,
  now: number,
  ended: boolean,
): SessionPhase {
  if (ended || (expiresAt !== null && now >= expiresAt)) return "ended";
  if (expiresAt !== null && expiresAt - now <= WARN_BEFORE_MS) return "ending";
  return "fresh";
}

/** The `exp` a JWT carries, in milliseconds; null when it carries none. */
export function tokenExpiry(token: string | null | undefined): number | null {
  const payload = token?.split(".")[1];
  if (!payload) return null;
  try {
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const exp = (JSON.parse(json) as { exp?: unknown }).exp;
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
}

// The one record that the session has ended, whoever found out first: the
// token refresh that failed, or a request that carried a token and was
// answered 401.
let ended = false;
const listeners = new Set<() => void>();

export function markSessionEnded(): void {
  if (ended) return;
  ended = true;
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useSessionEnded(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => ended,
    () => false,
  );
}
