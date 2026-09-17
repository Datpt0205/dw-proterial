import { z } from "zod";

// ---- IT spending tab (per-account) ----------------------------------------

/**
 * The three stages a row is in (0149): Đã chi tiêu (a winner or a contract),
 * Đang ra thầu (invited, no winner yet), Đang trong kế hoạch (a KHLCNT lot
 * nobody has invited).
 */
export const spendingPhaseSchema = z.enum(["invested", "bidding", "planned"]);
export type SpendingPhase = z.infer<typeof spendingPhaseSchema>;

/** A person types what was bought or what is planned; the bidding stage is the portal's. */
export const manualSpendingPhaseSchema = z.enum(["invested", "planned"]);

export const spendingStatusSchema = z.enum([
  "proposed",
  "official",
  "rejected",
  "merged",
]);
export type SpendingStatus = z.infer<typeof spendingStatusSchema>;

export const spendingSourceKindSchema = z.enum([
  "tender",
  "khlcnt",
  "news",
  "document",
  "manual",
]);
export type SpendingSourceKind = z.infer<typeof spendingSourceKindSchema>;

export const spendingItemSchema = z.object({
  id: z.string().uuid(),
  phase: spendingPhaseSchema,
  item_name: z.string(),
  /** The model's clean name (0109); null until asked — show item_name then. */
  display_name: z.string().nullish(),
  category: z.string().nullish(),
  /** Which shelf the tab files it under; null until the model has been asked. */
  group: z.string().nullish(),
  vendor: z.string().nullish(),
  year: z.number().int().nullish(),
  quarter: z.string().nullish(),
  amount_text: z.string().nullish(),
  amount_numeric: z.number().nullish(),
  currency: z.string().nullish(),
  status: spendingStatusSchema,
  source_kind: spendingSourceKindSchema,
  source_ref: z.string().nullish(),
  source_url: z.string().nullish(),
  evidence: z.string().nullish(),
  provenance: z.string(),
  updated_at: z.string(),
  /** Records folded into this row: {kind, ref, url, quote, item_name}. */
  extra_sources: z.array(z.record(z.string(), z.unknown())),
  /** A pending row: the existing row the duplicate check says it repeats. */
  duplicate_of: z.string().uuid().nullish(),
});
export type SpendingItem = z.infer<typeof spendingItemSchema>;

export const spendingReviewActionSchema = z.enum([
  "approve",
  "reject",
  "merge",
]);
export type SpendingReviewAction = z.infer<typeof spendingReviewActionSchema>;

export const spendingGroupSchema = z.object({
  key: z.string(),
  label: z.string(),
});
export type SpendingGroup = z.infer<typeof spendingGroupSchema>;

export const spendingOverviewSchema = z.object({
  items: z.array(spendingItemSchema),
  /** The shelves in display order — the server's vocabulary, not a copy. */
  groups: z.array(spendingGroupSchema),
});
export type SpendingOverview = z.infer<typeof spendingOverviewSchema>;

export const spendingRefreshResultSchema = z.object({
  invested: z.number().int(),
  planned: z.number().int(),
  bidding: z.number().int(),
  grouped: z.number().int(),
  /** Uploaded documents read this click, and how many wait for the next. */
  documents_read: z.number().int(),
  documents_waiting: z.number().int(),
});
export type SpendingRefreshResult = z.infer<typeof spendingRefreshResultSchema>;

/** What a refresh would find, probed for free — no model call behind it. */
export const spendingStalenessSchema = z.object({
  new_rows: z.number().int(),
  documents_waiting: z.number().int(),
  /** Rows on the table whose package moved on: a new portal step, state, winner or price. */
  changed_rows: z.number().int(),
});
export type SpendingStaleness = z.infer<typeof spendingStalenessSchema>;

export const manualSpendingRowSchema = z.object({
  phase: manualSpendingPhaseSchema,
  item_name: z.string().min(1),
  category: z.string().nullish(),
  vendor: z.string().nullish(),
  year: z.number().int().nullish(),
  quarter: z.string().nullish(),
  amount_text: z.string().nullish(),
  note: z.string().nullish(),
});
export type ManualSpendingRow = z.infer<typeof manualSpendingRowSchema>;

// ---- what-to-sell analysis -------------------------------------------------

export const sellCitationSchema = z.object({
  kind: z.enum(["spending", "profile"]),
  ref: z.string(),
  quote: z.string(),
});
export type SellCitation = z.infer<typeof sellCitationSchema>;

export const sellIdeaSchema = z.object({
  title: z.string(),
  rationale: z.string(),
  next_step: z.string(),
  confidence: z.enum(["low", "medium", "high"]),
  citations: z.array(sellCitationSchema),
});
export type SellIdea = z.infer<typeof sellIdeaSchema>;

export const sellRecommendationSchema = z.object({
  id: z.string().uuid(),
  summary: z.string(),
  items: z.array(sellIdeaSchema),
  created_at: z.string(),
  prompt_version: z.string(),
  /** The seller's own ask this analysis answered; null = the full table. */
  intent: z.string().nullish(),
});
export type SellRecommendation = z.infer<typeof sellRecommendationSchema>;
