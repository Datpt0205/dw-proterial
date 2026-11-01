import { z } from "zod";
import type { ApiClient } from "./client";
import type { components, paths } from "./generated/purchasing";

/**
 * The Purchasing context's routes (`/api/v1/purchasing/*`, DW2 Mua hàng),
 * typed from the OpenAPI snapshot through `generated/purchasing.d.ts` and
 * nothing else, as `SalesApi` is: a field the API adds or drops reaches the
 * screens as a compile error.
 *
 * Every mutation takes an `Idempotency-Key` minted by the caller once per
 * press (ui-quality §3) and, where it moves a case, the `case_version` the
 * person saw: a stale one is refused (409). Approving is never here: it is
 * the platform's `ApiClient.decideApproval`.
 */
export type PurchasingSchemas = components["schemas"];

export type PurchaseCase = PurchasingSchemas["PurchaseCase"];
export type PurchaseCaseStatus = PurchasingSchemas["CaseStatus"];
export type PurchaseInboxItem = PurchasingSchemas["InboxItem"];
export type PurchaseFindingCode = PurchasingSchemas["PurchaseFindingCode"];
export type PurchaseRequestDraft = PurchasingSchemas["DraftView"];
export type PurchaseMyRequest = PurchasingSchemas["MyRequest"];
export type PurchaseOfferForm = PurchasingSchemas["OfferForm"];
export type PurchaseChoice = PurchasingSchemas["Choice"];
export type PurchaseComparison = PurchasingSchemas["ComparisonView"];
export type PurchaseSwitches = PurchasingSchemas["SwitchesView"];
export type PurchaseStepLevel = PurchasingSchemas["StepLevelView"];
export type PurchaseAutomationStep = PurchasingSchemas["AutomationStep"];
export type PurchaseAutomationLevel = PurchasingSchemas["AutomationLevel"];
export type PurchasingRuleKey = PurchasingSchemas["PurchasingRuleKey"];
export type PurchasingRules = PurchasingSchemas["PurchasingRulesView"];
export type PurchasingRuleVersion =
  PurchasingSchemas["PurchasingRuleVersionView"];
export type PurchasingWordsDraft = PurchasingSchemas["WordsDraft"];

type Answer<
  P extends keyof paths,
  M extends "get" | "post",
  S extends 200 | 201,
> = paths[P][M] extends {
  responses: { [K in S]: { content: { "application/json": infer R } } };
}
  ? R
  : never;

/** Accepts what the server answered; the generated type is the contract. */
function shaped<T>(): z.ZodType<T> {
  return z.custom<T>(() => true);
}

const enc = encodeURIComponent;
const BASE = "/api/v1/purchasing";

export class PurchasingApi {
  constructor(private readonly client: ApiClient) {}

  private get<P extends keyof paths>(
    path: string,
  ): Promise<Answer<P, "get", 200>> {
    return this.client.request("GET", path, shaped<Answer<P, "get", 200>>());
  }

  private post<P extends keyof paths, S extends 200 | 201 = 200>(
    path: string,
    body: unknown,
    idempotencyKey?: string,
  ): Promise<Answer<P, "post", S>> {
    return this.client.request("POST", path, shaped<Answer<P, "post", S>>(), {
      body,
      idempotencyKey,
    });
  }

  // ---- cases --------------------------------------------------------------

  /** One page of cases, newest first; a requester's own only (the server narrows). */
  cases(before: { at: string; id: string } | null = null, limit = 50) {
    const query = new URLSearchParams({ limit: String(limit) });
    if (before) {
      query.set("before_at", before.at);
      query.set("before_id", before.id);
    }
    return this.get<"/api/v1/purchasing/requests">(`${BASE}/requests?${query}`);
  }

  case(caseId: string) {
    return this.get<"/api/v1/purchasing/requests/{case_id}">(
      `${BASE}/requests/${enc(caseId)}`,
    );
  }

  /** A request a buyer types from paper or a form, with its own number. */
  submitForm(
    request: PurchasingSchemas["PurchaseRequest-Input"],
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests", 201>(
      `${BASE}/requests`,
      request,
      idempotencyKey,
    );
  }

  /** What a send would stamp: the cross-check and the tier, nothing stored. */
  check(caseId: string) {
    return this.get<"/api/v1/purchasing/requests/{case_id}/check">(
      `${BASE}/requests/${enc(caseId)}/check`,
    );
  }

  /** "Đã xem": a buyer read a request DW2 opened while its switch asks a person. */
  review(caseId: string, caseVersion: number, idempotencyKey: string) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/review">(
      `${BASE}/requests/${enc(caseId)}/review`,
      { case_version: caseVersion },
      idempotencyKey,
    );
  }

  submit(caseId: string, caseVersion: number, idempotencyKey: string) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/submit">(
      `${BASE}/requests/${enc(caseId)}/submit`,
      { case_version: caseVersion },
      idempotencyKey,
    );
  }

  /**
   * The RFQs of an approved request: to the suppliers the master data lists,
   * and to those the buyer names for a line (a line nobody is listed for).
   */
  draftRfq(
    caseId: string,
    caseVersion: number,
    idempotencyKey: string,
    suppliers: PurchaseChoice[] = [],
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/rfq">(
      `${BASE}/requests/${enc(caseId)}/rfq`,
      { case_version: caseVersion, suppliers },
      idempotencyKey,
    );
  }

  /** A buyer's own words for one supplier's RFQ (DW2 sends nothing). */
  writeRfq(
    caseId: string,
    supplierCode: string,
    words: { subject: string; body: string },
    caseVersion: number,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/rfq/{supplier_code}">(
      `${BASE}/requests/${enc(caseId)}/rfq/${enc(supplierCode)}`,
      { case_version: caseVersion, ...words },
      idempotencyKey,
    );
  }

  /** The suppliers the company knows, by code and name, to name one for a line. */
  suppliers() {
    return this.get<"/api/v1/purchasing/suppliers">(`${BASE}/suppliers`);
  }

  recordOffer(
    caseId: string,
    caseVersion: number,
    offer: PurchaseOfferForm,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/offers">(
      `${BASE}/requests/${enc(caseId)}/offers`,
      { case_version: caseVersion, offer },
      idempotencyKey,
    );
  }

  /** A supplier's reply in the mailbox, read into offers for the lines it was asked. */
  readOfferMail(
    caseId: string,
    messageId: string,
    caseVersion: number,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/offers/from-mail/{message_id}">(
      `${BASE}/requests/${enc(caseId)}/offers/from-mail/${enc(messageId)}`,
      { case_version: caseVersion },
      idempotencyKey,
    );
  }

  comparison(caseId: string) {
    return this.get<"/api/v1/purchasing/requests/{case_id}/comparison">(
      `${BASE}/requests/${enc(caseId)}/comparison`,
    );
  }

  select(
    caseId: string,
    caseVersion: number,
    choices: PurchaseChoice[],
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/selection">(
      `${BASE}/requests/${enc(caseId)}/selection`,
      { case_version: caseVersion, choices },
      idempotencyKey,
    );
  }

  draftOrders(caseId: string, caseVersion: number, idempotencyKey: string) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/po">(
      `${BASE}/requests/${enc(caseId)}/po`,
      { case_version: caseVersion },
      idempotencyKey,
    );
  }

  /** The Bravo import file the case's stamp draws, as the server named it. */
  async bravoFile(caseId: string): Promise<{ blob: Blob; filename: string }> {
    const response = await this.client.rawRequest(
      "GET",
      `${BASE}/requests/${enc(caseId)}/po/bravo.xlsx`,
    );
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const filename =
      /filename="([^"]+)"/.exec(disposition)?.[1] ?? "bravo.xlsx";
    return { blob: await response.blob(), filename };
  }

  // ---- a requester's own --------------------------------------------------

  /** "Tôi cần mua…": the model's draft of the words, nothing stored. */
  draftMine(words: string) {
    return this.post<"/api/v1/purchasing/requests/mine/draft">(
      `${BASE}/requests/mine/draft`,
      { words },
    );
  }

  sendMine(request: PurchaseMyRequest, idempotencyKey: string) {
    return this.post<"/api/v1/purchasing/requests/mine", 201>(
      `${BASE}/requests/mine`,
      request,
      idempotencyKey,
    );
  }

  // ---- mailbox ------------------------------------------------------------

  mailbox() {
    return this.get<"/api/v1/purchasing/mail">(`${BASE}/mail`);
  }

  readMail(messageId: string, idempotencyKey: string) {
    return this.post<"/api/v1/purchasing/mail/{message_id}/read">(
      `${BASE}/mail/${enc(messageId)}/read`,
      undefined,
      idempotencyKey,
    );
  }

  // ---- settings -----------------------------------------------------------

  switches() {
    return this.get<"/api/v1/purchasing/automation">(`${BASE}/automation`);
  }

  rules() {
    return this.get<"/api/v1/purchasing/rules">(`${BASE}/rules`);
  }

  /** "Hạn mức trưởng phòng lên 50 triệu": the model's draft, the platform's checks. */
  ruleInWords(
    key: PurchasingRuleKey,
    request: string,
    focus: string | null = null,
  ) {
    return this.post<"/api/v1/purchasing/rules/{key}/words">(
      `${BASE}/rules/${enc(key)}/words`,
      { request, focus },
    );
  }

  proposeRules(
    key: PurchasingRuleKey,
    document: Record<string, unknown>,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/rules/{key}/versions">(
      `${BASE}/rules/${enc(key)}/versions`,
      { document },
      idempotencyKey,
    );
  }
}
