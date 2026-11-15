"use client";

import { useSyncExternalStore } from "react";
import type { SalesSchemas, SourceRegion } from "@dw/api-client";

type Anchor = SalesSchemas["SourceAnchor"];
type Order = SalesSchemas["OrderCaseView"];

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

/**
 * The regions the screen expects the server to ask for before prepare and
 * cross-check: the page or sheet the PO number was read on, and every one
 * holding a value that is uncertain or typed by hand. The server's rule
 * (`required_regions`) is the owner; when it asks for more, its 409 names it.
 */
export function expectedRegions(order: Order): SourceRegion[] {
  const regions = new Map<string, SourceRegion>();
  const add = (anchor: Anchor | null | undefined) => {
    const region = anchorRegion(anchor);
    if (region) regions.set(JSON.stringify(region), region);
  };
  add(order.header_anchors.po_no);
  for (const flag of order.header_flags) add(order.header_anchors[flag.field]);
  for (const line of order.lines) {
    for (const [field, state] of Object.entries(line.value_states))
      if (state === "uncertain" || state === "hand_entered")
        add(line.anchors[field]);
    for (const flag of line.flags) add(line.anchors[flag.field]);
  }
  return [...regions.values()];
}

/**
 * What of an order's source this browser has not opened yet for its version:
 * the regions, and each in words. A PO written in the mail (AI item 4) has
 * one source, the mail's text. The order page and the work list's inline
 * decision (ticket 48) both read it, so "Chưa mở nguồn" says one thing.
 */
export function unopenedSources(order: Order): {
  regions: SourceRegion[];
  labels: string[];
} {
  if (order.attachment_id === null)
    return {
      regions: [],
      labels: wasMailServed(order.case_id, order.case_version)
        ? []
        : ["nội dung thư"],
    };
  const regions = expectedRegions(order).filter(
    (r) => !wasServed(order.case_id, order.case_version, r),
  );
  return { regions, labels: regions.map(regionLabel) };
}
