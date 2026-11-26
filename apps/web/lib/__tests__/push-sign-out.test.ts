import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Sales ticket 78: signing out ends this device's pushes. The browser's
 * subscription is ended before anything leaves the device, so a page that
 * unloads before the server answers is off all the same, and the server is
 * waited for only so long. The browser's push surface and the API client are
 * fakes with the shape `lib/push.ts` uses.
 */

const order: string[] = [];
const deletePushSubscription = vi.fn<(endpoint: string) => Promise<void>>();

vi.mock("../session", () => ({
  apiClient: () => ({ deletePushSubscription }),
}));

function subscription(unsubscribe: () => Promise<boolean>) {
  return {
    endpoint: "https://push.example/abc",
    unsubscribe: vi.fn(unsubscribe),
  };
}

function browser(sub: ReturnType<typeof subscription> | null) {
  const registration = {
    pushManager: { getSubscription: vi.fn(async () => sub) },
  };
  vi.stubGlobal("PushManager", function PushManager() {});
  vi.stubGlobal("Notification", { permission: "granted" });
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: {
      getRegistration: vi.fn(async () => registration),
      register: vi.fn(async () => registration),
      controller: null,
    },
  });
}

beforeEach(() => {
  order.length = 0;
  deletePushSubscription.mockReset();
  deletePushSubscription.mockImplementation(async () => {
    order.push("server");
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete (navigator as { serviceWorker?: unknown }).serviceWorker;
  vi.useRealTimers();
});

describe("ending pushes at sign-out", () => {
  it("unsubscribes the device first, then has the server forget it", async () => {
    const sub = subscription(async () => {
      order.push("device");
      return true;
    });
    browser(sub);
    const { endPushOnSignOut } = await import("../push");

    await endPushOnSignOut();

    expect(order).toEqual(["device", "server"]);
    expect(deletePushSubscription).toHaveBeenCalledWith(
      "https://push.example/abc",
    );
  });

  it("is off on the device when the server refuses", async () => {
    const sub = subscription(async () => true);
    browser(sub);
    deletePushSubscription.mockRejectedValue(new Error("offline"));
    const { endPushOnSignOut } = await import("../push");

    await expect(endPushOnSignOut()).resolves.toBeUndefined();
    expect(sub.unsubscribe).toHaveBeenCalledOnce();
  });

  it("waits for a server that never answers only so long, already unsubscribed", async () => {
    vi.useFakeTimers();
    const sub = subscription(async () => true);
    browser(sub);
    deletePushSubscription.mockImplementation(
      () => new Promise<void>(() => {}),
    );
    const { endPushOnSignOut } = await import("../push");

    let done = false;
    const ending = endPushOnSignOut(2000).then(() => {
      done = true;
    });
    await vi.advanceTimersByTimeAsync(1999);
    expect(done).toBe(false);
    expect(sub.unsubscribe).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1);
    await ending;
    expect(done).toBe(true);
  });

  it("does nothing where this browser has no push", async () => {
    const { endPushOnSignOut } = await import("../push");

    await endPushOnSignOut();

    expect(deletePushSubscription).not.toHaveBeenCalled();
  });

  it("does nothing on a device never subscribed", async () => {
    browser(null);
    const { endPushOnSignOut } = await import("../push");

    await endPushOnSignOut();

    expect(deletePushSubscription).not.toHaveBeenCalled();
  });
});

describe("turning pushes off from the profile", () => {
  it("still has the server forget the device when the browser fails", async () => {
    const sub = subscription(async () => {
      throw new Error("browser refused");
    });
    browser(sub);
    const { turnOff } = await import("../push");

    await expect(turnOff()).rejects.toThrow("browser refused");
    expect(deletePushSubscription).toHaveBeenCalledWith(
      "https://push.example/abc",
    );
  });
});
