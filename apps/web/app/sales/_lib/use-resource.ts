"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "../../../lib/auth/auth-context";

export interface Resource<T> {
  data: T | null;
  /** True until the first answer (or failure) for the current key. */
  loading: boolean;
  /** What the last attempt failed with; the region draws it (RegionState). */
  error: unknown;
  /** Read again, keeping what is shown until the answer arrives. */
  reload: () => void;
}

/**
 * One read for one region: loading until the first answer, the error kept so
 * the region can tell a 403 from an outage, and a reload that keeps the last
 * data on screen. The key folds in the active workspace, so a switch reads
 * again instead of showing the other workspace's rows.
 *
 * `enabled: false` makes no call at all: a region the viewer's scopes do not
 * reach draws its forbidden state without asking the server for a 403.
 *
 * Unlike `useCachedResource` it raises no toast: an error the person must act
 * on is drawn in the region, never only in a message that disappears
 * (ui-quality §10), and feedback goes through `App.useApp()` (§1).
 */
export function useResource<T>(
  key: string,
  load: () => Promise<T>,
  { enabled = true }: { enabled?: boolean } = {},
): Resource<T> {
  const { active } = useAuth();
  const scopedKey = `${active?.workspaceId ?? "none"}::${key}`;
  const [state, setState] = useState<{
    key: string;
    data: T | null;
    error: unknown;
    loading: boolean;
  }>({ key: scopedKey, data: null, error: null, loading: enabled });
  const [tick, setTick] = useState(0);
  const loadRef = useRef(load);
  loadRef.current = load;

  useEffect(() => {
    if (!enabled) {
      setState({ key: scopedKey, data: null, error: null, loading: false });
      return;
    }
    let cancelled = false;
    setState((previous) =>
      previous.key === scopedKey
        ? { ...previous, loading: previous.data === null }
        : { key: scopedKey, data: null, error: null, loading: true },
    );
    loadRef
      .current()
      .then((data) => {
        if (!cancelled)
          setState({ key: scopedKey, data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (!cancelled)
          setState((previous) => ({
            ...previous,
            key: scopedKey,
            error,
            loading: false,
          }));
      });
    return () => {
      cancelled = true;
    };
  }, [scopedKey, enabled, tick]);

  const reload = useCallback(() => setTick((value) => value + 1), []);
  const current = state.key === scopedKey;
  return {
    data: current ? state.data : null,
    loading: current ? state.loading : enabled,
    error: current ? state.error : null,
    reload,
  };
}
