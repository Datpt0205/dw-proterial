"use client";

import { useState } from "react";
import { Globe } from "lucide-react";

/** The bare hostname of a URL, or "" when it does not parse. */
export function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

/**
 * A site's own icon, or the globe.
 *
 * Fetched from the site itself rather than through a favicon service: the
 * reader is already being shown these pages, so asking a third party which
 * domains they are would be the only thing here that leaves the building. A
 * site with no `/favicon.ico` falls back rather than showing a broken image.
 *
 * Shared by the AI panel's research steps and the Company Info activity
 * ticker — one look for "the AI read this site" everywhere.
 */
export function SourceIcon({ url }: { url: string }) {
  const [failed, setFailed] = useState(false);
  const host = hostOf(url);
  if (failed || !host) {
    return <Globe className="size-3.5 shrink-0 text-muted-foreground/60" />;
  }
  return (
    // A 14px favicon per host, thrown away with the row. `next/image` would
    // want every host declared in `remotePatterns`, and the hosts here are
    // whatever the model happened to read.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={`https://${host}/favicon.ico`}
      alt=""
      width={14}
      height={14}
      className="size-3.5 shrink-0 rounded-[2px]"
      onError={() => setFailed(true)}
    />
  );
}
