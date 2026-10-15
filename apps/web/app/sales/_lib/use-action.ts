"use client";

import { useCallback, useState } from "react";
import { App } from "antd";
import { OFFLINE_REASON, useOnline } from "@dw/ui";
import { useIdempotencyKeys } from "../../../lib/idempotency";

export type ActionResult<T> =
  { ok: true; value: T } | { ok: false; error: unknown };

/**
 * One way every Sales mutation is sent.
 *
 * - **Idempotency** (ui-quality §3): the key comes from
 *   `lib/idempotency.ts`, minted once per press of one action with one
 *   payload, reused on a retry of it, replaced after an edit or a success.
 * - **Success** is said after the server's 2xx, never before, through
 *   `App.useApp()` (no sonner on Sales pages).
 * - **Offline** (ui-quality §4): while the shell says there is no network,
 *   nothing is sent and the press fails with the reason, so a dialog's OK
 *   that no `GuardedButton` disabled is refused in words, not by a fetch.
 * - **Failure** is handed back to the caller, which draws it beside the
 *   control: an error the person must act on never lives only in a toast.
 */
export function useAction() {
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const online = useOnline();
  const [pending, setPending] = useState<string | null>(null);

  const run = useCallback(
    async <T>(
      id: string,
      payload: unknown,
      call: (idempotencyKey: string) => Promise<T>,
      success: string,
    ): Promise<ActionResult<T>> => {
      if (!online) return { ok: false, error: new Error(OFFLINE_REASON) };
      const key = keys.keyFor(id, payload);
      setPending(id);
      try {
        const value = await call(key);
        keys.settle(id);
        void message.success(success);
        return { ok: true, value };
      } catch (error) {
        return { ok: false, error };
      } finally {
        setPending(null);
      }
    },
    [keys, message, online],
  );

  return { run, pending };
}
