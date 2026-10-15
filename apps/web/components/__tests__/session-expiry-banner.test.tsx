import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { App } from "antd";
import {
  markSessionEnded,
  sessionPhase,
  tokenExpiry,
  WARN_BEFORE_MS,
} from "../../lib/session-expiry";

const extendSession = vi.fn<() => Promise<boolean>>();
const reauthenticate = vi.fn();
let sessionExpiresAt: number | null = null;
vi.mock("../../lib/auth/auth-context", () => ({
  useAuth: () => ({ sessionExpiresAt, extendSession, reauthenticate }),
}));

import { SessionExpiryBanner } from "../session-expiry-banner";

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
});

afterEach(() => {
  cleanup();
  extendSession.mockReset();
  reauthenticate.mockReset();
});

const MINUTE = 60_000;

function page() {
  return render(
    <App>
      <SessionExpiryBanner />
      <textarea aria-label="Nhận xét" defaultValue="đang gõ dở" />
    </App>,
  );
}

describe("sessionPhase", () => {
  it("warns only inside the last minutes, and ends at the end", () => {
    const now = 1_000_000;
    expect(sessionPhase(null, now, false)).toBe("fresh");
    expect(sessionPhase(now + WARN_BEFORE_MS + 1, now, false)).toBe("fresh");
    expect(sessionPhase(now + WARN_BEFORE_MS, now, false)).toBe("ending");
    expect(sessionPhase(now, now, false)).toBe("ended");
    expect(sessionPhase(null, now, true)).toBe("ended");
  });

  it("reads a token's exp, and nothing from a token without one", () => {
    const body = btoa(JSON.stringify({ sub: "x", exp: 1_800_000_000 }));
    expect(tokenExpiry(`h.${body}.s`)).toBe(1_800_000_000_000);
    expect(tokenExpiry(`h.${btoa("{}")}.s`)).toBeNull();
    expect(tokenExpiry("not-a-jwt")).toBeNull();
    expect(tokenExpiry(null)).toBeNull();
  });
});

describe("the session expiry banner (ui-quality §4, WCAG 2.2.1)", () => {
  it("says nothing while the end is far off", () => {
    sessionExpiresAt = Date.now() + 60 * MINUTE;
    page();
    expect(screen.queryByText(/Phiên đăng nhập/)).toBeNull();
  });

  it("warns ahead and lets the person stay signed in", async () => {
    sessionExpiresAt = Date.now() + 3 * MINUTE + 30_000;
    extendSession.mockResolvedValue(true);
    page();

    expect(screen.getByText(/Phiên đăng nhập sẽ hết sau 3 phút/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Tiếp tục phiên" }));
    await waitFor(() => expect(extendSession).toHaveBeenCalledTimes(1));
    expect(screen.queryByText(/Không gia hạn thêm được nữa/)).toBeNull();
    expect(reauthenticate).not.toHaveBeenCalled();
  });

  it("says when the session cannot be extended, and offers to sign in again", async () => {
    sessionExpiresAt = Date.now() + 2 * MINUTE;
    extendSession.mockResolvedValue(false);
    page();

    fireEvent.click(screen.getByRole("button", { name: "Tiếp tục phiên" }));
    await screen.findByText(/Không gia hạn thêm được nữa/);
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập lại" }));
    expect(reauthenticate).toHaveBeenCalledTimes(1);
  });

  it("once ended, keeps the page and what was typed until the person signs in again", () => {
    sessionExpiresAt = Date.now() - 1_000;
    page();

    expect(screen.getByText(/Phiên đăng nhập đã hết/)).toBeTruthy();
    expect(
      (screen.getByLabelText("Nhận xét") as HTMLTextAreaElement).value,
    ).toBe("đang gõ dở");
    expect(reauthenticate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Đăng nhập lại" }));
    expect(reauthenticate).toHaveBeenCalledTimes(1);
  });

  // Last: the ended mark is module state, as it is for a page load.
  it("shows the ended state when a request found the session dead", () => {
    sessionExpiresAt = Date.now() + 60 * MINUTE;
    page();
    expect(screen.queryByText(/Phiên đăng nhập đã hết/)).toBeNull();
    act(() => markSessionEnded());
    expect(screen.getByText(/Phiên đăng nhập đã hết/)).toBeTruthy();
  });
});
