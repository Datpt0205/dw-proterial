"use client";

import { useRef } from "react";

/**
 * The `Idempotency-Key` a mutation carries (ui-quality §3), one owner for
 * every page that sends one.
 *
 * A key is minted once per press of one action with one payload, reused when
 * the same payload is retried after a failure (so a request that reached the
 * server before the network dropped is answered from its record instead of
 * acting twice), and replaced once the payload changes or the call succeeds:
 * the API refuses a reused key with a different body
 * (`dependencies/idempotency.py`).
 */
export class IdempotencyKeys {
  private readonly keys = new Map<string, { payload: string; key: string }>();

  /** The key for this press of action `id` with this payload. */
  keyFor(id: string, payload: unknown): string {
    const body = JSON.stringify(payload ?? null);
    let entry = this.keys.get(id);
    if (!entry || entry.payload !== body) {
      entry = { payload: body, key: crypto.randomUUID() };
      this.keys.set(id, entry);
    }
    return entry.key;
  }

  /** The action succeeded: its next press is a new request. */
  settle(id: string): void {
    this.keys.delete(id);
  }
}

/** One {@link IdempotencyKeys} for the life of the component. */
export function useIdempotencyKeys(): IdempotencyKeys {
  const keys = useRef<IdempotencyKeys | null>(null);
  keys.current ??= new IdempotencyKeys();
  return keys.current;
}
