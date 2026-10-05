"use client";

import Link from "next/link";
import type { BreadcrumbProps } from "antd";

/**
 * A Sales page's breadcrumb: the context, then each level down to the page;
 * every level but the page itself is a link.
 */
export function salesCrumbs(
  ...levels: (string | { title: string; href: string })[]
): NonNullable<BreadcrumbProps["items"]> {
  return [
    { title: <Link href="/sales">Sales</Link> },
    ...levels.map((level) =>
      typeof level === "string"
        ? { title: level }
        : { title: <Link href={level.href}>{level.title}</Link> },
    ),
  ];
}
