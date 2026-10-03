"use client";

import { useMemo, useSyncExternalStore, type ReactNode } from "react";
import { App, ConfigProvider } from "antd";
import viVN from "antd/locale/vi_VN";
import { appTheme } from "./theme";

const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

function subscribeToReducedMotion(onChange: () => void): () => void {
  if (typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia(REDUCED_MOTION);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia(REDUCED_MOTION).matches
  );
}

/**
 * The theme, the Vietnamese locale and the feedback holder every screen sits in.
 *
 * `App` is what makes `App.useApp()` work: the `message`, `notification` and
 * `modal` it returns read this theme and `vi_VN`, which the static `message.*`
 * cannot. With reduced motion asked for, the theme turns antd's motion off,
 * beside the rule in `globals.css` that stops every other transition.
 */
export function UiProvider({ children }: { children: ReactNode }) {
  const reducedMotion = useSyncExternalStore(
    subscribeToReducedMotion,
    prefersReducedMotion,
    () => false,
  );
  const themeConfig = useMemo(
    () =>
      reducedMotion
        ? { ...appTheme, token: { ...appTheme.token, motion: false } }
        : appTheme,
    [reducedMotion],
  );
  return (
    <ConfigProvider theme={themeConfig} locale={viVN}>
      <App>{children}</App>
    </ConfigProvider>
  );
}
