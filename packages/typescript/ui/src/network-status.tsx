"use client";

import { useSyncExternalStore } from "react";
import { Alert } from "antd";

/**
 * Whether the browser has a network, detected once for every screen
 * (ui-quality §4): the shell draws the banner from it, and a screen reads the
 * same hook to disable its mutations. `navigator.onLine` is the browser's own
 * answer and its `online`/`offline` events the only signal; a request that
 * fails while it still says online is the region's offline state instead
 * (`toRegionError`).
 */
function subscribe(onChange: () => void): () => void {
  window.addEventListener("online", onChange);
  window.addEventListener("offline", onChange);
  return () => {
    window.removeEventListener("online", onChange);
    window.removeEventListener("offline", onChange);
  };
}

export function useOnline(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => navigator.onLine,
    // The server render has no network to ask about: it draws online.
    () => true,
  );
}

/** Why a mutation is disabled while offline, for its tooltip. */
export const OFFLINE_REASON =
  "Đang mất kết nối mạng: thao tác này mở lại khi có mạng.";

/** The shell's strip while offline; nothing while online. */
export function OfflineBanner() {
  const online = useOnline();
  if (online) return null;
  return (
    <Alert
      banner
      type="warning"
      showIcon
      role="status"
      title="Mất kết nối mạng. Các thao tác thay đổi dữ liệu tạm khóa tới khi có mạng lại; những gì bạn đã nhập vẫn còn trên trang."
    />
  );
}
