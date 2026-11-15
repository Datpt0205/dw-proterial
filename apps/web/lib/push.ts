"use client";

import { apiClient } from "./session";

/**
 * Web Push on this device (Sales ticket 48): the service worker of our own
 * (`public/sw.js`, no library), the subscription the platform keeps for this
 * person in this workspace, and the app badge.
 *
 * iOS (16.4 and later) offers pushes only to the portal installed on the
 * Home Screen and opened from there; in Safari itself `PushManager` does not
 * exist. That is `needs_install`, which the profile explains once.
 */

export type PushSupport = "ready" | "needs_install" | "unsupported";

const WORKER = "/sw.js";

function isIos(): boolean {
  const ua = navigator.userAgent;
  return (
    /iPhone|iPad|iPod/.test(ua) ||
    // iPadOS reports a Mac with a touch screen.
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

function isInstalled(): boolean {
  return (
    window.matchMedia?.("(display-mode: standalone)").matches === true ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

export function pushSupport(): PushSupport {
  if (typeof window === "undefined") return "unsupported";
  const capable =
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window;
  if (capable) return "ready";
  return isIos() && !isInstalled() ? "needs_install" : "unsupported";
}

/** The service worker, registered once per page load; null where none runs. */
export async function registerWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof window === "undefined" || !("serviceWorker" in navigator))
    return null;
  try {
    return await navigator.serviceWorker.register(WORKER, { scope: "/" });
  } catch {
    // An old browser, a private window, a blocked worker: pushes stay off.
    return null;
  }
}

function keyBytes(base64url: string): Uint8Array<ArrayBuffer> {
  const padded = (base64url + "=".repeat((4 - (base64url.length % 4)) % 4))
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  const raw = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) bytes[i] = raw.charCodeAt(i);
  return bytes;
}

function asSaved(subscription: PushSubscription) {
  const json = subscription.toJSON();
  return {
    endpoint: subscription.endpoint,
    keys: { p256dh: json.keys?.p256dh ?? "", auth: json.keys?.auth ?? "" },
  };
}

async function current(): Promise<PushSubscription | null> {
  const registration = await registerWorker();
  return registration ? registration.pushManager.getSubscription() : null;
}

/** Whether this device is subscribed and allowed to show notifications. */
export async function pushIsOn(): Promise<boolean> {
  if (pushSupport() !== "ready" || Notification.permission !== "granted")
    return false;
  return (await current()) !== null;
}

export type TurnOnResult = "on" | "denied" | "off_on_server";

/**
 * Asks the person (the browser's own prompt, on their press), subscribes this
 * device with the deployment's key and hands the subscription to the API.
 */
export async function turnOn(): Promise<TurnOnResult> {
  const key = await apiClient().pushKey();
  if (!key.enabled || !key.public_key) return "off_on_server";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  const registration = await registerWorker();
  if (!registration) return "denied";
  await navigator.serviceWorker.ready;
  const subscription =
    (await registration.pushManager.getSubscription()) ??
    (await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(key.public_key),
    }));
  await apiClient().savePushSubscription(asSaved(subscription));
  return "on";
}

/** Unsubscribes this device, here and on the server. */
export async function turnOff(): Promise<void> {
  const subscription = await current();
  if (!subscription) return;
  await apiClient()
    .deletePushSubscription(subscription.endpoint)
    .catch(() => undefined);
  await subscription.unsubscribe();
}

/**
 * Renews this device's subscription on the server each time the app opens,
 * so one in use is never pruned (`platform.prune_push_subscriptions`, 90
 * days), and one the browser rotated reaches the server. Silent: nothing to
 * renew is nothing to say.
 */
export async function renewPush(): Promise<void> {
  if (pushSupport() !== "ready" || Notification.permission !== "granted")
    return;
  const subscription = await current();
  if (!subscription) return;
  await apiClient()
    .savePushSubscription(asSaved(subscription))
    .catch(() => undefined);
}

/**
 * The app badge (Badging API where the platform has it: the installed app on
 * iOS 16.4+, Chromium on desktop) set to the person's count of work, and the
 * service worker told it, so the next push adds to the right number.
 */
export function showBadge(count: number): void {
  if (typeof navigator === "undefined") return;
  const badging = navigator as Navigator & {
    setAppBadge?: (n?: number) => Promise<void>;
    clearAppBadge?: () => Promise<void>;
  };
  const done =
    count > 0 ? badging.setAppBadge?.(count) : badging.clearAppBadge?.();
  void done?.catch(() => undefined);
  navigator.serviceWorker?.controller?.postMessage({ type: "badge", count });
}
