"use client";

import Link from "next/link";
import type { PageHeaderCrumb } from "@dw/ui";

/**
 * A Sales page's breadcrumb: the context, then each level down to the page;
 * every level but the page itself is a link. "Sales" leads to the home page,
 * which sends someone who works cases to "Việc cần làm" and shows anyone else
 * the pages they can open: leadership and IT are refused /sales itself.
 */
export function salesCrumbs(
  ...levels: (string | { title: string; href: string })[]
): PageHeaderCrumb[] {
  return [
    { title: <Link href="/">Sales</Link> },
    ...levels.map((level) =>
      typeof level === "string"
        ? { title: level }
        : { title: <Link href={level.href}>{level.title}</Link> },
    ),
  ];
}
