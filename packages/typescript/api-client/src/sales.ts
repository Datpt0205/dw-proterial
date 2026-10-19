import { z } from "zod";
import type { ApiClient } from "./client";
import type { components, paths } from "./generated/sales";

/**
 * The Sales context's routes (`/api/v1/sales/*`), typed from the OpenAPI
 * snapshot through `generated/sales.d.ts` and nothing else: no type here is
 * written by hand, so a field the API adds or drops reaches the screens as a
 * compile error, not as a silent `undefined`.
 *
 * The response is not re-validated in the browser. The generated types are
 * the one owner of the shape; a zod mirror of forty views would be a second
 * one (failure-modes.md #2), and the API already validates what it answers
 * with Pydantic.
 *
 * Every mutation takes an `Idempotency-Key` minted by the caller once per
 * press (ui-quality §3) and the `case_version` the decision was made on.
 */
export type SalesSchemas = components["schemas"];

type Json<
  P extends keyof paths,
  M extends "get" | "post",
> = paths[P][M] extends {
  responses: { 200: { content: { "application/json": infer R } } };
}
  ? R
  : never;

/** A request the API queued (202): what it answers is the job, not the result. */
type Accepted<P extends keyof paths> = paths[P]["post"] extends {
  responses: { 202: { content: { "application/json": infer R } } };
}
  ? R
  : never;

type PutJson<P extends keyof paths> = paths[P]["put"] extends {
  responses: { 200: { content: { "application/json": infer R } } };
}
  ? R
  : never;

type Body<P extends keyof paths> = paths[P]["post"] extends {
  requestBody: { content: { "application/json": infer B } };
}
  ? B
  : never;

/** Accepts what the server answered; the generated type is the contract. */
function shaped<T>(): z.ZodType<T> {
  return z.custom<T>(() => true);
}

const enc = encodeURIComponent;

export type CaseChange = SalesSchemas["CaseChangeView"];
export type Hidden = SalesSchemas["Hidden"];
export type Amount = SalesSchemas["Amount"];
export type Words = SalesSchemas["Words"];
/** Every currency the Sales API names (one enum in OpenAPI). */
export type SalesCurrency = SalesSchemas["OrderCaseView"]["currency"];
export type Artifact = SalesSchemas["ArtifactView"];
/**
 * The platform approval a case waits on. The decision is made there
 * (`ApiClient.decideApproval`), never on a Sales route.
 */
export type PendingDecision = SalesSchemas["PendingDecisionView"];
/** A message's processing job (ticket 25): "DW xử lý" queues it, the worker runs it. */
export type ProcessingJob = SalesSchemas["ProcessingJobView"];

export class SalesApi {
  constructor(private readonly client: ApiClient) {}

  private get<P extends keyof paths>(path: string): Promise<Json<P, "get">> {
    return this.client.request("GET", path, shaped<Json<P, "get">>());
  }

  private post<P extends keyof paths>(
    path: string,
    body: unknown,
    idempotencyKey: string,
  ): Promise<Json<P, "post">> {
    return this.client.request("POST", path, shaped<Json<P, "post">>(), {
      body,
      idempotencyKey,
    });
  }

  private postAccepted<P extends keyof paths>(
    path: string,
    idempotencyKey: string,
  ): Promise<Accepted<P>> {
    return this.client.request("POST", path, shaped<Accepted<P>>(), {
      body: undefined,
      idempotencyKey,
    });
  }

  private put<P extends keyof paths>(
    path: string,
    body: unknown,
    idempotencyKey: string,
  ): Promise<PutJson<P>> {
    return this.client.request("PUT", path, shaped<PutJson<P>>(), {
      body,
      idempotencyKey,
    });
  }

  // ---- overview and work --------------------------------------------------

  overview() {
    return this.get<"/api/v1/sales/overview">("/api/v1/sales/overview");
  }

  /** One page of the caller's work, by due date then by when it came in. */
  myWorkPage(cursor: string | null = null, limit = 200) {
    const query = new URLSearchParams({ limit: String(limit) });
    if (cursor !== null) query.set("cursor", cursor);
    return this.get<"/api/v1/sales/my-work">(`/api/v1/sales/my-work?${query}`);
  }

  /**
   * Every page of the caller's work (ticket 24 pages it on the server). The
   * screens count across the whole list (overdue, due soon, per tab) and ask
   * whether one case is the caller's, so they read it all; what bounds it is
   * the caller's open work, no longer the workspace's history.
   * `next_cursor === null` is the only stop condition.
   */
  async myWork(): Promise<SalesSchemas["WorkItem"][]> {
    const items: SalesSchemas["WorkItem"][] = [];
    let cursor: string | null = null;
    do {
      const page: Json<"/api/v1/sales/my-work", "get"> =
        await this.myWorkPage(cursor);
      items.push(...page.items);
      cursor = page.next_cursor ?? null;
    } while (cursor !== null);
    return items;
  }

  // ---- inbox --------------------------------------------------------------

  inbox() {
    return this.get<"/api/v1/sales/inbox">("/api/v1/sales/inbox");
  }

  /** "DW xử lý": queues the message (202); the worker processes it, and
   * the inbox's `processing` says where it stands (ticket 25). */
  processMessage(messageId: string, key: string) {
    return this.postAccepted<"/api/v1/sales/inbox/{message_id}/process">(
      `/api/v1/sales/inbox/${enc(messageId)}/process`,
      key,
    );
  }

  /** "DW xử lý tất cả": one job per message still without a disposition. */
  processAll(key: string) {
    return this.postAccepted<"/api/v1/sales/inbox/process-all">(
      "/api/v1/sales/inbox/process-all",
      key,
    );
  }

  // ---- orders -------------------------------------------------------------

  orders() {
    return this.get<"/api/v1/sales/orders">("/api/v1/sales/orders");
  }

  order(caseId: string) {
    return this.get<"/api/v1/sales/orders/{case_id}">(
      `/api/v1/sales/orders/${enc(caseId)}`,
    );
  }

  /** The original as the reader saw it; the server records that it was served. */
  orderSource(caseId: string, attachmentId: string, region: SourceRegion) {
    return this.get<"/api/v1/sales/orders/{case_id}/source/{attachment_id}">(
      `/api/v1/sales/orders/${enc(caseId)}/source/${enc(attachmentId)}${regionQuery(region)}`,
    );
  }

  dispose(
    caseId: string,
    findingKey: string,
    body: Body<"/api/v1/sales/orders/{case_id}/findings/{finding_key}/disposition">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/orders/{case_id}/findings/{finding_key}/disposition">(
      `/api/v1/sales/orders/${enc(caseId)}/findings/${enc(findingKey)}/disposition`,
      body,
      key,
    );
  }

  /** One value a `value_uncertain` flagged, typed by Sales (ticket 15). */
  correctValue(
    caseId: string,
    findingKey: string,
    body: Body<"/api/v1/sales/orders/{case_id}/findings/{finding_key}/corrections">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/orders/{case_id}/findings/{finding_key}/corrections">(
      `/api/v1/sales/orders/${enc(caseId)}/findings/${enc(findingKey)}/corrections`,
      body,
      key,
    );
  }

  confirmMapping(
    caseId: string,
    lineNo: number,
    body: Body<"/api/v1/sales/orders/{case_id}/lines/{line_no}/mapping">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/orders/{case_id}/lines/{line_no}/mapping">(
      `/api/v1/sales/orders/${enc(caseId)}/lines/${lineNo}/mapping`,
      body,
      key,
    );
  }

  recordPcDate(
    caseId: string,
    lineNo: number,
    caseVersion: number,
    key: string,
  ) {
    return this.post<"/api/v1/sales/orders/{case_id}/lines/{line_no}/delivery-date">(
      `/api/v1/sales/orders/${enc(caseId)}/lines/${lineNo}/delivery-date`,
      { case_version: caseVersion },
      key,
    );
  }

  requestCorrection(caseId: string, caseVersion: number, key: string) {
    return this.post<"/api/v1/sales/orders/{case_id}/correction-request">(
      `/api/v1/sales/orders/${enc(caseId)}/correction-request`,
      { case_version: caseVersion },
      key,
    );
  }

  /** The customer answered the correction request without a corrected PO:
   * the review resumes, every finding as it stood (ticket 32). */
  resumeReview(caseId: string, caseVersion: number, key: string) {
    return this.post<"/api/v1/sales/orders/{case_id}/resume-review">(
      `/api/v1/sales/orders/${enc(caseId)}/resume-review`,
      { case_version: caseVersion },
      key,
    );
  }

  prepare(caseId: string, caseVersion: number, key: string) {
    return this.post<"/api/v1/sales/orders/{case_id}/prepare">(
      `/api/v1/sales/orders/${enc(caseId)}/prepare`,
      { case_version: caseVersion },
      key,
    );
  }

  bravoEntry(
    caseId: string,
    body: Body<"/api/v1/sales/orders/{case_id}/bravo-entry">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/orders/{case_id}/bravo-entry">(
      `/api/v1/sales/orders/${enc(caseId)}/bravo-entry`,
      body,
      key,
    );
  }

  /** "Gửi kiểm chéo lại": a new DW1 run raises the order's cross-check (ticket 14). */
  resendCrossCheck(caseId: string, caseVersion: number, key: string) {
    return this.post<"/api/v1/sales/orders/{case_id}/resend-cross-check">(
      `/api/v1/sales/orders/${enc(caseId)}/resend-cross-check`,
      { case_version: caseVersion },
      key,
    );
  }

  confirm(
    caseId: string,
    body: Body<"/api/v1/sales/orders/{case_id}/confirm">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/orders/{case_id}/confirm">(
      `/api/v1/sales/orders/${enc(caseId)}/confirm`,
      body,
      key,
    );
  }

  close(
    caseId: string,
    body: Body<"/api/v1/sales/orders/{case_id}/close">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/orders/{case_id}/close">(
      `/api/v1/sales/orders/${enc(caseId)}/close`,
      body,
      key,
    );
  }

  // ---- quotes -------------------------------------------------------------

  quotes() {
    return this.get<"/api/v1/sales/quotes">("/api/v1/sales/quotes");
  }

  screening() {
    return this.get<"/api/v1/sales/quotes/screening">(
      "/api/v1/sales/quotes/screening",
    );
  }

  quote(caseId: string) {
    return this.get<"/api/v1/sales/quotes/{case_id}">(
      `/api/v1/sales/quotes/${enc(caseId)}`,
    );
  }

  quoteSource(caseId: string, attachmentId: string, region: SourceRegion) {
    return this.get<"/api/v1/sales/quotes/{case_id}/source/{attachment_id}">(
      `/api/v1/sales/quotes/${enc(caseId)}/source/${enc(attachmentId)}${regionQuery(region)}`,
    );
  }

  /** The mail a model read the request from; served and recorded like a
   * page, which confirming a value read from it requires (ticket 29). */
  quoteMessageText(caseId: string) {
    return this.get<"/api/v1/sales/quotes/{case_id}/message-text">(
      `/api/v1/sales/quotes/${enc(caseId)}/message-text`,
    );
  }

  answerFinding(
    caseId: string,
    findingKey: string,
    body: Body<"/api/v1/sales/quotes/{case_id}/findings/{finding_key}/answer">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/quotes/{case_id}/findings/{finding_key}/answer">(
      `/api/v1/sales/quotes/${enc(caseId)}/findings/${enc(findingKey)}/answer`,
      body,
      key,
    );
  }

  ycbg(
    caseId: string,
    body: Body<"/api/v1/sales/quotes/{case_id}/ycbg">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/quotes/{case_id}/ycbg">(
      `/api/v1/sales/quotes/${enc(caseId)}/ycbg`,
      body,
      key,
    );
  }

  designSent(caseId: string, caseVersion: number, key: string) {
    return this.post<"/api/v1/sales/quotes/{case_id}/design-sent">(
      `/api/v1/sales/quotes/${enc(caseId)}/design-sent`,
      { case_version: caseVersion },
      key,
    );
  }

  specDiscussion(
    caseId: string,
    body: Body<"/api/v1/sales/quotes/{case_id}/spec-discussion">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/quotes/{case_id}/spec-discussion">(
      `/api/v1/sales/quotes/${enc(caseId)}/spec-discussion`,
      body,
      key,
    );
  }

  price(
    caseId: string,
    body: Body<"/api/v1/sales/quotes/{case_id}/price">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/quotes/{case_id}/price">(
      `/api/v1/sales/quotes/${enc(caseId)}/price`,
      body,
      key,
    );
  }

  submit(
    caseId: string,
    body: Body<"/api/v1/sales/quotes/{case_id}/submit">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/quotes/{case_id}/submit">(
      `/api/v1/sales/quotes/${enc(caseId)}/submit`,
      body,
      key,
    );
  }

  sent(caseId: string, caseVersion: number, key: string) {
    return this.post<"/api/v1/sales/quotes/{case_id}/sent">(
      `/api/v1/sales/quotes/${enc(caseId)}/sent`,
      { case_version: caseVersion },
      key,
    );
  }

  masterList(caseId: string, caseVersion: number, key: string) {
    return this.post<"/api/v1/sales/quotes/{case_id}/master-list">(
      `/api/v1/sales/quotes/${enc(caseId)}/master-list`,
      { case_version: caseVersion },
      key,
    );
  }

  decline(
    caseId: string,
    body: Body<"/api/v1/sales/quotes/{case_id}/decline">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/quotes/{case_id}/decline">(
      `/api/v1/sales/quotes/${enc(caseId)}/decline`,
      body,
      key,
    );
  }

  // ---- artifacts (ticket 06) -------------------------------------------------

  /** The case's stored files, and which kinds may be rendered now. */
  artifacts(kind: "order" | "quote", caseId: string) {
    return kind === "order"
      ? this.get<"/api/v1/sales/orders/{case_id}/artifacts">(
          `/api/v1/sales/orders/${enc(caseId)}/artifacts`,
        )
      : this.get<"/api/v1/sales/quotes/{case_id}/artifacts">(
          `/api/v1/sales/quotes/${enc(caseId)}/artifacts`,
        );
  }

  /** Render one kind from the case at the version the caller saw. */
  renderArtifact(
    kind: "order" | "quote",
    caseId: string,
    body: Body<"/api/v1/sales/orders/{case_id}/artifacts">,
    key: string,
  ) {
    return kind === "order"
      ? this.post<"/api/v1/sales/orders/{case_id}/artifacts">(
          `/api/v1/sales/orders/${enc(caseId)}/artifacts`,
          body,
          key,
        )
      : this.post<"/api/v1/sales/quotes/{case_id}/artifacts">(
          `/api/v1/sales/quotes/${enc(caseId)}/artifacts`,
          body,
          key,
        );
  }

  /**
   * The stored bytes, through the API with every gate it checks (scope, state,
   * case version, price scope for a price-bearing kind): never a link.
   */
  async downloadArtifact(
    kind: "order" | "quote",
    caseId: string,
    artifactId: string,
  ): Promise<Blob> {
    const response = await this.client.rawRequest(
      "GET",
      `/api/v1/sales/${kind === "order" ? "orders" : "quotes"}/${enc(caseId)}/artifacts/${enc(artifactId)}`,
    );
    return response.blob();
  }

  // ---- the assignee (ticket 17) ---------------------------------------------

  /** Who the case may be given to: members who work this kind of case here. */
  assignees(kind: "order" | "quote", caseId: string) {
    return kind === "order"
      ? this.get<"/api/v1/sales/orders/{case_id}/assignees">(
          `/api/v1/sales/orders/${enc(caseId)}/assignees`,
        )
      : this.get<"/api/v1/sales/quotes/{case_id}/assignees">(
          `/api/v1/sales/quotes/${enc(caseId)}/assignees`,
        );
  }

  /** The head gives the case to `assignee`, or to nobody when null. */
  reassign(
    kind: "order" | "quote",
    caseId: string,
    body: { assignee: string | null; case_version: number },
    key: string,
  ) {
    return kind === "order"
      ? this.put<"/api/v1/sales/orders/{case_id}/assignee">(
          `/api/v1/sales/orders/${enc(caseId)}/assignee`,
          body,
          key,
        )
      : this.put<"/api/v1/sales/quotes/{case_id}/assignee">(
          `/api/v1/sales/quotes/${enc(caseId)}/assignee`,
          body,
          key,
        );
  }

  // ---- master data (read-only mock) ----------------------------------------

  customers() {
    return this.get<"/api/v1/sales/master-data/customers">(
      "/api/v1/sales/master-data/customers",
    );
  }

  items() {
    return this.get<"/api/v1/sales/master-data/items">(
      "/api/v1/sales/master-data/items",
    );
  }

  convertList() {
    return this.get<"/api/v1/sales/master-data/convert-list">(
      "/api/v1/sales/master-data/convert-list",
    );
  }

  quotations() {
    return this.get<"/api/v1/sales/master-data/quotations">(
      "/api/v1/sales/master-data/quotations",
    );
  }

  lme() {
    return this.get<"/api/v1/sales/master-data/lme">(
      "/api/v1/sales/master-data/lme",
    );
  }

  bravoOrders() {
    return this.get<"/api/v1/sales/master-data/bravo-orders">(
      "/api/v1/sales/master-data/bravo-orders",
    );
  }

  openYcbg() {
    return this.get<"/api/v1/sales/master-data/open-ycbg">(
      "/api/v1/sales/master-data/open-ycbg",
    );
  }

  // ---- worker ---------------------------------------------------------------

  pause(reason: string | null, key: string) {
    return this.post<"/api/v1/sales/worker/pause">(
      "/api/v1/sales/worker/pause",
      { reason },
      key,
    );
  }

  resume(reason: string, key: string) {
    return this.post<"/api/v1/sales/worker/resume">(
      "/api/v1/sales/worker/resume",
      { reason },
      key,
    );
  }

  // ---- PO layouts (ticket 30) -----------------------------------------------

  layouts() {
    return this.get<"/api/v1/sales/layouts">("/api/v1/sales/layouts");
  }

  /** The form's cells, the pre-fill DW1 stamped, the approved layout if any. */
  layoutSource(messageId: string, attachmentId: string) {
    return this.get<"/api/v1/sales/layouts/source">(
      `/api/v1/sales/layouts/source?message_id=${enc(messageId)}&attachment_id=${enc(attachmentId)}`,
    );
  }

  /** What the reader reads with a mapping, and every check it fails. */
  previewLayout(body: Body<"/api/v1/sales/layouts/preview">, key: string) {
    return this.post<"/api/v1/sales/layouts/preview">(
      "/api/v1/sales/layouts/preview",
      body,
      key,
    );
  }

  proposeLayout(body: Body<"/api/v1/sales/layouts">, key: string) {
    return this.post<"/api/v1/sales/layouts">(
      "/api/v1/sales/layouts",
      body,
      key,
    );
  }

  // ---- a tenant's own rules (tickets 19, 38) ----------------------------------

  /** What applies per key, and every version the tenant holds, documents included. */
  rules() {
    return this.get<"/api/v1/sales/rules">("/api/v1/sales/rules");
  }

  /** The JSON Schema a proposal of the key is validated by (ticket 40). */
  ruleSchema(ruleKey: SalesSchemas["RuleKey"]) {
    return this.get<"/api/v1/sales/rules/{key}/schema">(
      `/api/v1/sales/rules/${enc(ruleKey)}/schema`,
    );
  }

  /** Every version of the key the platform released, newest first, whole. */
  rulePlatformDocuments(ruleKey: SalesSchemas["RuleKey"]) {
    return this.get<"/api/v1/sales/rules/{key}/platform">(
      `/api/v1/sales/rules/${enc(ruleKey)}/platform`,
    );
  }

  /**
   * Proposes a version of one key. It opens a `sales.rules` platform
   * approval, decided on `/approvals` by someone other than the proposer.
   */
  proposeRule(
    ruleKey: SalesSchemas["RuleKey"],
    body: Body<"/api/v1/sales/rules/{key}/versions">,
    key: string,
  ) {
    return this.post<"/api/v1/sales/rules/{key}/versions">(
      `/api/v1/sales/rules/${enc(ruleKey)}/versions`,
      body,
      key,
    );
  }
}

/** A page of a PDF, or a sheet of a workbook: what the source route opens. */
export type SourceRegion = { page: number } | { sheet: string };

function regionQuery(region: SourceRegion): string {
  return "page" in region
    ? `?page=${region.page}`
    : `?sheet=${encodeURIComponent(region.sheet)}`;
}
