import {
  accountPeopleSchema,
  bidderCrawlSchema,
  facebookUrlSchema,
  cardSchema,
  newsFeedSchema,
  portalCompileResultSchema,
  researchAnswerSchema,
  researchProfileSchema,
  researchStatusSchema,
  sectionReportSchema,
  startCrawlResultSchema,
  tenderAnalyticsSchema,
  tenderListSchema,
  tenderOpportunitySchema,
  tenderPortalSchema,
  tenderPreferenceSchema,
  triggerScanResultSchema,
  triggerResearchSchema,
  type AccountPeople,
  type BidderCrawl,
  type FacebookUrl,
  type CrawlScope,
  type IntelCard,
  type NewsFeed,
  type PortalCompileResult,
  type ResearchAnswer,
  type ResearchProfile,
  type ResearchPolicy,
  type ResearchStatus,
  type ResearchSubject,
  type SectionReport,
  type StartCrawlResult,
  type TenderAnalytics,
  type TenderList,
  type TenderOpportunity,
  type TenderPortal,
  type TenderPreference,
  type TenderScope,
  type TenderSource,
  type TriageStatus,
  type TriggerScanResult,
  type TriggerResearch,
  analystEventSchema,
  analystMessageSchema,
  analystThreadSchema,
  errorResponseSchema,
  type AnalystEvent,
  type AnalystMessage,
  type AnalystThread,
  type ScreenFilter,
  spendingOverviewSchema,
  spendingItemSchema,
  spendingRefreshResultSchema,
  spendingStalenessSchema,
  sellRecommendationSchema,
  type SpendingOverview,
  type SpendingItem,
  type SpendingRefreshResult,
  type SpendingStaleness,
  type ManualSpendingRow,
  type SellRecommendation,
} from "@dw/contracts";
import { z } from "zod";
import { ApiClient, ApiError, type ApiClientOptions } from "./client";

/**
 * The Signal tab's reads and its four buttons.
 *
 * Everything here is on the platform API rather than a service of its own, so
 * it extends `ApiClient` without a second base URL. The three writes all return
 * immediately: the work they ask for happens on the worker, and the status
 * endpoints beside them are what a screen polls.
 */
/** The Company Info calls for one subject; see `SalesIntelClient.research`. */
export interface ResearchClient {
  profile(): Promise<ResearchProfile>;
  people(): Promise<AccountPeople>;
  status(): Promise<ResearchStatus>;
  trigger(policy?: ResearchPolicy): Promise<TriggerResearch>;
  sectionReport(sectionKey: string): Promise<SectionReport>;
  editCard(
    cardKey: string,
    body: { facts?: Record<string, unknown>; narrative?: string },
  ): Promise<unknown>;
}

export class SalesIntelClient extends ApiClient {
  /**
   * Kept as well as passed up, because the analyst turn streams over raw
   * `fetch` rather than through `request`, and needs the base URL and the token
   * getter directly. Same reason `SalesChatClient` keeps its own.
   */
  constructor(private readonly intelOptions: ApiClientOptions) {
    super(intelOptions);
  }

  /**
   * One account's packages from one source, under one subject filter.
   *
   * No year: the years are chips built from `counts.by_year`, and the whole
   * source is returned so pressing one costs no round trip. The counts in the
   * response describe the scoped set rather than the page, which is why `scope`
   * has to be sent rather than applied here.
   */
  listTenders(
    accountId: string,
    params: { source?: TenderSource; scope?: TenderScope } = {},
  ): Promise<TenderList> {
    const query = new URLSearchParams();
    if (params.source) query.set("source", params.source);
    if (params.scope) query.set("scope", params.scope);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/tenders${suffix}`,
      tenderListSchema,
    );
  }

  /**
   * The analysis of the same set the list is showing.
   *
   * All three filters travel, not just the year. The two views share one filter
   * bar, and an analysis computed over a wider set than the list beneath it puts
   * two different answers about one account on the same screen.
   */
  tenderAnalytics(
    accountId: string,
    params: { year?: number; source?: TenderSource; scope?: TenderScope } = {},
  ): Promise<TenderAnalytics> {
    const query = new URLSearchParams();
    if (params.year) query.set("year", String(params.year));
    if (params.source) query.set("source", params.source);
    if (params.scope) query.set("scope", params.scope);
    const suffix = query.toString() ? `?${query.toString()}` : "";
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/tenders/analytics${suffix}`,
      tenderAnalyticsSchema,
    );
  }

  /**
   * Queue a scan. 202 when queued, 200 when one was already running.
   *
   * `policy` defaults to `force` because this is only ever reached from a
   * button somebody pressed, and the reason they press it is that the feed
   * looks wrong - answering with `if_needed` answers a question they did not
   * ask. `mode` travels in the body, not the query string.
   */
  refreshSignals(
    accountId: string,
    mode: "news" | "tenders",
    policy: "if_needed" | "force" = "force",
  ): Promise<TriggerScanResult> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/news/scan`,
      triggerScanResultSchema,
      { body: { mode, policy } },
    );
  }

  /**
   * Raise a deal from one invitation, or return the one already raised.
   *
   * No body: everything the deal is made of is on the package already, and a
   * client assembling that payload would put the naming, the value, the
   * deadline and the deduplication key in a file nothing can test.
   */
  raiseTenderOpportunity(
    accountId: string,
    tenderId: string,
  ): Promise<TenderOpportunity> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/tenders/${tenderId}/opportunity`,
      tenderOpportunitySchema,
    );
  }

  /**
   * Correct the Facebook page this account's news scan reads.
   *
   * 422 for anything that is not a company page - a group, a personal profile,
   * a `/posts` sub-path. Those read as a working setting and then return
   * nothing on every scan, which is the failure the tab cannot show by itself.
   */
  setFacebookUrl(accountId: string, url: string): Promise<FacebookUrl> {
    return this.request(
      "PUT",
      `/api/v1/intel/accounts/${accountId}/facebook-url`,
      facebookUrlSchema,
      { body: { url } },
    );
  }

  tenderPortal(accountId: string): Promise<TenderPortal> {
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/tender-portal`,
      tenderPortalSchema,
    );
  }

  setTenderPortalUrl(
    accountId: string,
    entryUrl: string,
  ): Promise<TenderPortal> {
    return this.request(
      "PUT",
      `/api/v1/intel/accounts/${accountId}/tender-portal`,
      tenderPortalSchema,
      { body: { entry_url: entryUrl } },
    );
  }

  discoverTenderPortal(accountId: string): Promise<PortalCompileResult> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/tender-portal/discover`,
      portalCompileResultSchema,
    );
  }

  compileTenderPortal(accountId: string): Promise<PortalCompileResult> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/tender-portal/compile`,
      portalCompileResultSchema,
    );
  }

  startBidderCrawl(
    accountId: string,
    body: { scope?: CrawlScope; limit_packages?: number } = {},
  ): Promise<StartCrawlResult> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/tenders/bidders/crawl`,
      startCrawlResultSchema,
      { body },
    );
  }

  /** Null when this account never ran one. */
  bidderCrawlStatus(accountId: string): Promise<BidderCrawl | null> {
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/tenders/bidders/status`,
      bidderCrawlSchema.nullable(),
    );
  }

  cancelBidderCrawl(accountId: string): Promise<BidderCrawl> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/tenders/bidders/cancel`,
      bidderCrawlSchema,
    );
  }

  tenderPreference(accountId: string): Promise<TenderPreference | null> {
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/tenders/pref`,
      tenderPreferenceSchema.nullable(),
    );
  }

  setTenderPreference(
    accountId: string,
    prefText: string,
  ): Promise<TenderPreference> {
    return this.request(
      "PUT",
      `/api/v1/intel/accounts/${accountId}/tenders/pref`,
      tenderPreferenceSchema,
      { body: { pref_text: prefText } },
    );
  }

  /** Answered on this request; the orchestrator's ceilings are what bound it. */
  ask(question: string, accountId?: string): Promise<ResearchAnswer> {
    return this.request(
      "POST",
      "/api/v1/intel/research/ask",
      researchAnswerSchema,
      {
        body: { question, account_id: accountId ?? null },
      },
    );
  }

  // ----------------------------------------------------------- company info --

  /**
   * The Company Info reads and writes for one subject — an account or, since
   * spec 003 US4, a lead. Same endpoints, same shapes; only the path segment
   * names the record. The account-flavoured methods below delegate here so
   * there is one place that knows the URLs.
   */
  research(subject: ResearchSubject): ResearchClient {
    const base = `/api/v1/intel/${subject.kind === "lead" ? "leads" : "accounts"}/${subject.id}`;
    return {
      /** Everything the eight cards render, in one call. */
      profile: () =>
        this.request("GET", `${base}/profile`, researchProfileSchema),
      /**
       * The stored leadership roster, three-tiered. Empty for a subject never
       * researched — the card shows its own empty state, so this never
       * throws for "no people yet".
       */
      people: () => this.request("GET", `${base}/people`, accountPeopleSchema),
      /** What a screen polls while a run is in flight. */
      status: () =>
        this.request("GET", `${base}/research/status`, researchStatusSchema),
      /**
       * Queue a research run. `force` re-researches a subject that already
       * has a profile; the default lets the freshness rule on the server
       * decide whether one is due. The literals are the endpoint's own.
       */
      trigger: (policy: ResearchPolicy = "if_needed") =>
        this.request("POST", `${base}/research`, triggerResearchSchema, {
          body: { policy },
        }),
      /** One section's long report. */
      sectionReport: (sectionKey: string) =>
        this.request(
          "GET",
          `${base}/research/report-section/${sectionKey}`,
          sectionReportSchema,
        ),
      /**
       * Write a card. An empty string is a real value here: it clears the
       * fact and marks the field the person's, which is the only way a wrong
       * value ever leaves the profile.
       */
      editCard: (
        cardKey: string,
        body: { facts?: Record<string, unknown>; narrative?: string },
      ) =>
        this.request(
          "PATCH",
          `${base}/research/cards/${cardKey}`,
          z.unknown(),
          { body },
        ),
    };
  }

  researchProfile(accountId: string): Promise<ResearchProfile> {
    return this.research({ kind: "account", id: accountId }).profile();
  }

  accountPeople(accountId: string): Promise<AccountPeople> {
    return this.research({ kind: "account", id: accountId }).people();
  }

  researchStatus(accountId: string): Promise<ResearchStatus> {
    return this.research({ kind: "account", id: accountId }).status();
  }

  triggerResearch(
    accountId: string,
    policy: ResearchPolicy = "if_needed",
  ): Promise<TriggerResearch> {
    return this.research({ kind: "account", id: accountId }).trigger(policy);
  }

  /**
   * Which cards exist and what each one owns.
   *
   * The edit form is built from this rather than from a list in the frontend,
   * so a field a lane gains reaches the screen without a second declaration to
   * keep in step - and a field no card owns cannot be sent at all.
   */
  intelCards(): Promise<IntelCard[]> {
    return this.request("GET", "/api/v1/intel/cards", z.array(cardSchema));
  }

  // -------------------------------------------------------------------- news --

  newsFeed(accountId: string): Promise<NewsFeed> {
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/news`,
      newsFeedSchema,
    );
  }

  /**
   * The one column a scan may not write: a person's verdict on a story.
   *
   * `status` is the closed set the endpoint accepts, not any string. It took
   * any string before and the tab sent `"kept"`, so both triage buttons 422'd
   * on every click with nothing in the types to say so.
   */
  triageSignal(signalId: string, status: TriageStatus): Promise<void> {
    return this.request("PATCH", `/api/v1/intel/news/${signalId}`, z.void(), {
      body: { status },
    });
  }

  // ------------------------------------------------------------ it spending --

  itSpending(accountId: string): Promise<SpendingOverview> {
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/it-spending`,
      spendingOverviewSchema,
    );
  }

  /** What a refresh would find — a free SQL probe, no model call. */
  itSpendingStaleness(accountId: string): Promise<SpendingStaleness> {
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/it-spending/staleness`,
      spendingStalenessSchema,
    );
  }

  /** Re-derive the system rows from the stored tenders. Idempotent. */
  refreshItSpending(accountId: string): Promise<SpendingRefreshResult> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/it-spending/refresh`,
      spendingRefreshResultSchema,
    );
  }

  addItSpendingRow(
    accountId: string,
    row: ManualSpendingRow,
  ): Promise<SpendingItem> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/it-spending`,
      spendingItemSchema,
      { body: row },
    );
  }

  /** Approve, reject, or fold one AI-proposed row into the row it repeats
      (the check's hint, or `targetId`). */
  reviewItSpendingRow(
    accountId: string,
    itemId: string,
    action: "approve" | "reject" | "merge",
    targetId?: string,
  ): Promise<SpendingItem> {
    return this.request(
      "PATCH",
      `/api/v1/intel/accounts/${accountId}/it-spending/${itemId}`,
      spendingItemSchema,
      { body: targetId ? { action, target_id: targetId } : { action } },
    );
  }

  /** Run the what-to-sell analysis now, optionally focused on the seller's
      own ask ("chỉ phân tích nhóm phần mềm"). Null on a host with no agent. */
  analyzeSellRecommendations(
    accountId: string,
    intent?: string,
  ): Promise<SellRecommendation | null> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/sell-recommendations`,
      sellRecommendationSchema.nullable(),
      { body: { intent: intent?.trim() || null } },
    );
  }

  latestSellRecommendation(
    accountId: string,
  ): Promise<SellRecommendation | null> {
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/sell-recommendations/latest`,
      sellRecommendationSchema.nullable(),
    );
  }

  // ---------------------------------------------------------------- analyst --

  /** Opens a thread. The first question names it, so the sidebar reads back. */
  openAnalystThread(accountId: string, title: string): Promise<AnalystThread> {
    return this.request(
      "POST",
      `/api/v1/intel/accounts/${accountId}/analyst/threads`,
      analystThreadSchema,
      { body: { title } },
    );
  }

  listAnalystThreads(accountId: string): Promise<AnalystThread[]> {
    return this.request(
      "GET",
      `/api/v1/intel/accounts/${accountId}/analyst/threads`,
      z.array(analystThreadSchema),
    );
  }

  analystTranscript(threadId: string): Promise<AnalystMessage[]> {
    return this.request(
      "GET",
      `/api/v1/intel/analyst/threads/${threadId}/messages`,
      z.array(analystMessageSchema),
    );
  }

  /**
   * One turn, streamed.
   *
   * Over `fetch` rather than `EventSource`, which cannot send the Authorization
   * header every request here is verified against - the same reason sales-chat
   * streams this way.
   */
  async *askAnalyst(
    threadId: string,
    message: string,
    screenFilter?: ScreenFilter,
  ): AsyncGenerator<AnalystEvent> {
    const fetchImpl = this.intelOptions.fetchImpl ?? fetch;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    };
    const token = await this.intelOptions.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;

    const response = await fetchImpl(
      `${this.intelOptions.baseUrl}/api/v1/intel/analyst/threads/${threadId}/messages`,
      {
        method: "POST",
        headers,
        // The filter chips travel with the question. Omitted rather than sent as
        // nulls when the caller has none, because the server's absence default is
        // the screen's own default - and sending an explicit empty filter would
        // widen the answer to every year and every subject instead.
        body: JSON.stringify(
          screenFilter ? { message, screen_filter: screenFilter } : { message },
        ),
      },
    );
    // The backend explains itself in the body. Showing only the status turned
    // every business refusal into "network error" on screen once already.
    if (!response.ok || !response.body) {
      const json: unknown = await response.json().catch(() => null);
      const parsed = errorResponseSchema.safeParse(json);
      throw new ApiError(
        response.status,
        parsed.success
          ? parsed.data
          : {
              code: "internal",
              message: `HTTP ${response.status}`,
              details: {},
            },
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let boundary = buffer.indexOf("\n\n");
      while (boundary !== -1) {
        const block = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const event = parseAnalystEvent(block);
        if (event) yield event;
        boundary = buffer.indexOf("\n\n");
      }
    }
  }
}

/**
 * An event the client does not recognise is dropped, not thrown.
 *
 * A stream is a live turn: refusing the whole answer because one frame carried
 * a field this build has not seen yet would lose the tokens that already
 * arrived, and a deploy skew is exactly when that happens.
 */
function parseAnalystEvent(block: string): AnalystEvent | null {
  const lines = block.split("\n");
  const type = lines.find((line) => line.startsWith("event: "))?.slice(7);
  const data = lines.find((line) => line.startsWith("data: "))?.slice(6);
  if (!type || !data) return null;

  const parsed = analystEventSchema.safeParse({
    type,
    data: JSON.parse(data) as unknown,
  });
  return parsed.success ? parsed.data : null;
}
