/*
 * The portal's service worker (Sales ticket 48): Web Push and the app badge,
 * nothing else. It caches no page and intercepts no request, so the portal
 * behaves exactly as without it, offline included.
 *
 * A push carries five fields (`dw_sales.application.followups.PushNotice`):
 * title, body, url, count, tag. The title and body are the kind of work and
 * at most a case number; the url is an app path, opened on tap; count adds to
 * the badge. Anything else in a payload is ignored.
 *
 * Written by hand, no library (the ticket's decision): it is about a hundred
 * lines and every line is the platform's own API.
 */

const FEED = "/sales";
const BADGE_CACHE = "dw-badge";
const BADGE_KEY = "/__dw_badge";

/** An app path only: anything else opens the feed. */
function appPath(url) {
  return typeof url === "string" && url.startsWith("/") && !url.startsWith("//")
    ? url
    : FEED;
}

async function readBadge() {
  try {
    const cache = await caches.open(BADGE_CACHE);
    const held = await cache.match(BADGE_KEY);
    const value = held ? Number(await held.text()) : 0;
    return Number.isFinite(value) && value > 0 ? value : 0;
  } catch {
    return 0;
  }
}

async function writeBadge(count) {
  try {
    const cache = await caches.open(BADGE_CACHE);
    await cache.put(BADGE_KEY, new Response(String(count)));
  } catch {
    // No storage: the badge is shown, just not remembered.
  }
  if (count > 0 && self.navigator.setAppBadge) {
    await self.navigator.setAppBadge(count).catch(() => undefined);
  } else if (self.navigator.clearAppBadge) {
    await self.navigator.clearAppBadge().catch(() => undefined);
  }
}

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }
  const title =
    typeof data.title === "string" && data.title ? data.title : "DW";
  const body = typeof data.body === "string" ? data.body : "";
  const tag = typeof data.tag === "string" && data.tag ? data.tag : undefined;
  const count = Number.isInteger(data.count) && data.count > 0 ? data.count : 1;
  event.waitUntil(
    (async () => {
      await writeBadge((await readBadge()) + count);
      // Every push shows a notification: iOS withdraws pushes from an app
      // whose push shows nothing (`userVisibleOnly`).
      await self.registration.showNotification(title, {
        body,
        tag,
        icon: "/icons/icon-192.png",
        badge: "/icons/icon-192.png",
        data: { url: appPath(data.url) },
      });
    })(),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = appPath(event.notification.data && event.notification.data.url);
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      for (const client of windows) {
        if ("focus" in client) {
          await client.focus();
          if ("navigate" in client) await client.navigate(url);
          return;
        }
      }
      await self.clients.openWindow(url);
    })(),
  );
});

// The page says the true count when it has read the person's work.
self.addEventListener("message", (event) => {
  const message = event.data;
  if (message && message.type === "badge" && Number.isInteger(message.count)) {
    event.waitUntil(writeBadge(Math.max(0, message.count)));
  }
});
