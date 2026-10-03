"use client";

import { useMemo, useSyncExternalStore, type ReactNode } from "react";
import { App, ConfigProvider } from "antd";
import viVN from "antd/locale/vi_VN";
import dayjs from "dayjs";
import "dayjs/locale/vi";
import { buildTheme } from "./theme";

// antd's pickers format through dayjs, so its locale is set beside antd's.
dayjs.locale("vi");

const DARK_QUERY = "(prefers-color-scheme: dark)";

function subscribe(onChange: () => void): () => void {
  const query = window.matchMedia(DARK_QUERY);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

const prefersDark = () => window.matchMedia(DARK_QUERY).matches;
// The server cannot see the OS setting: it renders light, and a dark OS
// switches on the first client render.
const onServer = () => false;

/**
 * The antd theme, in light or dark as the OS asks (design v3), with the
 * Vietnamese locale and antd's `App`, whose `App.useApp()` gives `message`,
 * `notification` and `modal` that read this theme.
 */
export function ThemeProvider({
  fontFamily,
  children,
}: {
  /** The family the app loaded; see `buildTheme`. */
  fontFamily: string;
  children: ReactNode;
}) {
  const dark = useSyncExternalStore(subscribe, prefersDark, onServer);
  const themeConfig = useMemo(
    () => buildTheme(dark ? "dark" : "light", fontFamily),
    [dark, fontFamily],
  );
  return (
    <ConfigProvider theme={themeConfig} locale={viVN}>
      <App>{children}</App>
    </ConfigProvider>
  );
}
