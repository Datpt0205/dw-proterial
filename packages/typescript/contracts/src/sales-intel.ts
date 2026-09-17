import { z } from "zod";

/**
 * The Signal tab's shapes, validated at the boundary.
 *
 * Two fields on a package are per reader and never per row - `my_offering_match`
 * and `pref_match`. They are computed on read from the caller's own catalogue
 * and their own preference, so two people looking at the same package see
 * different answers, and neither answer is stored anywhere.
 */

export const tenderPrefMatchSchema = z.object({
  score: z.number().int(),
  reason: z.string().nullable(),
});

/**
 * One service the scorer matched, and how well it fits this package.
 *
 * The name travels with the code because this is rendered as the evidence
 * behind the relevance badge, and `[FDX-042]` on its own tells a reader nothing.
 */
export const offeringMatchSchema = z.object({
  code: z.string(),
  name: z.string(),
  score: z.number().int(),
});

/**
 * One package inside a plan (KHLCNT).
 *
 * This is the whole content of a plan card: the plan's own name is almost always
 * "Kế hoạch lựa chọn nhà thầu năm 2026", so a plan without its lots is a card
 * that says nothing. `lcnt_start_raw` stays the string the portal prints - "Quý
 * III/2026" or "09/2026" - because a quarter has no day and parsing one into a
 * date would put a deadline on screen that nobody published.
 */
export const tenderLotSchema = z.object({
  name: z.string(),
  work_summary: z.string().nullable().optional(),
  price: z.string().nullable().optional(),
  lcnt_start_raw: z.string().nullable().optional(),
  notify_no: z.string().nullable().optional(),
  // The state of the invitation this lot became, when that invitation is not
  // itself in the feed - a lot invited last year falls outside the window, and
  // without this it would read as though it had never gone to market.
  notify_state: z.string().nullable().optional(),
  // Set when the invitation is in this feed, so the screen can navigate to it
  // instead of sending the reader back to the portal.
  tender_id: z.string().nullable().optional(),
  score: z.number().int().nullable().optional(),
  band: z.string().nullable().optional(),
  matched: z.array(z.string()),
  note: z.string().nullable().optional(),
});

export const tenderSchema = z.object({
  id: z.string().uuid(),
  filter_tag: z.string(),
  topic: z.string().nullable(),
  source: z.string(),
  is_historical: z.boolean(),
  notify_no: z.string().nullable(),
  plan_no: z.string().nullable(),
  bid_name: z.string(),
  invest_field: z.string().nullable(),
  bid_form: z.string().nullable(),
  process_status: z.string().nullable(),
  bid_state: z.string().nullable(),
  // As published and as parsed. The text is the system of record; the number is
  // null whenever the parse was not certain, so a sort loses a row before a
  // reader is shown a figure nobody published.
  total_value: z.string().nullable(),
  total_value_numeric: z.number().int().nullable(),
  winning_price: z.string().nullable(),
  winner_name: z.string().nullable(),
  currency: z.string(),
  public_date: z.string().nullable(),
  bid_close_date: z.string().nullable(),
  bid_open_date: z.string().nullable(),
  url: z.string().nullable(),
  relevance_score: z.number().int().nullable(),
  // The score as one of `cao` / `trung_binh` / `thap`, decided on the server so
  // a boundary cannot be moved on one side only. Null means unscored, which is
  // "waiting to be assessed" on screen and not a score of zero.
  relevance_band: z.string().nullable().optional(),
  // The evidence behind the badge. Empty means nothing was matched, which is
  // not the same as unscored - `eval_status` is what says which.
  matched_offerings: z.array(offeringMatchSchema),
  relevance_note: z.string().nullable(),
  eval_status: z.string().nullable(),
  // A plan's funding type as the portal labels it. Null on an invitation.
  classification: z.string().nullable().optional(),
  // Still accepting documents as of this request.
  is_open: z.boolean(),
  // Every package inside a plan, including the ones not yet invited. Empty on
  // an invitation.
  lots: z.array(tenderLotSchema),
  // One of `open` / `reviewing` / `expired` / `won`, computed against the time
  // of the request. Null for a plan, which has not reached the market.
  group: z.string().nullable().optional(),
  my_offering_match: z.array(z.string()),
  pref_match: tenderPrefMatchSchema.nullable().optional(),
});

/**
 * The deal a package belongs to.
 *
 * `created` separates the two answers a button needs: it has just done
 * something, or it has found the work already done. Both are successes, and
 * collapsing them makes a second press look like a failure.
 */
export const tenderOpportunitySchema = z.object({
  opportunity_id: z.string(),
  name: z.string(),
  stage: z.string(),
  created: z.boolean(),
});

export const tenderCountsSchema = z.object({
  total: z.number().int(),
  by_source: z.record(z.number().int()),
  by_year: z.record(z.number().int()),
  // Including `khac`, the off-topic packages the default scope hides.
  // Unclassified ones are keyed under "" so the tally adds up to `total`.
  by_topic: z.record(z.number().int()).optional(),
  // Year to subject filter to count, with "all" meaning every year. A matrix
  // rather than a flat tally because the two filters nest: picking 2026 has to
  // make the "CNTT" chip read the count of IT packages in 2026. The client
  // cannot compute it - off-topic packages are not in the payload on the default
  // scope, and one person's preference matches rows another person's does not.
  scopes_by_year: z.record(z.record(z.number().int())),
  // The four bidding-history groups over the scoped set rather than the page, so
  // the numbers beside the chips do not move when a chip is pressed.
  groups: z.record(z.number().int()),
});

/**
 * One band of the relevance scale, as the server labels it.
 *
 * Sent with every response rather than kept as a constant here. The previous
 * system had a copy on each side and they had drifted: the browser cut the top
 * band at 70 while the scoring rubric cut it at 80, so packages showed as less
 * relevant than they had been scored and nothing on screen could reveal it.
 */
export const relevanceBandSchema = z.object({
  id: z.string(),
  label: z.string(),
  min: z.number().int(),
});

/**
 * A scan row as `ScanStatusView` really sends it.
 *
 * This was wrong from the day it was written - it declared `id`, `account_id`
 * and `created_at`, none of which the endpoint returns, and required three
 * counters the endpoint sends as null while a scan is still running. So the
 * Signal tab parsed fine with no scan on file and threw the moment one existed,
 * which is exactly the state a person reaches by pressing the scan button.
 */
export const scanStatusSchema = z.object({
  scan_id: z.string().uuid(),
  mode: z.string(),
  status: z.string(),
  // Null until the scan has counted anything. A running scan has no totals yet.
  found_raw: z.number().int().nullable(),
  kept: z.number().int().nullable(),
  new_count: z.number().int().nullable(),
  error: z.string().nullable(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
});

/**
 * The statuses a scan is still working under.
 *
 * Mirrors `ACTIVE_SCAN_STATUSES` in `dw_sales_intel/application/records.py`, and
 * it lives here rather than in each tab because of the bug it closes: two tabs
 * asked `status === "running"`, and a scan that has just been started is
 * `queued`. So pressing the button enqueued the work, the row came back
 * `queued`, the UI concluded nothing was happening, and switched off both the
 * progress banner and the poll that would have noticed the change. It read as a
 * button that had not worked - people pressed it a second time, by which point
 * the row had turned `running` and the UI finally caught up.
 *
 * A queued scan is running as far as a reader is concerned: they asked for it and
 * it has not finished.
 */
export const ACTIVE_SCAN_STATUSES = ["queued", "running"] as const;

/** Whether this scan row is one the caller is still waiting on. */
export function isScanActive(
  scan: { status: string } | null | undefined,
): boolean {
  return (
    scan != null &&
    (ACTIVE_SCAN_STATUSES as readonly string[]).includes(scan.status)
  );
}

export const tenderListSchema = z.object({
  account_id: z.string().uuid(),
  items: z.array(tenderSchema),
  counts: tenderCountsSchema,
  relevance_bands: z.array(relevanceBandSchema),
  truncated: z.boolean(),
  last_scan: scanStatusSchema.nullable(),
});

/**
 * `coverage` is required beside every ratio, never optional. A win rate over the
 * three packages whose bidders were crawled, shown next to a hundred that were
 * not, is true and reads as a fact about the account.
 */
export const coverageSchema = z.object({
  packages: z.number().int(),
  crawled: z.number().int(),
  decided: z.number().int(),
  ratio: z.number(),
});

/**
 * One competitor across everything the account put out to tender.
 *
 * Field for field against `VendorRowView`. Four of these six were guessed and
 * wrong - `packages` for `entered`, `wins` for `won`, `total_value` for
 * `total_won_value`, and `lost` missing entirely - and the analytics response
 * therefore failed to parse on every call. The tab caught the rejection and
 * rendered nothing, so the panel looked like an account with no competitors
 * rather than a broken schema.
 *
 * `entered` and `won` are counts, `lost` is not `entered - won`: a package
 * whose result is not published is neither.
 */
/**
 * One package in a vendor's history with this account.
 *
 * The row behind the summary line, and the reason expanding is worth a click:
 * `my_price` beside `winning_price` is the price this vendor lost at. Measured
 * on a real account, one bid 55.88bn and lost at 55.06bn - 1.5% apart, and that
 * number exists nowhere else on the screen.
 *
 * `my_price` is null for an uncrawled package and for a two-envelope package
 * whose financial envelope is not open. Never render it as zero.
 */
export const vendorPackageSchema = z.object({
  tender_id: z.string(),
  bid_name: z.string(),
  notify_no: z.string().nullable().optional(),
  budget: z.number().int().nullable().optional(),
  winning_price: z.number().int().nullable().optional(),
  winner_name: z.string().nullable().optional(),
  my_price: z.number().int().nullable().optional(),
  // True won, false lost, null still being decided.
  won: z.boolean().nullable().optional(),
  // False when the row is known only from the record of who won. The parent's
  // win count includes those, so without this the children would be fewer than
  // the number above them and the table would look like it was miscounting.
  crawled: z.boolean(),
});

export const vendorRowSchema = z.object({
  mst: z.string().nullable(),
  name: z.string(),
  entered: z.number().int(),
  won: z.number().int(),
  lost: z.number().int(),
  // Entered, opened, no result published. Apart from `lost` because folding
  // them in depresses a win rate with packages still being decided.
  pending: z.number().int(),
  win_rate: z.number(),
  total_won_value: z.number().int(),
  // The published estimate of what they won. The gap against `total_won_value`
  // is what they discounted to win it.
  total_budget: z.number().int(),
  // What they bid across every package they entered, won or lost. The value
  // column reads against this, and like `entered` it is an under-count until
  // the crawl has covered the account.
  entered_budget: z.number().int(),
  won_value_entered: z.number().int(),
  share_value_pct: z.number(),
  share_count_pct: z.number(),
  history: z.array(vendorPackageSchema),
});

/**
 * The totals every share on a vendor row is a share of.
 *
 * Sent rather than summed here: the shares are computed over every vendor and
 * the table shows ten, so adding up what is on screen builds a smaller base and
 * prints percentages totalling over a hundred.
 */
export const vendorSummarySchema = z.object({
  total_won_value: z.number().int(),
  total_budget: z.number().int(),
  won_packages: z.number().int(),
  vendor_count: z.number().int(),
  // Won, but with no readable award price. Counted in `won_packages` and
  // contributing nothing to the value, which is how far that column is trusted.
  unpriced_packages: z.number().int(),
});

export const competitionStatsSchema = z.object({
  packages_with_roster: z.number().int(),
  single_bidder: z.number().int(),
  single_bidder_pct: z.number(),
  // Null when no package had both a published estimate and a published award.
  // Not zero: "no discount" and "nothing to compute one from" are different.
  average_discount_pct: z.number().nullable(),
});

export const topPackageSchema = z.object({
  tender_id: z.string(),
  bid_name: z.string(),
  total_value: z.number().int().nullable(),
  winning_price: z.number().int().nullable(),
  winner_name: z.string().nullable(),
  // Negative when the award exceeded the estimate. Sent as measured.
  discount_pct: z.number().nullable(),
});

export const tenderAnalyticsSchema = z.object({
  account_id: z.string().uuid(),
  coverage: coverageSchema,
  vendors: z.array(vendorRowSchema),
  vendor_summary: vendorSummarySchema,
  // Named `stats` by the endpoint. It was declared `competition` here, which is
  // a required key the response never carries, so the parse threw before any of
  // the field mismatches above could even matter.
  stats: competitionStatsSchema,
  top_packages: z.array(topPackageSchema),
});

export const portalCompileSchema = z.object({
  id: z.string().uuid(),
  kind: z.string(),
  status: z.string(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
  attempts: z.number().int(),
  error_code: z.string().nullable(),
});

/** The panel never carries the recipe body - see `TenderPortalView` in Python. */
export const tenderPortalSchema = z.object({
  account_id: z.string().uuid(),
  health: z.string().nullable(),
  entry_url: z.string().nullable(),
  url_source: z.string().nullable(),
  mode: z.string().nullable(),
  recipe_version: z.number().int().nullable(),
  has_recipe: z.boolean(),
  consecutive_failures: z.number().int(),
  compiled_at: z.string().nullable(),
  last_ok_at: z.string().nullable(),
  last_run_at: z.string().nullable(),
  last_error_code: z.string().nullable(),
  discovery_confidence: z.number().int().nullable(),
  discovery_reason: z.string().nullable(),
  active_compile: portalCompileSchema.nullable(),
});

export const portalCompileResultSchema = z.object({
  account_id: z.string().uuid(),
  status: z.enum(["queued", "skipped"]),
  kind: z.string(),
  compile_id: z.string().uuid().nullable(),
  reason: z.string().nullable(),
});

export const bidderCrawlSchema = z.object({
  id: z.string().uuid(),
  account_id: z.string().uuid(),
  scope: z.string(),
  limit_packages: z.number().int(),
  status: z.string(),
  cancel_requested: z.boolean(),
  total: z.number().int().nullable(),
  done: z.number().int().nullable(),
  with_data: z.number().int().nullable(),
  requests: z.number().int().nullable(),
  duration_ms: z.number().int().nullable(),
  error: z.string().nullable(),
  created_at: z.string(),
  started_at: z.string().nullable(),
  finished_at: z.string().nullable(),
});

export const startCrawlResultSchema = z.object({
  account_id: z.string().uuid(),
  status: z.enum(["queued", "skipped"]),
  crawl_id: z.string().uuid().nullable(),
  reason: z.string().nullable(),
});

export const tenderPreferenceSchema = z.object({
  account_id: z.string().uuid(),
  pref_text: z.string(),
  match_state: z.string(),
  matched_at: z.string().nullable(),
  match_queued: z.boolean(),
});

export const researchAnswerSchema = z.object({
  run_id: z.string().uuid(),
  question: z.string(),
  answer: z.string(),
});

export type Tender = z.infer<typeof tenderSchema>;
export type TenderLot = z.infer<typeof tenderLotSchema>;
export type OfferingMatch = z.infer<typeof offeringMatchSchema>;
export type RelevanceBand = z.infer<typeof relevanceBandSchema>;
export type TenderList = z.infer<typeof tenderListSchema>;
export type TenderOpportunity = z.infer<typeof tenderOpportunitySchema>;
export type TenderAnalytics = z.infer<typeof tenderAnalyticsSchema>;
export type VendorRow = z.infer<typeof vendorRowSchema>;
export type VendorPackage = z.infer<typeof vendorPackageSchema>;
export type VendorSummary = z.infer<typeof vendorSummarySchema>;
export type TopPackage = z.infer<typeof topPackageSchema>;
export type TenderPortal = z.infer<typeof tenderPortalSchema>;
export type PortalCompileResult = z.infer<typeof portalCompileResultSchema>;
export type BidderCrawl = z.infer<typeof bidderCrawlSchema>;
export type StartCrawlResult = z.infer<typeof startCrawlResultSchema>;
export type TenderPreference = z.infer<typeof tenderPreferenceSchema>;
export type ResearchAnswer = z.infer<typeof researchAnswerSchema>;

// ------------------------------------------------------------- company info --

/**
 * A profile section as the API returns it.
 *
 * `facts` is an open map because the fields a lane writes are declared in
 * Python and differ per section; the closed list lives in `/intel/cards`, which
 * is what the edit form is built from. Validating it here as a fixed shape
 * would mean a lane gaining a field breaks the screen.
 */
export const sourceRefSchema = z.object({
  url: z.string(),
  title: z.string(),
});

export const profileSectionSchema = z.object({
  section_key: z.string(),
  version: z.number().int(),
  narrative: z.string(),
  facts: z.record(z.string(), z.unknown()),
  sources: z.array(sourceRefSchema),
  coverage: z.string(),
  confidence: z.string().nullable().optional(),
  manual_fields: z.array(z.string()),
});

/** One stored figure of one year — a row of the finance mini-table. */
export const financialFactSchema = z.object({
  metric_code: z.string(),
  fiscal_year: z.number().int(),
  fiscal_period: z.string(),
  value_text: z.string(),
});
export type FinancialFact = z.infer<typeof financialFactSchema>;

export const researchProfileSchema = z.object({
  account_id: z.string().uuid(),
  sections: z.array(profileSectionSchema),
  // The server always sends it (empty when nothing is stored); an empty
  // history renders the card exactly as before.
  financial_history: z.array(financialFactSchema),
});

export const sectionReportSchema = z.object({
  account_id: z.string().uuid(),
  section_key: z.string(),
  title: z.string(),
  report: z.string(),
  coverage: z.string(),
  sources: z.array(sourceRefSchema),
});

export const cardSchema = z.object({
  card: z.string(),
  title: z.string(),
  section_key: z.string(),
  editable_fields: z.array(z.string()),
  narrative_editable: z.boolean(),
});

/**
 * One stored decision maker, as the three-tier org list renders them.
 *
 * `birth_year` is a year only, never a date: a row written from a year-only
 * fact stores 1 January in the database, and handing that back as a date
 * would present fabricated precision.
 */
export const accountPersonSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  title: z.string().nullable().optional(),
  level: z.string().nullable().optional(),
  org_tier: z.number().int().nullable().optional(),
  linkedin_url: z.string().nullable().optional(),
  // "male" | "female" as the sources addressed the person; null when unsaid.
  gender: z.string().nullish(),
  education: z.string().nullable().optional(),
  appointed_year: z.number().int().nullable().optional(),
  birth_year: z.number().int().nullable().optional(),
  expertise: z.string().nullable().optional(),
  profile: z.string().nullable().optional(),
  career: z.string().nullable().optional(),
  assessment: z.string().nullable().optional(),
  sources: z.array(z.string()),
});

export const accountPeopleSchema = z.object({
  account_id: z.string().uuid(),
  people: z.array(accountPersonSchema),
});

/** What a research run is about: an account, or (spec 003 US4) a lead. */
export const researchSubjectKindSchema = z.enum(["account", "lead"]);
export type ResearchSubjectKind = z.infer<typeof researchSubjectKindSchema>;
export interface ResearchSubject {
  kind: ResearchSubjectKind;
  id: string;
}

export const researchRunSchema = z.object({
  run_id: z.string().uuid(),
  status: z.string(),
  triggered_by: z.string(),
  subject_kind: researchSubjectKindSchema.optional(),
  round_number: z.number().int(),
  attempts: z.number().int(),
  created_at: z.string(),
  error: z.string().nullable().optional(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
});

export const researchStatusSchema = z.object({
  account_id: z.string().uuid(),
  run: researchRunSchema.nullable(),
  coverage: z.record(z.string(), z.string()),
});

/**
 * Whether a research run is queued unconditionally or only when one is due.
 *
 * The client used to declare `"auto" | "force"` and default to `"auto"`, which
 * is not a value the endpoint accepts - so the Company Info tab's "Nghiên cứu
 * ngay" button 422'd on every click and the tab showed `internal: HTTP 422`.
 * Same shape of bug as the triage buttons: a hand-written literal that nothing
 * checked against the schema.
 */
export const researchPolicySchema = z.enum(["force", "if_needed"]);

/**
 * What `GET /tenders` and `GET /tenders/analytics` may be narrowed to.
 *
 * `all` also lifts the off-topic filter, so it is how somebody reaches the
 * packages the classifier labelled `khac`. `pref` narrows to what this caller's
 * own saved sentence matched.
 *
 * `pref` is a server scope rather than a filter applied here, and has to be:
 * every count beside every chip is computed over the scoped set, so a client
 * that fetched the wide set and narrowed it locally would print counts
 * describing a different set than the rows under them.
 */
export const tenderScopeSchema = z.enum(["all", "cntt", "pref"]);

/** The two sites a package can come from. */
export const tenderSourceSchema = z.enum(["muasamcong", "portal"]);

/** What a bidder crawl may be narrowed to. A different list from the feed's. */
export const crawlScopeSchema = z.enum(["all", "cntt", "pref"]);

export const triggerResearchSchema = z.object({
  run_id: z.string().uuid().nullable(),
  // `skipped` with a reason is a normal answer: a profile that is still fresh
  // does not need re-researching, and saying so is not an error.
  status: z.enum(["queued", "skipped"]),
  reason: z.string().nullable(),
});

export const proposedChangeSchema = z.object({
  action_id: z.string(),
  section_key: z.string(),
  field_path: z.string(),
  before: z.unknown().nullable(),
  after: z.unknown().nullable(),
  reason: z.string(),
});

// -------------------------------------------------------------------- news --

export const newsSignalSchema = z.object({
  id: z.string().uuid(),
  title: z.string().nullable(),
  url: z.string().nullable(),
  source_label: z.string().nullable(),
  published_at: z.string().nullable(),
  published_precision: z.string(),
  first_seen_at: z.string().nullable(),
  // The deterministic score and the parts it was made of. The breakdown is what
  // lets a reader see why a story ranked where it did instead of trusting a
  // number, so it travels with the number rather than behind a second call.
  relevance: z.number().int(),
  score_breakdown: z.record(z.string(), z.unknown()),
  topic: z.string(),
  news_tag: z.string().nullable(),
  sentiment: z.string().nullable(),
  entity_match: z.string(),
  story_safe: z.boolean(),
  snippet: z.string().nullable(),
  talk_track: z.string().nullable(),
  status: z.string(),
});

export const newsEventSchema = z.object({
  id: z.string().uuid(),
  topic: z.string(),
  news_tag: z.string().nullable(),
  event_date: z.string(),
  priority: z.string(),
  impact: z.string().nullable(),
  recommended_action: z.string().nullable(),
  // Which of the four things a salesperson can do this event calls for, in the
  // order the summariser put them, empty when it calls for none. Strings, not
  // `unknown`: the tab filters on them, and `unknown` forced a cast at every
  // use, which is a type check that does nothing.
  action_groups: z.array(z.string()),
  source_count: z.number().int(),
  source_ids: z.array(z.string().uuid()),
});

/**
 * The statuses a person may move a story to.
 *
 * An enum rather than a string because the client used to take any string and
 * the tab passed `"kept"`, which the endpoint rejects - the two triage buttons
 * failed on every click, and nothing in the types said so.
 */
export const triageStatusSchema = z.enum(["read", "saved", "dismissed"]);

/**
 * What pressing a scan button answered.
 *
 * `skipped` with a reason is a normal answer, not an error: a scan was already
 * running, and telling the reader that is the difference between a button that
 * did nothing and a button that is broken.
 */
export const triggerScanResultSchema = z.object({
  status: z.enum(["queued", "skipped"]),
  scan_id: z.string().uuid().nullable(),
  reason: z.string().nullable(),
});

export const newsFeedSchema = z.object({
  account_id: z.string().uuid(),
  signals: z.array(newsSignalSchema),
  events: z.array(newsEventSchema),
  // The page the social half of a scan reads, and when a read last worked
  // against it. On the feed rather than fetched separately because it is the
  // one input to this tab a person can be wrong about, and being wrong is
  // invisible: the scraper answers 200 with an "unavailable" note for a URL
  // that is not a company page, so "this company posts nothing" and "we are
  // pointed at the wrong page" look identical in a count.
  facebook_url: z.string().nullable().optional(),
  facebook_url_confirmed_at: z.string().nullable().optional(),
  last_scan: scanStatusSchema.nullable(),
});

/** The page now on file, after a person corrected it. */
export const facebookUrlSchema = z.object({
  account_id: z.string().uuid(),
  facebook_url: z.string(),
});

export type SourceRef = z.infer<typeof sourceRefSchema>;
export type ProfileSection = z.infer<typeof profileSectionSchema>;
export type ResearchProfile = z.infer<typeof researchProfileSchema>;
export type SectionReport = z.infer<typeof sectionReportSchema>;
export type IntelCard = z.infer<typeof cardSchema>;
export type ResearchStatus = z.infer<typeof researchStatusSchema>;
export type AccountPerson = z.infer<typeof accountPersonSchema>;
export type AccountPeople = z.infer<typeof accountPeopleSchema>;
export type ResearchPolicy = z.infer<typeof researchPolicySchema>;
export type TenderScope = z.infer<typeof tenderScopeSchema>;
export type CrawlScope = z.infer<typeof crawlScopeSchema>;
export type TenderSource = z.infer<typeof tenderSourceSchema>;
export type TriggerResearch = z.infer<typeof triggerResearchSchema>;
export type ProposedChange = z.infer<typeof proposedChangeSchema>;
export type TriageStatus = z.infer<typeof triageStatusSchema>;
export type TriggerScanResult = z.infer<typeof triggerScanResultSchema>;
export type NewsSignal = z.infer<typeof newsSignalSchema>;
export type NewsEvent = z.infer<typeof newsEventSchema>;
export type NewsFeed = z.infer<typeof newsFeedSchema>;
export type FacebookUrl = z.infer<typeof facebookUrlSchema>;
