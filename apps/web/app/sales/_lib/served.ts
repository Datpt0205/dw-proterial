"use client";

import { useSyncExternalStore } from "react";
import type { SalesSchemas, SourceRegion } from "@dw/api-client";

type Anchor = SalesSchemas["SourceAnchor"];

/**
 * The pages and sheets this browser was shown, per case version.
 *
 * The server is the owner of "was this person served the source": it records
 * every source it serves and refuses prepare and cross-check without it
 * (409 "chưa mở nguồn", which names what is missing). This only lets a button
 * say "Chưa mở nguồn" before it is pressed. It forgets on reload, and then the
 * person opens the source again, which the server records again.
 */
const served = new Map<string, Set<string>>();
const listeners = new Set<() => void>();
let revision = 0;

function caseKey(caseId: string, caseVersion: number): string {
  return `${caseId}@${caseVersion}`;
}

export function regionKey(region: SourceRegion): string {
  return "page" in region ? `page:${region.page}` : `sheet:${region.sheet}`;
}

// The mail's own text, the one region of a PO written in the mail (AI item 4).
const MAIL = "mail";

function mark(caseId: string, caseVersion: number, region: string) {
  const key = caseKey(caseId, caseVersion);
  const set = served.get(key) ?? new Set<string>();
  if (set.has(region)) return;
  set.add(region);
  served.set(key, set);
  revision += 1;
  listeners.forEach((listener) => listener());
}

export function markServed(
  caseId: string,
  caseVersion: number,
  region: SourceRegion,
) {
  mark(caseId, caseVersion, regionKey(region));
}

export function markMailServed(caseId: string, caseVersion: number) {
  mark(caseId, caseVersion, MAIL);
}

export function wasMailServed(caseId: string, caseVersion: number): boolean {
  return served.get(caseKey(caseId, caseVersion))?.has(MAIL) ?? false;
}

/** Where in the mail's text an anchor points; null for a file's anchor. */
export function mailRange(
  anchor: Anchor | null | undefined,
): { start: number; end: number } | null {
  if (!anchor || anchor.attachment_id !== null || !anchor.chars) return null;
  return { start: anchor.chars.start, end: anchor.chars.end };
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Re-renders when anything is served; read with `wasServed`. */
export function useServedRevision(): number {
  return useSyncExternalStore(
    subscribe,
    () => revision,
    () => 0,
  );
}

export function wasServed(
  caseId: string,
  caseVersion: number,
  region: SourceRegion,
): boolean {
  return (
    served.get(caseKey(caseId, caseVersion))?.has(regionKey(region)) ?? false
  );
}

/** The page or sheet an anchor points into; null for a quote-only anchor. */
export function anchorRegion(
  anchor: Anchor | null | undefined,
): SourceRegion | null {
  if (!anchor) return null;
  if (anchor.page) return { page: anchor.page };
  if (anchor.cell_ref) {
    const bang = anchor.cell_ref.lastIndexOf("!");
    if (bang > 0)
      return { sheet: anchor.cell_ref.slice(0, bang).replace(/^'|'$/g, "") };
  }
  return null;
}

/** "trang 2" / "sheet 注文書", for a sentence. */
export function regionLabel(region: SourceRegion): string {
  return "page" in region ? `trang ${region.page}` : `sheet ${region.sheet}`;
}
