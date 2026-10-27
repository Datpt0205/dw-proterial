"use client";

import Link from "next/link";
import { Button } from "antd";
import { RegionState, stateForError } from "@dw/ui";
import { toRegionError } from "../lib/error-message";

/**
 * A region that failed to load, drawn by the shared `RegionState` from the
 * server's code: a 403 reads as "no access", a 404 as "not found", a change
 * under the viewer offers a reload, and only a real failure offers a retry
 * with its request id.
 */
export function LoadError({
  error,
  onRetry,
  compact,
}: {
  error: unknown;
  onRetry?: () => void;
  compact?: boolean;
}) {
  const state = stateForError(toRegionError(error));
  const retry = !onRetry ? undefined : state.kind === "conflict" ? (
    <Button type="primary" onClick={onRetry}>
      Tải lại
    </Button>
  ) : state.kind === "error" || state.kind === "offline" ? (
    <Button onClick={onRetry}>Thử lại</Button>
  ) : state.kind === "forbidden" ? (
    // Why, then where to go: the home page lists what the viewer can open.
    <Link href="/">Về trang chính</Link>
  ) : undefined;
  return (
    <RegionState
      kind={state.kind}
      description={
        state.kind === "forbidden"
          ? `${state.message} Nếu bạn cần mục này, nhờ quản trị hệ thống cấp quyền.`
          : state.message
      }
      requestId={state.requestId}
      action={retry}
      compact={compact}
    />
  );
}
