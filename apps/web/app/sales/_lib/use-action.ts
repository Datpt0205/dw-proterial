"use client";

import { useCallback, useRef, useState } from "react";
import { App } from "antd";

export type ActionResult<T> =
  { ok: true; value: T } | { ok: false; error: unknown };

/**
 * One way every Sales mutation is sent.
 *
 * - **Idempotency** (ui-quality §3): a key is minted once per press of one
 *   action with one payload, reused when the same payload is retried after a
 *   failure, and replaced once the payload changes or the call succeeds. The
 *   API refuses a reused key with a different body.
 * - **Success** is said after the server's 2xx, never before, through
 *   `App.useApp()` (no sonner on Sales pages).
 * - **Failure** is handed back to the caller, which draws it beside the
 *   control: an error the person must act on never lives only in a toast.
 */
export function useAction() {
  const { message } = App.useApp();
  const keys = useRef(new Map<string, { payload: string; key: string }>());
  const [pending, setPending] = useState<string | null>(null);

  const run = useCallback(
    async <T>(
      id: string,
      payload: unknown,
      call: (idempotencyKey: string) => Promise<T>,
      success: string,
    ): Promise<ActionResult<T>> => {
      const body = JSON.stringify(payload ?? null);
      let entry = keys.current.get(id);
      if (!entry || entry.payload !== body) {
        entry = { payload: body, key: crypto.randomUUID() };
        keys.current.set(id, entry);
      }
      setPending(id);
      try {
        const value = await call(entry.key);
        keys.current.delete(id);
        void message.success(success);
        return { ok: true, value };
      } catch (error) {
        return { ok: false, error };
      } finally {
        setPending(null);
      }
    },
    [message],
  );

  return { run, pending };
}
