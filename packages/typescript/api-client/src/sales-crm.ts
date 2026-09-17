import { z } from "zod";
import {
  accountPageSchema,
  accountSchema,
  accountStatsSchema,
  broadcastSchema,
  searchHitsSchema,
  teamFeedSchema,
  pipelineHealthBundleSchema,
  homeBriefSchema,
  homeTeamSchema,
  activityPageSchema,
  contactPageSchema,
  contactUsageSchema,
  duplicateContactSchema,
  convertResultSchema,
  crmContactSchema,
  crmDocumentSchema,
  crmNoteSchema,
  documentPageSchema,
  notePageSchema,
  companyMatchesSchema,
  duplicateCandidateSchema,
  enrichmentDraftSchema,
  errorResponseSchema,
  leadPageSchema,
  leadSchema,
  opportunityPageSchema,
  dealContactSchema,
  oppMapSchema,
  oppMapMutationSchema,
  oppPersonCandidateSchema,
  oppRevisionSchema,
  oppSuggestionSchema,
  oppSuggestRunSchema,
  stageCriteriaSchema,
  taskCommentSchema,
  pipelineSummarySchema,
  opportunitySchema,
  salesTaskSchema,
  idealCustomerProfileSchema,
  leadScoringActivitySchema,
  leadScoringEventSchema,
  assessmentDetailSchema,
  leadAssessmentSchema,
  scoreTemplateSchema,
  scoreTemplateSummarySchema,
  templateSelectionSchema,
  scoringResultSchema,
  taskPageSchema,
  type Account,
  type AccountPage,
  type ScoreTemplate,
  type ScoreTemplateDefinition,
  type ScoreTemplateSummary,
  type TemplateSelection,
  type AccountStats,
  type ActivityPage,
  type ActivitySubject,
  type ContactPage,
  type ContactUsage,
  type DealContact,
  type DuplicateContact,
  type ConvertResult,
  type Broadcast,
  type SearchHits,
  type TeamFeed,
  type CrmContact,
  type IdealCustomerProfile,
  type PipelineHealthBundle,
  type HomeBrief,
  type HomeTeam,
  type CrmDocument,
  type CrmNote,
  type DocumentPage,
  type NotePage,
  type DocumentCategory,
  type DocumentScope,
  type DuplicateCandidate,
  type CompanyMatches,
  type EnrichmentDraft,
  type Lead,
  type LeadPage,
  type LeadStatus,
  type Opportunity,
  type OpportunityPage,
  type OppMap,
  type OppMapMutation,
  type OppMapOp,
  type OppPersonCandidate,
  type OppRevision,
  type OppSuggestion,
  type OppSuggestRun,
  type StageCriteria,
  type TaskComment,
  type PipelineSummary,
  type OpportunityStage,
  type SalesTask,
  type TaskStatus,
  type AssessmentDetail,
  type LeadAssessment,
  type LeadScoringActivity,
  type LeadScoringEvent,
  type ScoringResult,
  type TaskPage,
  bellPageSchema,
  privateNoteSchema,
  extractionStatusSchema,
  reminderSchema,
  type BellPage,
  type ContactReminder,
  type ExtractionStatus,
  type PrivateNote,
  type ReminderKind,
  type ReminderVisibility,
  keyPeopleCandidateSchema,
  personResearchSchema,
  proposalDecisionSchema,
  riskReportSchema,
  stakeholderArrangeSchema,
  stakeholderDigestSchema,
  stakeholderExtractResultSchema,
  stakeholderMapSchema,
  stakeholderMutationSchema,
  stakeholderProposalSchema,
  stakeholderRevisionSchema,
  type KeyPeopleCandidate,
  type PersonResearch,
  type RiskReport,
  type StakeholderArrange,
  type StakeholderDigest,
  type StakeholderExtractResult,
  type StakeholderMap,
  type StakeholderMutation,
  type StakeholderOp,
  type StakeholderProposal,
  type StakeholderRevision,
  type ReportColumnFilter,
  type ReportListSort,
  type ReportCatalog,
  type ReportChange,
  type ReportNeighbours,
  type ReportPage,
  type ReportRootModule,
  type ReportRunPage,
  type ReportRunRequest,
  type ReportView,
  type SaveReportCommand,
  reportCatalogSchema,
  reportChangeSchema,
  reportNeighboursSchema,
  reportPageSchema,
  reportRunPageSchema,
  reportViewSchema,
  type AccountAccess,
  type OpportunityAccess,
  type ShareOutcome,
  type SharingTeam,
  shareOutcomeSchema,
  sharingTeamSchema,
} from "@dw/contracts";
import { ApiClient, ApiError, type ApiClientOptions } from "./client";

/**
 * What the report list is showing: the same parameters travel on the detail
 * and neighbour calls, because "(n of N)", PREVIOUS and NEXT have to walk the
 * order the reader is actually looking at.
 */
export interface ReportListParams {
  limit?: number;
  offset?: number;
  search?: string;
  sort?: ReportListSort;
  descending?: boolean;
  filters?: ReportColumnFilter[];
}

/** Query-string helper: skips null/undefined/empty values. */
function qs(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const rendered = search.toString();
  return rendered ? `?${rendered}` : "";
}

/** Column filters travel as one JSON query param the API validates. */
function encodeConditions(conditions: unknown[] | undefined): {
  filters?: string;
} {
  return conditions?.length ? { filters: JSON.stringify(conditions) } : {};
}

/**
 * A leadership dashboard focus: narrow every tab to one person (`owner`) or one
 * manager's team (`team` = their subtree). The server still checks the focus is
 * within what the caller may see, so this only ever narrows.
 */
export interface DashboardFocus {
  owner?: string | null;
  team?: string | null;
}

export type LeadSortField =
  | "company_name"
  | "status"
  | "contact_name"
  | "contact_phone"
  | "contact_email"
  | "owner_user_id"
  | "source"
  | "created_at";

/** The four text operators the business documents name, shared by every list
 *  that filters a text column. One union rather than one per screen, because
 *  the condition editor is one component. */
export type TextFilterOp = "is" | "isnt" | "contain" | "not_contain";
export type LeadTextFilterOp = TextFilterOp;

export type LeadTextFilterField =
  | "company_name"
  | "contact_name"
  | "contact_phone"
  | "contact_email"
  | "source";

/** Columns whose values can be ticked off a list ("lọc theo giá trị đã tồn tại"). */
export type LeadValueFilterField =
  | "company_name"
  | "contact_name"
  | "contact_phone"
  | "contact_email"
  | "source"
  | "owner_user_id";

/** One column filter condition; the API ANDs them (AC-LEADLIST-020..023). */
export type LeadColumnFilter =
  | {
      kind: "text";
      field: LeadTextFilterField;
      op: LeadTextFilterOp;
      value: string;
    }
  | { kind: "status"; statuses: LeadStatus[] }
  | { kind: "created"; date_from?: string; date_to?: string }
  | { kind: "values"; field: LeadValueFilterField; values: string[] }
  | { kind: "score"; minimum?: number; maximum?: number };

export interface LeadFilters {
  limit?: number;
  offset?: number;
  status?: LeadStatus;
  search?: string;
  owner_user_id?: string;
  sort?: LeadSortField;
  descending?: boolean;
  filters?: LeadColumnFilter[];
}

/** What the opportunity list can be ordered by - the eight on-screen columns,
 *  one at a time. */
export type OpportunitySortField =
  | "name"
  | "account_name"
  | "stage"
  | "amount"
  | "expected_close_date"
  | "owner_user_id"
  | "probability"
  | "created_at";

/** What the account list can be ordered by - the seven on-screen columns
 *  (spec 011, §Nhóm D). The owner column orders by the person's NAME, because
 *  ordering people by an opaque id reads as unsorted. */
export type AccountSortField =
  | "name"
  | "industry"
  | "district"
  | "open_opportunities"
  | "owner_user_id"
  | "created_at"
  | "updated_at";

/** Text columns on the account list. Not the owner: picked, never typed. */
export type AccountTextFilterField = "name" | "industry" | "district";

/** Columns whose values can be ticked off a list, wider by the owner. */
export type AccountValueFilterField =
  "name" | "industry" | "district" | "owner_user_id";

export type AccountDateFilterField = "created_at" | "updated_at";

/** The only numeric column is a count of deals neither won nor lost, so the
 *  filter and the cell beside it always agree. */
export type AccountNumberFilterField = "open_opportunities";

/** One account column filter condition; the API ANDs them (spec 011, FR-C05). */
export type AccountColumnFilter =
  | {
      kind: "text";
      field: AccountTextFilterField;
      op: TextFilterOp;
      value: string;
    }
  | { kind: "values"; field: AccountValueFilterField; values: string[] }
  | {
      kind: "date";
      field: AccountDateFilterField;
      date_from?: string;
      date_to?: string;
    }
  | {
      kind: "number";
      field: AccountNumberFilterField;
      minimum?: number;
      maximum?: number;
    };

/** Text columns on the opportunity list. */
export type OpportunityTextFilterField = "name" | "account_name";

/** Columns whose values can be ticked off a list. Wider by the owner, who is
 *  picked from a roster rather than typed. */
export type OpportunityValueFilterField =
  "name" | "account_name" | "owner_user_id";

export type OpportunityDateFilterField = "expected_close_date" | "created_at";

/** Probability is the number the column shows - the stage default when the deal
 *  carries no override - so a filter and the cell beside it always agree. */
export type OpportunityNumberFilterField = "amount" | "probability";

/** One column filter condition; the API ANDs them (AC-OPPLIST-021..026). */
export type OpportunityColumnFilter =
  | {
      kind: "text";
      field: OpportunityTextFilterField;
      op: TextFilterOp;
      value: string;
    }
  | { kind: "values"; field: OpportunityValueFilterField; values: string[] }
  | { kind: "stage"; stages: OpportunityStage[] }
  | {
      kind: "date";
      field: OpportunityDateFilterField;
      date_from?: string;
      date_to?: string;
    }
  | {
      kind: "number";
      field: OpportunityNumberFilterField;
      minimum?: number;
      maximum?: number;
    };

export interface OpportunityFilters {
  limit?: number;
  offset?: number;
  stage?: OpportunityStage;
  account_id?: string;
  contact_id?: string;
  owner_user_id?: string;
  open_only?: boolean;
  /** One keyword, matched against the deal name and the account name. */
  search?: string;
  filters?: OpportunityColumnFilter[];
  sort?: OpportunitySortField;
  descending?: boolean;
}

/** What narrows the Pipeline Summary. The same fields as the list minus
 *  `search`: the BD switches the summary off while someone is searching. */
export type PipelineSummaryFilters = Omit<
  OpportunityFilters,
  "limit" | "offset" | "search" | "sort" | "descending"
>;

export interface TaskFilters {
  limit?: number;
  offset?: number;
  status?: TaskStatus;
  /** Only what is still owed - not started or in progress. Since spec 006
   * there are three statuses, so "open" is a pair rather than a value. */
  open_only?: boolean;
  assigned_to_user_id?: string;
  lead_id?: string;
  account_id?: string;
  opportunity_id?: string;
  /** With account_id: also return tasks on the account's opportunities. */
  include_opportunity_tasks?: boolean;
  /** Also return calendar events, not only the follow-ups owed. Only the
   * lead's Activity tab wants both (AC-LEADACT-002). */
  include_events?: boolean;
  search?: string;
}

/**
 * The CRM application surface (leads, accounts, contacts, opportunities,
 * tasks, documents, timeline) plus the lead-scoring reads the CRM UI shows.
 */
/**
 * `?template_id=` when a caller names a frame, nothing when it does not.
 *
 * The distinction is real: absent means "under whatever I have selected", and
 * an explicit `null` cannot be spelled in a query string — a caller wanting the
 * system default passes no id and relies on their own selection, or sets it.
 */
function templateQuery(templateId?: string | null): string {
  return templateId ? qs({ template_id: templateId }) : "";
}

export class SalesCrmClient extends ApiClient {
  constructor(private readonly crmOptions: ApiClientOptions) {
    super(crmOptions);
  }

  // ---- reports (spec 013) ------------------------------------------------

  listReports(params: ReportListParams = {}): Promise<ReportPage> {
    const { filters, ...rest } = params;
    return this.request(
      "GET",
      `/api/v1/crm/reports${qs({ ...rest, ...encodeConditions(filters) })}`,
      reportPageSchema,
    );
  }

  /** The values one list column already holds, for the tick-a-value filter. */
  getReportFilterValues(
    field: "root_module" | "assigned_to",
  ): Promise<string[]> {
    return this.request(
      "GET",
      `/api/v1/crm/reports/filter-values${qs({ field })}`,
      z.array(z.string()),
    );
  }

  /** One report. Pass the list parameters to get "(n of N)" with it. */
  getReport(
    reportId: string,
    params: ReportListParams = {},
  ): Promise<ReportView> {
    const { filters, ...rest } = params;
    return this.request(
      "GET",
      `/api/v1/crm/reports/${reportId}${qs({ ...rest, ...encodeConditions(filters) })}`,
      reportViewSchema,
    );
  }

  /** Run the report: one page of one block, plus the list of blocks.
   *
   * POST rather than GET because the parameters, the column filters and the
   * sort do not fit safely in a query string. It has no side effect. */
  runReport(
    reportId: string,
    request: ReportRunRequest = {},
  ): Promise<ReportRunPage> {
    return this.request(
      "POST",
      `/api/v1/crm/reports/${reportId}/run`,
      reportRunPageSchema,
      { body: request as unknown as Record<string, unknown> },
    );
  }

  /** The values one result column already holds, as (code, label) pairs, for
   *  the tick-a-value filter and for a Multi parameter. The code is what goes
   *  back into the query; the label is what the reader ticks. Scoped
   *  server-side to the rows this caller's report may show. */
  getReportRowValues(
    reportId: string,
    field: string,
  ): Promise<[string, string][]> {
    return this.request(
      "GET",
      `/api/v1/crm/reports/${reportId}/filter-values${qs({ field })}`,
      z.array(z.tuple([z.string(), z.string()])),
    );
  }

  /** The log of who changed which field of this definition, newest first. */
  getReportChanges(reportId: string, limit = 50): Promise<ReportChange[]> {
    return this.request(
      "GET",
      `/api/v1/crm/reports/${reportId}/changes${qs({ limit })}`,
      z.array(reportChangeSchema),
    );
  }

  /** The module tree and fields the edit screen may add from. */
  getReportCatalog(root: ReportRootModule): Promise<ReportCatalog> {
    return this.request(
      "GET",
      `/api/v1/crm/reports/catalog${qs({ root })}`,
      reportCatalogSchema,
    );
  }

  /** Save a definition. A stale `expected_version` comes back as a 409. */
  saveReport(
    reportId: string,
    command: SaveReportCommand,
  ): Promise<ReportView> {
    return this.request(
      "PUT",
      `/api/v1/crm/reports/${reportId}`,
      reportViewSchema,
      {
        body: command as unknown as Record<string, unknown>,
      },
    );
  }

  /** The whole report as a file. Returns the blob plus the server's filename,
   *  because the name carries Vietnamese and the browser cannot guess it. */
  async exportReport(
    reportId: string,
    request: ReportRunRequest,
    format: "csv" | "pdf",
  ): Promise<{ blob: Blob; filename: string }> {
    const response = await this.rawRequest(
      "POST",
      `/api/v1/crm/reports/${reportId}/export${qs({ format })}`,
      { body: request as unknown as Record<string, unknown> },
    );
    const disposition = response.headers.get("content-disposition") ?? "";
    const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
    return {
      blob: await response.blob(),
      filename: encoded ? decodeURIComponent(encoded) : `report.${format}`,
    };
  }

  /** PREVIOUS / NEXT in the order the list was showing. */
  getReportNeighbours(
    reportId: string,
    params: ReportListParams = {},
  ): Promise<ReportNeighbours> {
    const { filters, ...rest } = params;
    return this.request(
      "GET",
      `/api/v1/crm/reports/${reportId}/neighbors${qs({ ...rest, ...encodeConditions(filters) })}`,
      reportNeighboursSchema,
    );
  }

  // ---- leads -------------------------------------------------------------

  listLeads(leadFilters: LeadFilters = {}): Promise<LeadPage> {
    const { filters, ...rest } = leadFilters;
    return this.request(
      "GET",
      `/api/v1/crm/leads${qs({
        ...rest,
        // Column filters travel as one JSON query param the API validates.
        filters: filters?.length ? JSON.stringify(filters) : undefined,
      })}`,
      leadPageSchema,
    );
  }

  /** The values one lead column already holds, for the tick-a-value filter.
   * Scoped server-side to the leads the caller may see. */
  getLeadFilterValues(field: LeadValueFilterField): Promise<string[]> {
    return this.request(
      "GET",
      `/api/v1/crm/leads/filter-values${qs({ field })}`,
      z.array(z.string()),
    );
  }

  createLead(payload: Record<string, unknown>): Promise<Lead> {
    return this.request("POST", "/api/v1/crm/leads", leadSchema, {
      body: payload,
    });
  }

  getLead(leadId: string): Promise<Lead> {
    return this.request("GET", `/api/v1/crm/leads/${leadId}`, leadSchema);
  }

  updateLead(leadId: string, payload: Record<string, unknown>): Promise<Lead> {
    return this.request("PATCH", `/api/v1/crm/leads/${leadId}`, leadSchema, {
      body: payload,
    });
  }

  changeLeadStatus(
    leadId: string,
    payload: { status: LeadStatus; reason?: string; expected_version: number },
  ): Promise<Lead> {
    return this.request(
      "POST",
      `/api/v1/crm/leads/${leadId}/status`,
      leadSchema,
      {
        body: payload,
      },
    );
  }

  deleteLead(leadId: string): Promise<void> {
    return this.requestVoid("DELETE", `/api/v1/crm/leads/${leadId}`);
  }

  convertLead(
    leadId: string,
    payload: Record<string, unknown>,
  ): Promise<ConvertResult> {
    return this.request(
      "POST",
      `/api/v1/crm/leads/${leadId}/convert`,
      convertResultSchema,
      {
        body: payload,
      },
    );
  }

  // ---- accounts ----------------------------------------------------------

  listAccounts(
    filters: {
      limit?: number;
      offset?: number;
      parent_account_id?: string;
      search?: string;
      /** At most one per column; the API ANDs them (spec 011, FR-C05). */
      filters?: AccountColumnFilter[];
      sort?: AccountSortField;
      descending?: boolean;
    } = {},
  ): Promise<AccountPage> {
    const { filters: conditions, ...rest } = filters;
    return this.request(
      "GET",
      `/api/v1/crm/accounts${qs({ ...rest, ...encodeConditions(conditions) })}`,
      accountPageSchema,
    );
  }

  /** The values one column already holds, for the tick-a-value panel. Narrowed
   *  by the server to what this caller may see. */
  getAccountFilterValues(field: AccountValueFilterField): Promise<string[]> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/filter-values${qs({ field })}`,
      z.array(z.string()),
    );
  }

  createAccount(payload: Record<string, unknown>): Promise<Account> {
    return this.request("POST", "/api/v1/crm/accounts", accountSchema, {
      body: payload,
    });
  }

  getAccount(accountId: string): Promise<Account> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}`,
      accountSchema,
    );
  }

  // ---- sharing team -------------------------------------------------------

  getSharingTeam(accountId: string): Promise<SharingTeam> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}/shares`,
      sharingTeamSchema,
    );
  }

  /**
   * Adds several people at one level - the pop-up's shape, and the spec's.
   * The response says who was left out and why, which is MSG06.
   */
  shareAccount(
    accountId: string,
    body: {
      principal_ids: string[];
      account_access: AccountAccess;
      opportunity_access?: OpportunityAccess;
    },
  ): Promise<ShareOutcome> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/shares`,
      shareOutcomeSchema,
      { body },
    );
  }

  changeShareLevel(
    accountId: string,
    shareId: string,
    body: {
      account_access: AccountAccess;
      opportunity_access: OpportunityAccess;
      expected_version: number;
    },
  ): Promise<void> {
    return this.requestVoid(
      "PATCH",
      `/api/v1/crm/accounts/${accountId}/shares/${shareId}`,
      { body },
    );
  }

  removeShare(accountId: string, shareId: string): Promise<void> {
    return this.requestVoid(
      "DELETE",
      `/api/v1/crm/accounts/${accountId}/shares/${shareId}`,
    );
  }

  updateAccount(
    accountId: string,
    payload: Record<string, unknown>,
  ): Promise<Account> {
    return this.request(
      "PATCH",
      `/api/v1/crm/accounts/${accountId}`,
      accountSchema,
      {
        body: payload,
      },
    );
  }

  getAccountStats(accountId: string): Promise<AccountStats> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}/stats`,
      accountStatsSchema,
    );
  }

  search(term: string, limit?: number): Promise<SearchHits> {
    return this.request(
      "GET",
      `/api/v1/crm/search${qs({ q: term, limit })}`,
      searchHitsSchema,
    );
  }

  getTeamFeed(limit = 40): Promise<TeamFeed> {
    return this.request(
      "GET",
      `/api/v1/crm/team/feed${qs({ limit })}`,
      teamFeedSchema,
    );
  }

  listBroadcasts(limit = 50): Promise<Broadcast[]> {
    return this.request(
      "GET",
      `/api/v1/crm/broadcasts${qs({ limit })}`,
      z.array(broadcastSchema),
    );
  }

  postBroadcast(payload: {
    title: string;
    body?: string;
    company_name?: string;
    account_id?: string;
  }): Promise<Broadcast> {
    return this.request("POST", "/api/v1/crm/broadcasts", broadcastSchema, {
      body: payload,
    });
  }

  deleteBroadcast(broadcastId: string): Promise<void> {
    return this.requestVoid("DELETE", `/api/v1/crm/broadcasts/${broadcastId}`);
  }

  getPipelineHealth(
    period?: string,
    focus?: DashboardFocus,
  ): Promise<PipelineHealthBundle> {
    return this.request(
      "GET",
      `/api/v1/crm/dashboard/pipeline-health${qs({ period, owner: focus?.owner, team: focus?.team })}`,
      pipelineHealthBundleSchema,
    );
  }

  getHomeBrief(): Promise<HomeBrief> {
    return this.request("GET", "/api/v1/crm/home/brief", homeBriefSchema);
  }

  getHomeTeam(): Promise<HomeTeam> {
    return this.request("GET", "/api/v1/crm/home/team", homeTeamSchema);
  }

  findDuplicates(params: {
    tax_code?: string;
    name?: string;
    website?: string;
  }): Promise<DuplicateCandidate[]> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/duplicates${qs({ ...params })}`,
      z.array(duplicateCandidateSchema),
    );
  }

  /**
   * Which filed companies a typed name matches. Step 1 of the create flow.
   *
   * `country` decides which language the search runs in and which register it
   * trusts: a Japanese company searched in Vietnamese comes back empty, and
   * empty reads on the form as "not found" rather than "asked in the wrong
   * language".
   */
  identifyCompany(
    name: string,
    country?: string,
    signal?: AbortSignal,
  ): Promise<CompanyMatches> {
    return this.request(
      "POST",
      "/api/v1/crm/accounts/identify",
      companyMatchesSchema,
      { body: { name, country }, signal },
    );
  }

  // ---- stakeholder map ---------------------------------------------------

  /** The whole tree in one read: rows, the humans behind them, the badge. */
  getStakeholderMap(accountId: string): Promise<StakeholderMap> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map`,
      stakeholderMapSchema,
    );
  }

  /**
   * The one write door. Sends the version the tree was read at; a 409 means
   * somebody else saved first, and the canvas shows the reload banner rather
   * than silently overwriting them.
   */
  applyStakeholderOps(
    accountId: string,
    baseVersion: number,
    ops: StakeholderOp[],
  ): Promise<StakeholderMutation> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/ops`,
      stakeholderMutationSchema,
      { body: { base_version: baseVersion, ops } },
    );
  }

  clearStakeholderMap(
    accountId: string,
    baseVersion: number,
  ): Promise<StakeholderMutation> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/clear`,
      stakeholderMutationSchema,
      { body: { base_version: baseVersion } },
    );
  }

  stakeholderRevisions(accountId: string): Promise<StakeholderRevision[]> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/revisions`,
      z.array(stakeholderRevisionSchema),
    );
  }

  restoreStakeholderMap(
    accountId: string,
    version: number,
  ): Promise<StakeholderMutation> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/restore`,
      stakeholderMutationSchema,
      { body: { version } },
    );
  }

  stakeholderAnalysis(accountId: string): Promise<RiskReport> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/analysis`,
      riskReportSchema,
    );
  }

  keyPeopleCandidates(accountId: string): Promise<KeyPeopleCandidate[]> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/key-people-candidates`,
      z.array(keyPeopleCandidateSchema),
    );
  }

  importKeyPeople(
    accountId: string,
    baseVersion: number,
    personIds: string[],
    createInferredEdges = false,
  ): Promise<StakeholderMutation> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/import-key-people`,
      stakeholderMutationSchema,
      {
        body: {
          base_version: baseVersion,
          person_ids: personIds,
          create_inferred_edges: createInferredEdges,
        },
      },
    );
  }

  /** Queue one person for the web-research agent; the worker runs it. */
  triggerPersonResearch(
    accountId: string,
    contactId: string,
  ): Promise<PersonResearch> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/person-research`,
      personResearchSchema,
      { body: { contact_id: contactId } },
    );
  }

  personResearchStatus(
    accountId: string,
    contactId: string,
  ): Promise<PersonResearch> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/person-research/${contactId}`,
      personResearchSchema,
    );
  }

  /** The model's ordered levels for the canvas to lay rows out; writes nothing. */
  arrangeStakeholderMap(accountId: string): Promise<StakeholderArrange> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/arrange`,
      stakeholderArrangeSchema,
    );
  }

  /** The roster in a paragraph, written fresh by the model and not stored. */
  stakeholderDigest(accountId: string): Promise<StakeholderDigest> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/digest`,
      stakeholderDigestSchema,
    );
  }

  stakeholderProposals(
    accountId: string,
    status = "pending",
  ): Promise<StakeholderProposal[]> {
    return this.request(
      "GET",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/proposals?status=${status}`,
      z.array(stakeholderProposalSchema),
    );
  }

  acceptStakeholderProposal(
    accountId: string,
    proposalId: string,
    baseVersion: number,
    overrides: Record<string, unknown> = {},
  ): Promise<StakeholderMutation> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/proposals/${proposalId}/accept`,
      stakeholderMutationSchema,
      { body: { base_version: baseVersion, overrides } },
    );
  }

  rejectStakeholderProposal(
    accountId: string,
    proposalId: string,
  ): Promise<{ id: string; status: string }> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/proposals/${proposalId}/reject`,
      proposalDecisionSchema,
    );
  }

  /**
   * Read attached meeting documents into the proposal box, inline. With no
   * documentId, every indexed attachment on the account is (re)read — dedupe
   * keys make a rerun over already-read documents free.
   */
  extractStakeholders(
    accountId: string,
    documentId?: string,
  ): Promise<StakeholderExtractResult> {
    return this.request(
      "POST",
      `/api/v1/crm/accounts/${accountId}/stakeholder-map/extract`,
      stakeholderExtractResultSchema,
      { body: { document_id: documentId ?? null } },
    );
  }

  /**
   * Draft the rest of a company's record. Step 2, once step 1 is answered.
   *
   * `legal_name` and `tax_code` are the entity the user picked, and passing
   * them is what keeps this pass on one company: every query it runs carries
   * the name, so a brand that means three companies would otherwise return an
   * address from one and a headcount from another.
   */
  enrichPreview(
    name: string,
    country?: string,
    identity?: { legal_name?: string; tax_code?: string },
    signal?: AbortSignal,
  ): Promise<EnrichmentDraft> {
    return this.request(
      "POST",
      "/api/v1/crm/accounts/enrich-preview",
      enrichmentDraftSchema,
      {
        body: { name, country, ...identity },
        signal,
      },
    );
  }

  // ---- contacts ----------------------------------------------------------

  listContacts(
    filters: {
      limit?: number;
      offset?: number;
      account_id?: string;
      /** One lead's buying committee, recorded before it converted. */
      lead_id?: string;
      search?: string;
      /** True for Contacts - the people somebody has actually spoken to.
       *  Omit for the whole account pool, which is what the map and the
       *  create-opportunity picker need. */
      contacted?: boolean;
    } = {},
  ): Promise<ContactPage> {
    return this.request(
      "GET",
      `/api/v1/crm/contacts${qs({ ...filters })}`,
      contactPageSchema,
    );
  }

  /** Who this person already is in the workspace, or null when they are new.
   * The same rule createContact/updateContact are judged by, asked as a
   * question so the form can warn before the save refuses. */
  findDuplicateContact(probe: {
    full_name: string;
    email?: string;
    phone?: string;
    role_title?: string;
    /** The row being edited, so an edit does not find itself. */
    exclude?: string;
  }): Promise<DuplicateContact | null> {
    return this.request(
      "GET",
      `/api/v1/crm/contacts/duplicate${qs({ ...probe })}`,
      duplicateContactSchema.nullable(),
    );
  }

  getContact(contactId: string): Promise<CrmContact> {
    return this.request(
      "GET",
      `/api/v1/crm/contacts/${contactId}`,
      crmContactSchema,
    );
  }

  createContact(payload: Record<string, unknown>): Promise<CrmContact> {
    return this.request("POST", "/api/v1/crm/contacts", crmContactSchema, {
      body: payload,
    });
  }

  updateContact(
    contactId: string,
    payload: Record<string, unknown>,
  ): Promise<CrmContact> {
    return this.request(
      "PATCH",
      `/api/v1/crm/contacts/${contactId}`,
      crmContactSchema,
      {
        body: payload,
      },
    );
  }

  /** Make this person the lead's Contact (spec 008). Its own route, not a
   * field on the PATCH: the flag decides which name the lead list shows, so no
   * ordinary edit may move it as a side effect. */
  setPrimaryContact(
    contactId: string,
    payload: { expected_version: number },
  ): Promise<CrmContact> {
    return this.request(
      "POST",
      `/api/v1/crm/contacts/${contactId}/primary`,
      crmContactSchema,
      { body: payload },
    );
  }

  /** What deleting this person would sweep away, and whether the caller may. */
  getContactUsage(contactId: string): Promise<ContactUsage> {
    return this.request(
      "GET",
      `/api/v1/crm/contacts/${contactId}/usage`,
      contactUsageSchema,
    );
  }

  deleteContact(contactId: string): Promise<void> {
    return this.requestVoid("DELETE", `/api/v1/crm/contacts/${contactId}`);
  }

  // ---- opportunities -----------------------------------------------------

  listOpportunities(
    filters: OpportunityFilters = {},
  ): Promise<OpportunityPage> {
    const { filters: conditions, ...rest } = filters;
    return this.request(
      "GET",
      `/api/v1/crm/opportunities${qs({
        ...rest,
        ...encodeConditions(conditions),
      })}`,
      opportunityPageSchema,
    );
  }

  getOpportunityFilterValues(
    field: OpportunityValueFilterField,
  ): Promise<string[]> {
    return this.request(
      "GET",
      `/api/v1/crm/opportunities/filter-values${qs({ field })}`,
      z.array(z.string()),
    );
  }

  getPipelineSummary(
    filters: PipelineSummaryFilters = {},
  ): Promise<PipelineSummary> {
    const { filters: conditions, ...rest } = filters;
    return this.request(
      "GET",
      `/api/v1/crm/opportunities/pipeline-summary${qs({
        ...rest,
        ...encodeConditions(conditions),
      })}`,
      pipelineSummarySchema,
    );
  }

  createOpportunity(payload: Record<string, unknown>): Promise<Opportunity> {
    return this.request(
      "POST",
      "/api/v1/crm/opportunities",
      opportunitySchema,
      {
        body: payload,
      },
    );
  }

  getOpportunity(opportunityId: string): Promise<Opportunity> {
    return this.request(
      "GET",
      `/api/v1/crm/opportunities/${opportunityId}`,
      opportunitySchema,
    );
  }

  updateOpportunity(
    opportunityId: string,
    payload: Record<string, unknown>,
  ): Promise<Opportunity> {
    return this.request(
      "PATCH",
      `/api/v1/crm/opportunities/${opportunityId}`,
      opportunitySchema,
      { body: payload },
    );
  }

  // ---- a deal's contacts (0120) ------------------------------------------
  // The same rows read from the person's side are their related deals, which
  // `listOpportunities({ contact_id })` already answers.

  listDealContacts(opportunityId: string): Promise<DealContact[]> {
    return this.request(
      "GET",
      `/api/v1/crm/opportunities/${opportunityId}/contacts`,
      z.array(dealContactSchema),
    );
  }

  addDealContact(
    opportunityId: string,
    contactId: string,
  ): Promise<DealContact[]> {
    return this.request(
      "POST",
      `/api/v1/crm/opportunities/${opportunityId}/contacts`,
      z.array(dealContactSchema),
      { body: { contact_id: contactId } },
    );
  }

  removeDealContact(
    opportunityId: string,
    contactId: string,
  ): Promise<DealContact[]> {
    return this.request(
      "DELETE",
      `/api/v1/crm/opportunities/${opportunityId}/contacts/${contactId}`,
      z.array(dealContactSchema),
    );
  }

  deleteOpportunity(opportunityId: string): Promise<void> {
    return this.requestVoid(
      "DELETE",
      `/api/v1/crm/opportunities/${opportunityId}`,
    );
  }

  getStageCriteria(
    opportunityId: string,
    stage: OpportunityStage,
  ): Promise<StageCriteria> {
    return this.request(
      "GET",
      `/api/v1/crm/opportunities/${opportunityId}/stage-criteria${qs({ stage })}`,
      stageCriteriaSchema,
    );
  }

  recordStageChecks(
    opportunityId: string,
    payload: {
      expected_version: number;
      answers: Record<string, string | null>;
    },
  ): Promise<Opportunity> {
    return this.request(
      "PATCH",
      `/api/v1/crm/opportunities/${opportunityId}/stage-checks`,
      opportunitySchema,
      { body: payload },
    );
  }

  cloneOpportunity(opportunityId: string): Promise<Opportunity> {
    return this.request(
      "POST",
      `/api/v1/crm/opportunities/${opportunityId}/clone`,
      opportunitySchema,
    );
  }

  /** An empty map at version 0 while nobody has drawn one (BD FC-03). */
  getOppStakeholderMap(opportunityId: string): Promise<OppMap> {
    return this.request(
      "GET",
      `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map`,
      oppMapSchema,
    );
  }

  /** The map's one write door; 409 carries `stale_map_version`. */
  applyOppMapOps(
    opportunityId: string,
    payload: { base_version: number; ops: OppMapOp[] },
  ): Promise<OppMapMutation> {
    return this.request(
      "POST",
      `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map/ops`,
      oppMapMutationSchema,
      { body: payload },
    );
  }

  getOppMapRevisions(opportunityId: string): Promise<OppRevision[]> {
    return this.request(
      "GET",
      `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map/revisions`,
      z.array(oppRevisionSchema),
    );
  }

  restoreOppMap(
    opportunityId: string,
    payload: { base_version: number; version: number },
  ): Promise<OppMapMutation> {
    return this.request(
      "POST",
      `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map/restore`,
      oppMapMutationSchema,
      { body: payload },
    );
  }

  listOppMapSuggestions(
    opportunityId: string,
    params?: { status?: string },
  ): Promise<OppSuggestion[]> {
    const query = params?.status
      ? `?status=${encodeURIComponent(params.status)}`
      : "";
    return this.request(
      "GET",
      `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map/suggestions${query}`,
      z.array(oppSuggestionSchema),
    );
  }

  /** The account's people pool for the add dialog (BD FC-04); with
   * `forCardId` the same pool ranked against one placeholder card (doc 04
   * "resolve identity"), people already on the map left out. */
  getOppMapCandidates(
    opportunityId: string,
    options: { forCardId?: string } = {},
  ): Promise<OppPersonCandidate[]> {
    const path = `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map/candidates`;
    return this.request(
      "GET",
      `${path}${qs({ for_card_id: options.forCardId })}`,
      z.array(oppPersonCandidateSchema),
    );
  }

  /** One AI run over the account's people (BD FC-02); 404 without a model. */
  suggestOppMap(opportunityId: string): Promise<OppSuggestRun> {
    return this.request(
      "POST",
      `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map/suggest`,
      oppSuggestRunSchema,
    );
  }

  /** One suggestion onto the map. A drop from the tray sends where the person
   * landed and `connect_lines`, so their suggested lines to people already on
   * the map arrive in the same version. */
  acceptOppMapSuggestion(
    opportunityId: string,
    suggestionId: string,
    payload: {
      base_version: number;
      roles?: string[];
      attitude?: string;
      influence?: string;
      position?: { x: number; y: number };
      connect_lines?: boolean;
    },
  ): Promise<OppMapMutation> {
    return this.request(
      "POST",
      `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map/suggestions/${suggestionId}/accept`,
      oppMapMutationSchema,
      { body: payload },
    );
  }

  rejectOppMapSuggestion(
    opportunityId: string,
    suggestionId: string,
  ): Promise<OppSuggestion> {
    return this.request(
      "POST",
      `/api/v1/crm/opportunities/${opportunityId}/stakeholder-map/suggestions/${suggestionId}/reject`,
      oppSuggestionSchema,
    );
  }

  moveOpportunityStage(
    opportunityId: string,
    payload: {
      stage: OpportunityStage;
      expected_version: number;
      lost_reason?: string;
      probability?: number;
    },
  ): Promise<Opportunity> {
    return this.request(
      "POST",
      `/api/v1/crm/opportunities/${opportunityId}/stage`,
      opportunitySchema,
      { body: payload },
    );
  }

  // ---- tasks -------------------------------------------------------------

  listTasks(filters: TaskFilters = {}): Promise<TaskPage> {
    return this.request(
      "GET",
      `/api/v1/crm/tasks${qs({ ...filters })}`,
      taskPageSchema,
    );
  }

  createTask(payload: Record<string, unknown>): Promise<SalesTask> {
    return this.request("POST", "/api/v1/crm/tasks", salesTaskSchema, {
      body: payload,
    });
  }

  updateTask(
    taskId: string,
    payload: Record<string, unknown>,
  ): Promise<SalesTask> {
    return this.request(
      "PATCH",
      `/api/v1/crm/tasks/${taskId}`,
      salesTaskSchema,
      {
        body: payload,
      },
    );
  }

  listTaskComments(taskId: string): Promise<TaskComment[]> {
    return this.request(
      "GET",
      `/api/v1/crm/tasks/${taskId}/comments`,
      taskCommentSchema.array(),
    );
  }

  addTaskComment(
    taskId: string,
    payload: { body: string; attachment_document_ids?: string[] },
  ): Promise<TaskComment> {
    return this.request(
      "POST",
      `/api/v1/crm/tasks/${taskId}/comments`,
      taskCommentSchema,
      { body: payload },
    );
  }

  deleteTaskComment(taskId: string, commentId: string): Promise<void> {
    return this.requestVoid(
      "DELETE",
      `/api/v1/crm/tasks/${taskId}/comments/${commentId}`,
    );
  }

  deleteTask(taskId: string): Promise<void> {
    return this.requestVoid("DELETE", `/api/v1/crm/tasks/${taskId}`);
  }

  /** One task by id. The Tasks screen is a list, so a link that names a
   *  single task (a report cell, a notification) reads it back this way. */
  getTask(taskId: string): Promise<SalesTask> {
    return this.request("GET", `/api/v1/crm/tasks/${taskId}`, salesTaskSchema);
  }

  completeTask(taskId: string): Promise<SalesTask> {
    return this.request(
      "POST",
      `/api/v1/crm/tasks/${taskId}/done`,
      salesTaskSchema,
    );
  }

  reopenTask(taskId: string): Promise<SalesTask> {
    return this.request(
      "POST",
      `/api/v1/crm/tasks/${taskId}/reopen`,
      salesTaskSchema,
    );
  }

  // ---- timeline ----------------------------------------------------------

  getTimeline(
    subjectType: ActivitySubject,
    subjectId: string,
    filters: {
      limit?: number;
      offset?: number;
      /** Only this subject's activities that name the given person — the
       *  stakeholder profile's Activity group (doc 04). */
      related_contact_id?: string;
    } = {},
  ): Promise<ActivityPage> {
    return this.request(
      "GET",
      `/api/v1/crm/timeline${qs({ subject_type: subjectType, subject_id: subjectId, ...filters })}`,
      activityPageSchema,
    );
  }

  // ---- documents ---------------------------------------------------------

  listDocuments(
    scopeType: DocumentScope,
    scopeId: string,
    filters: {
      limit?: number;
      offset?: number;
      category?: DocumentCategory;
    } = {},
  ): Promise<DocumentPage> {
    return this.request(
      "GET",
      `/api/v1/crm/documents${qs({ scope_type: scopeType, scope_id: scopeId, ...filters })}`,
      documentPageSchema,
    );
  }

  async uploadDocument(
    scopeType: DocumentScope,
    scopeId: string,
    file: File,
    category?: DocumentCategory,
  ): Promise<CrmDocument> {
    // Multipart body, so this cannot go through the JSON transport above.
    const fetchImpl = this.crmOptions.fetchImpl ?? fetch;
    const headers: Record<string, string> = { Accept: "application/json" };
    const token = await this.crmOptions.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    const form = new FormData();
    form.set("file", file);
    form.set("scope_type", scopeType);
    form.set("scope_id", scopeId);
    if (category) form.set("category", category);
    const response = await fetchImpl(
      `${this.crmOptions.baseUrl}/api/v1/crm/documents`,
      {
        method: "POST",
        headers,
        body: form,
      },
    );
    const json: unknown = await response.json().catch(() => null);
    if (!response.ok) {
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
    return crmDocumentSchema.parse(json);
  }

  async downloadDocument(documentId: string): Promise<Blob> {
    const fetchImpl = this.crmOptions.fetchImpl ?? fetch;
    const headers: Record<string, string> = {};
    const token = await this.crmOptions.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetchImpl(
      `${this.crmOptions.baseUrl}/api/v1/crm/documents/${documentId}/content`,
      { headers },
    );
    if (!response.ok)
      throw new Error(`download failed: HTTP ${response.status}`);
    return response.blob();
  }

  /** The stored portrait, as bytes - the same authenticated pass-through as a
      document download; the bucket is never exposed to the browser. */
  async contactPhoto(contactId: string): Promise<Blob> {
    const fetchImpl = this.crmOptions.fetchImpl ?? fetch;
    const headers: Record<string, string> = {};
    const token = await this.crmOptions.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    const response = await fetchImpl(
      `${this.crmOptions.baseUrl}/api/v1/crm/contacts/${contactId}/photo`,
      { headers },
    );
    if (!response.ok) throw new Error(`photo failed: HTTP ${response.status}`);
    return response.blob();
  }

  deleteDocument(documentId: string): Promise<void> {
    return this.requestVoid("DELETE", `/api/v1/crm/documents/${documentId}`);
  }

  // ---- notes -------------------------------------------------------------

  listNotes(
    parent: {
      lead_id?: string;
      account_id?: string;
      opportunity_id?: string;
    },
    paging: { limit?: number; offset?: number } = {},
  ): Promise<NotePage> {
    return this.request(
      "GET",
      `/api/v1/crm/notes${qs({ ...parent, ...paging })}`,
      notePageSchema,
    );
  }

  createNote(payload: Record<string, unknown>): Promise<CrmNote> {
    return this.request("POST", "/api/v1/crm/notes", crmNoteSchema, {
      body: payload,
    });
  }

  updateNote(
    noteId: string,
    payload: { expected_version: number; body: string },
  ): Promise<CrmNote> {
    return this.request("PATCH", `/api/v1/crm/notes/${noteId}`, crmNoteSchema, {
      body: payload,
    });
  }

  deleteNote(noteId: string): Promise<void> {
    return this.requestVoid("DELETE", `/api/v1/crm/notes/${noteId}`);
  }

  // ---- lead scoring reads ------------------------------------------------

  /**
   * Contract B7 — the lead page's own block, under ONE template.
   *
   * `null` means this lead has never been scored under that template: an empty
   * state ("Not scored with this template yet"), not a zero. Omitting
   * `templateId` asks under the caller's own current selection.
   */
  getLeadAssessment(
    leadId: string,
    templateId?: string | null,
  ): Promise<LeadAssessment | null> {
    return this.request(
      "GET",
      `/api/v1/leads/${leadId}/assessment${templateQuery(templateId)}`,
      leadAssessmentSchema.nullable(),
    );
  }

  /** Contract B8 — the criterion rows behind the score, per axis. */
  getLeadAssessmentDetail(
    leadId: string,
    templateId?: string | null,
  ): Promise<AssessmentDetail | null> {
    return this.request(
      "GET",
      `/api/v1/leads/${leadId}/assessment/detail${templateQuery(templateId)}`,
      assessmentDetailSchema.nullable(),
    );
  }

  // ---- score templates (B1-B6) ------------------------------------------

  /** B1. The company's frames, the system default always first. */
  listScoreTemplates(): Promise<ScoreTemplateSummary[]> {
    return this.request(
      "GET",
      "/api/v1/lead-scoring/templates",
      z.array(scoreTemplateSummarySchema),
    );
  }

  /**
   * B2. One template in full. `null` asks for the system default, which has no
   * id — the same null that means "default" everywhere else in this API.
   */
  getScoreTemplate(templateId: string | null): Promise<ScoreTemplate> {
    return this.request(
      "GET",
      templateId
        ? `/api/v1/lead-scoring/templates/${templateId}`
        : "/api/v1/lead-scoring/templates/default",
      scoreTemplateSchema,
    );
  }

  /** B3. Creating one changes nobody's selection, including the creator's. */
  createScoreTemplate(input: {
    name: string;
    definition: ScoreTemplateDefinition;
    copied_from?: string | null;
  }): Promise<ScoreTemplate> {
    return this.request(
      "POST",
      "/api/v1/lead-scoring/templates",
      scoreTemplateSchema,
      { body: input },
    );
  }

  /**
   * B4. 403 unless the caller owns it or manages whoever does; 409 when the
   * name is taken, or when `expected_fingerprint` no longer matches — somebody
   * else edited it since this form was opened.
   */
  updateScoreTemplate(
    templateId: string,
    input: {
      name: string;
      definition: ScoreTemplateDefinition;
      expected_fingerprint?: string | null;
    },
  ): Promise<ScoreTemplate> {
    return this.request(
      "PUT",
      `/api/v1/lead-scoring/templates/${templateId}`,
      scoreTemplateSchema,
      { body: input },
    );
  }

  /** B4. Takes every score computed under it with it (FR-011a). */
  deleteScoreTemplate(templateId: string): Promise<void> {
    return this.requestVoid(
      "DELETE",
      `/api/v1/lead-scoring/templates/${templateId}`,
    );
  }

  /** B5. The caller's own choice, and one deleted-template notice at most. */
  getTemplateSelection(): Promise<TemplateSelection> {
    return this.request(
      "GET",
      "/api/v1/lead-scoring/templates/selection",
      templateSelectionSchema,
    );
  }

  /** B6. Whose choice this is comes from the session, not from the body. */
  setTemplateSelection(templateId: string | null): Promise<TemplateSelection> {
    return this.request(
      "PUT",
      "/api/v1/lead-scoring/templates/selection",
      templateSelectionSchema,
      { body: { template_id: templateId } },
    );
  }

  getLeadScore(leadId: string): Promise<ScoringResult> {
    return this.request(
      "GET",
      `/api/v1/lead-scoring/leads/${leadId}/score`,
      scoringResultSchema,
    );
  }

  getLeadScores(leadIds: string[]): Promise<Record<string, ScoringResult>> {
    if (leadIds.length === 0) return Promise.resolve({});
    return this.request(
      "GET",
      `/api/v1/lead-scoring/scores${qs({ lead_ids: leadIds.join(",") })}`,
      z.record(scoringResultSchema),
    );
  }

  /** Read-only and identical for everyone in the tenant; safe to cache per page. */
  getIdealCustomerProfile(): Promise<IdealCustomerProfile> {
    return this.request(
      "GET",
      "/api/v1/lead-scoring/icp",
      idealCustomerProfileSchema,
    );
  }

  getLeadScoreHistory(leadId: string): Promise<ScoringResult[]> {
    return this.request(
      "GET",
      `/api/v1/lead-scoring/leads/${leadId}/history`,
      z.array(scoringResultSchema),
    );
  }

  /**
   * Polled while a lead page is open. One indexed row lookup, no scorecard.
   */
  getLeadScoringActivity(leadId: string): Promise<LeadScoringActivity> {
    return this.request(
      "GET",
      `/api/v1/lead-scoring/leads/${leadId}/activity`,
      leadScoringActivitySchema,
    );
  }

  /**
   * The lead's scoring state, pushed as it changes.
   *
   * Over `fetch` rather than `EventSource`, which cannot send the Authorization
   * header this API requires - the same reason the chat turn stream does it
   * this way. The caller reads it as an async iterable and stops by breaking
   * out, which aborts the request.
   */
  async *streamLeadScoring(
    leadId: string,
    signal?: AbortSignal,
  ): AsyncGenerator<LeadScoringEvent> {
    const fetchImpl = this.crmOptions.fetchImpl ?? fetch;
    const headers: Record<string, string> = { Accept: "text/event-stream" };
    const token = await this.crmOptions.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;

    const response = await fetchImpl(
      `${this.crmOptions.baseUrl}/api/v1/lead-scoring/leads/${leadId}/events`,
      { method: "GET", headers, signal },
    );
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
        const event = parseScoringEvent(block);
        if (event) yield event;
        boundary = buffer.indexOf("\n\n");
      }
    }
  }

  /**
   * Contract A3 — ask for a re-score. Queues the debt; the worker's rescore
   * consumer is the only thing that opens a run, so the answer is 202 and the
   * new score arrives over the stream up to a debounce later. 409 means a run
   * is already working on this lead, which will read the same evidence.
   */
  requestRescore(
    leadId: string,
    templateId?: string | null,
  ): Promise<{ queued: boolean }> {
    return this.request(
      "POST",
      `/api/v1/leads/${leadId}/assessment/rescore`,
      z.object({ queued: z.boolean() }),
      { body: templateId === undefined ? {} : { template_id: templateId } },
    );
  }

  // ---- people profile: private notes, memorable dates, the bell ----------

  /** My own notes on this person — the server only ever returns mine (RLS). */
  listPrivateNotes(contactId: string): Promise<PrivateNote[]> {
    return this.request(
      "GET",
      `/api/v1/crm/contacts/${contactId}/private-notes`,
      z.array(privateNoteSchema),
    );
  }

  createPrivateNote(contactId: string, body: string): Promise<PrivateNote> {
    return this.request(
      "POST",
      `/api/v1/crm/contacts/${contactId}/private-notes`,
      privateNoteSchema,
      { body: { body } },
    );
  }

  updatePrivateNote(
    contactId: string,
    noteId: string,
    body: string,
  ): Promise<PrivateNote> {
    return this.request(
      "PATCH",
      `/api/v1/crm/contacts/${contactId}/private-notes/${noteId}`,
      privateNoteSchema,
      { body: { body } },
    );
  }

  deletePrivateNote(contactId: string, noteId: string): Promise<void> {
    return this.requestVoid(
      "DELETE",
      `/api/v1/crm/contacts/${contactId}/private-notes/${noteId}`,
    );
  }

  /** Shared dates of the whole team plus my private ones. */
  /** Trợ lý còn đang đọc hồ sơ này không. */
  getExtractionStatus(contactId: string): Promise<ExtractionStatus> {
    return this.request(
      "GET",
      `/api/v1/crm/contacts/${contactId}/reminders/extraction`,
      extractionStatusSchema,
    );
  }

  listReminders(contactId: string): Promise<ContactReminder[]> {
    return this.request(
      "GET",
      `/api/v1/crm/contacts/${contactId}/reminders`,
      z.array(reminderSchema),
    );
  }

  createReminder(
    contactId: string,
    payload: {
      title: string;
      kind: ReminderKind;
      month: number;
      day: number;
      year_hint?: number | null;
      recurrence?: "yearly" | "once";
      lead_days?: number;
      visibility?: ReminderVisibility;
    },
  ): Promise<ContactReminder> {
    return this.request(
      "POST",
      `/api/v1/crm/contacts/${contactId}/reminders`,
      reminderSchema,
      { body: payload },
    );
  }

  /** Only the reminder's owner may edit; dismiss travels as `status`. */
  updateReminder(
    contactId: string,
    reminderId: string,
    payload: {
      title?: string;
      month?: number;
      day?: number;
      lead_days?: number;
      status?: "active" | "dismissed";
    },
  ): Promise<ContactReminder> {
    return this.request(
      "PATCH",
      `/api/v1/crm/contacts/${contactId}/reminders/${reminderId}`,
      reminderSchema,
      { body: payload },
    );
  }

  deleteReminder(contactId: string, reminderId: string): Promise<void> {
    return this.requestVoid(
      "DELETE",
      `/api/v1/crm/contacts/${contactId}/reminders/${reminderId}`,
    );
  }

  /** The bell: the latest page plus the unread count, RLS-narrowed to me. */
  getNotifications(): Promise<BellPage> {
    return this.request("GET", "/api/v1/crm/notifications", bellPageSchema);
  }

  markNotificationRead(notificationId: string): Promise<void> {
    return this.requestVoid(
      "POST",
      `/api/v1/crm/notifications/${notificationId}/read`,
    );
  }

  markAllNotificationsRead(): Promise<void> {
    return this.requestVoid("POST", "/api/v1/crm/notifications/read-all");
  }

  // ---- shared ------------------------------------------------------------

  private async requestVoid(
    method: "DELETE" | "POST" | "PATCH",
    path: string,
    // Some 204s still carry a request body - an edit that answers "nothing to
    // show you" rather than "nothing happened".
    options: { body?: unknown } = {},
  ): Promise<void> {
    const fetchImpl = this.crmOptions.fetchImpl ?? fetch;
    const headers: Record<string, string> = {};
    const token = await this.crmOptions.getAccessToken?.();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.body !== undefined)
      headers["Content-Type"] = "application/json";
    const response = await fetchImpl(`${this.crmOptions.baseUrl}${path}`, {
      method,
      headers,
      ...(options.body === undefined
        ? {}
        : { body: JSON.stringify(options.body) }),
    });
    if (!response.ok) {
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
  }
}

/** Heartbeat comments and unknown event names are skipped, not thrown on. */
function parseScoringEvent(block: string): LeadScoringEvent | null {
  const lines = block.split("\n");
  const type = lines.find((line) => line.startsWith("event: "))?.slice(7);
  const data = lines.find((line) => line.startsWith("data: "))?.slice(6);
  if (!type || !data) return null;

  const parsed = leadScoringEventSchema.safeParse({
    type,
    data: JSON.parse(data),
  });
  return parsed.success ? parsed.data : null;
}
