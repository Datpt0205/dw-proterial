"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Bell, CheckCheck } from "lucide-react";
import type { AppNotification, Inbox } from "@dw/contracts";
import { formatDateTime } from "../lib/dates";
import { apiClient } from "../lib/session";

// How often the badge checks for something new while the app is open.
const POLL_MS = 60_000;

/** An app-relative path only; the database already refuses anything else,
 * and this refuses it again before navigating. */
function internalPath(link: string | null): string | null {
  return link && link.startsWith("/") && !link.startsWith("//") ? link : null;
}

export function NotificationBell() {
  const router = useRouter();
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [open, setOpen] = useState(false);
  const panel = useRef<HTMLDivElement>(null);

  const load = useCallback((signal?: AbortSignal) => {
    apiClient()
      .listNotifications(signal)
      .then(setInbox)
      .catch(() => {
        // A failed poll leaves the last inbox shown; the next one retries.
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    const timer = window.setInterval(() => load(), POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (panel.current && !panel.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const follow = async (item: AppNotification) => {
    setOpen(false);
    if (item.read_at === null) {
      await apiClient()
        .markNotificationRead(item.id)
        .catch(() => undefined);
      load();
    }
    const path = internalPath(item.link);
    if (path) router.push(path);
  };

  const readAll = async () => {
    await apiClient()
      .markAllNotificationsRead()
      .catch(() => undefined);
    load();
  };

  const unread = inbox?.unread ?? 0;

  return (
    <div className="relative" ref={panel}>
      <button
        type="button"
        aria-label={
          unread ? `Notifications, ${unread} unread` : "Notifications"
        }
        onClick={() => setOpen((value) => !value)}
        className="relative flex size-10 items-center justify-center rounded-xl border bg-white text-foreground shadow-sm"
      >
        <Bell className="size-5" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 min-w-5 rounded-full bg-destructive px-1 text-center text-xs font-semibold text-destructive-foreground">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-80 max-w-[90vw] rounded-xl border bg-white shadow-lg">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <span className="text-sm font-semibold">Notifications</span>
            {unread > 0 && (
              <button
                type="button"
                onClick={() => void readAll()}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                <CheckCheck className="size-3.5" /> Mark all read
              </button>
            )}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {(inbox?.items ?? []).length === 0 ? (
              <li className="px-3 py-6 text-center text-sm text-muted-foreground">
                Nothing yet.
              </li>
            ) : (
              inbox?.items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => void follow(item)}
                    className={`block w-full border-b px-3 py-2 text-left text-sm last:border-b-0 hover:bg-muted ${
                      item.read_at === null ? "bg-primary/5" : ""
                    }`}
                  >
                    <span className="block font-medium">{item.title}</span>
                    {item.body && (
                      <span className="block text-xs text-muted-foreground">
                        {item.body}
                      </span>
                    )}
                    <span className="block text-xs text-muted-foreground">
                      {formatDateTime(item.created_at)}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
