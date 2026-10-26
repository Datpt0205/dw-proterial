"use client";

import { useCallback, useLayoutEffect, useState } from "react";
import { theme } from "antd";

/** Room kept under the region, so its edge never sits on the window's. */
const BOTTOM_GAP = 24;

/**
 * The height that lets a long list scroll inside its own region instead of
 * growing the page (Đạt, 2026-10-26: "chỉ scroll trong đó thôi"): from the
 * region's top to the bottom of the window, less what its table draws above
 * and below the rows (the header row and the footer saying where the list
 * stands), never under `minPx`.
 *
 * For an antd `Table`, pass `ref={tableRef}` and `scroll={{ y }}`; for
 * any other region, set its `height` to `y` with `overflow: auto`. Below
 * antd's `md` (the theme's `screenMD`, the one owner of breakpoints) `y` is
 * undefined: on a phone one page scroll beats a scroll inside a scroll.
 *
 * The top is measured from the document, not the viewport, so scrolling the
 * page does not change the answer; anything above the region resizing (a
 * banner, a filter row wrapping) is caught by observing the body. `ref` is a
 * callback, so a region that mounts after a loading state is measured too.
 */
export function useFillHeight<T extends HTMLElement = HTMLDivElement>(
  minPx = 280,
) {
  const [el, ref] = useState<T | null>(null);
  const { token } = theme.useToken();
  const [y, setY] = useState<number | undefined>(undefined);

  useLayoutEffect(() => {
    if (!el) return;
    const measure = () => {
      if (window.innerWidth < token.screenMD) {
        setY(undefined);
        return;
      }
      const top = el.getBoundingClientRect().top + window.scrollY;
      const height = (selector: string) =>
        el.querySelector(selector)?.getBoundingClientRect().height ?? 0;
      const above = height(".ant-table-header") || height(".ant-table-thead");
      const below = height(".ant-table-footer");
      const next = Math.max(
        minPx,
        Math.floor(window.innerHeight - top - above - below - BOTTOM_GAP),
      );
      setY((prev) => (prev === next ? prev : next));
    };
    measure();
    // jsdom has none; there the window's resize event is all there is.
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(measure);
    observer?.observe(document.body);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [el, minPx, token.screenMD]);

  // An antd `Table` hands its ref as `{ nativeElement }`. Stable, or React
  // detaches and re-attaches it on every render, re-rendering the table each time.
  const tableRef = useCallback(
    (table: { nativeElement: HTMLElement } | null) =>
      ref((table?.nativeElement as T | undefined) ?? null),
    [],
  );
  return { ref, tableRef, y };
}
