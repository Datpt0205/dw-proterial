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

  // ---- overview and work --------------------------------------------------

  overview() {
    return this.get<"/api/v1/sales/overview">("/api/v1/sales/overview");
  }

  myWork() {
    return this.get<"/api/v1/sales/my-work">("/api/v1/sales/my-work");
  }

  // ---- inbox --------------------------------------------------------------

  inbox() {
    return this.get<"/api/v1/sales/inbox">("/api/v1/sales/inbox");
  }

  processMessage(messageId: string, key: string) {
    return this.post<"/api/v1/sales/inbox/{message_id}/process">(
      `/api/v1/sales/inbox/${enc(messageId)}/process`,
      undefined,
      key,
    );
  }

  processAll(key: string) {
    return this.post<"/api/v1/sales/inbox/process-all">(
      "/api/v1/sales/inbox/process-all",
      undefined,
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
}

/** A page of a PDF, or a sheet of a workbook: what the source route opens. */
export type SourceRegion = { page: number } | { sheet: string };

function regionQuery(region: SourceRegion): string {
  return "page" in region
    ? `?page=${region.page}`
    : `?sheet=${encodeURIComponent(region.sheet)}`;
}
