import { z } from "zod";
import type { ApiClient, ChatStreamEvent } from "./client";
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
export type PurchaseConfirmationMail = PurchasingSchemas["ConfirmationMail"];
export type PurchaseLateLine = PurchasingSchemas["LateLine"];
export type PurchaseAssistantTurn = PurchasingSchemas["AssistantTurnView"];
export type PurchasingMasterData = PurchasingSchemas["MasterDataView"];
export type PurchasingMasterImport = PurchasingSchemas["MasterImportView"];
export type PurchasingListChange = PurchasingSchemas["ListChange"];
export type PurchaseRfqMail = PurchasingSchemas["RfqMailView"];

type Answer<
  P extends keyof paths,
  M extends "get" | "post",
  S extends 200 | 201 | 202,
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

  private post<P extends keyof paths, S extends 200 | 201 | 202 = 200>(
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

  // ---- each drafted order followed (DW02 function 5) ----------------------

  recordBravoNo(
    caseId: string,
    poRef: string,
    bravoNo: string,
    caseVersion: number,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/po/{po_ref}/bravo-number">(
      `${BASE}/requests/${enc(caseId)}/po/${enc(poRef)}/bravo-number`,
      { case_version: caseVersion, bravo_no: bravoNo },
      idempotencyKey,
    );
  }

  /** The mails that confirm one of the case's orders, decided by code. */
  confirmationMails(caseId: string) {
    return this.get<"/api/v1/purchasing/requests/{case_id}/po/confirmations">(
      `${BASE}/requests/${enc(caseId)}/po/confirmations`,
    );
  }

  readConfirmation(
    caseId: string,
    messageId: string,
    caseVersion: number,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/po/confirmations/from-mail/{message_id}">(
      `${BASE}/requests/${enc(caseId)}/po/confirmations/from-mail/${enc(messageId)}`,
      { case_version: caseVersion },
      idempotencyKey,
    );
  }

  acceptConfirmation(
    caseId: string,
    poRef: string,
    caseVersion: number,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/po/{po_ref}/confirmation/accept">(
      `${BASE}/requests/${enc(caseId)}/po/${enc(poRef)}/confirmation/accept`,
      { case_version: caseVersion },
      idempotencyKey,
    );
  }

  recordReceipt(
    caseId: string,
    poRef: string,
    receipt: { line_no: number; quantity: string; received_on: string },
    caseVersion: number,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/requests/{case_id}/po/{po_ref}/receipts">(
      `${BASE}/requests/${enc(caseId)}/po/${enc(poRef)}/receipts`,
      { case_version: caseVersion, ...receipt },
      idempotencyKey,
    );
  }

  /** Every line past its date with less arrived than ordered. */
  lateLines() {
    return this.get<"/api/v1/purchasing/orders/late">(`${BASE}/orders/late`);
  }

  // ---- Hỏi đáp DW2 (DW02 function 6) ---------------------------------------

  /** A status question as it happens: what DW2 is doing, then its answer. */
  assistantStream(
    question: string,
    sessionId: string | null,
    idempotencyKey: string,
    onEvent: (event: ChatStreamEvent) => void,
    signal?: AbortSignal,
  ) {
    return this.client.chatStream<PurchasingSchemas["AssistantAnswerView"]>(
      `${BASE}/assistant/ask/stream`,
      { body: { question, session_id: sessionId }, idempotencyKey, signal },
      onEvent,
    );
  }

  assistantSessions() {
    return this.get<"/api/v1/purchasing/assistant/sessions">(
      `${BASE}/assistant/sessions`,
    );
  }

  assistantSession(sessionId: string) {
    return this.get<"/api/v1/purchasing/assistant/sessions/{session_id}">(
      `${BASE}/assistant/sessions/${enc(sessionId)}`,
    );
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

  // ---- rfq mail -----------------------------------------------------------

  /** "Gửi từ hộp thư của tôi": the RFQ goes out from the caller's own mailbox. */
  sendRfq(caseId: string, supplierCode: string, idempotencyKey: string) {
    return this.post<
      "/api/v1/purchasing/requests/{case_id}/rfq/{supplier_code}/send",
      202
    >(
      `${BASE}/requests/${enc(caseId)}/rfq/${enc(supplierCode)}/send`,
      undefined,
      idempotencyKey,
    );
  }

  /** The mailbox's mails code tied to this case's RFQs (sender asked, PR named). */
  rfqReplies(caseId: string) {
    return this.get<"/api/v1/purchasing/requests/{case_id}/rfq/replies">(
      `${BASE}/requests/${enc(caseId)}/rfq/replies`,
    );
  }

  rfqMails(caseId: string) {
    return this.get<"/api/v1/purchasing/requests/{case_id}/rfq/mails">(
      `${BASE}/requests/${enc(caseId)}/rfq/mails`,
    );
  }

  // ---- master data --------------------------------------------------------

  /** The lists in force, whose they are, what waits, the latest uploads. */
  masterData() {
    return this.get<"/api/v1/purchasing/master-data">(`${BASE}/master-data`);
  }

  /** The workbook to fill in: a guide and one sheet per list. */
  async masterTemplate(): Promise<{ blob: Blob; filename: string }> {
    const response = await this.client.rawRequest(
      "GET",
      `${BASE}/master-data/template.xlsx`,
    );
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const filename =
      /filename="([^"]+)"/.exec(disposition)?.[1] ?? "du-lieu-chu-dw2.xlsx";
    return { blob: await response.blob(), filename };
  }

  /** A filled workbook, as base64; the worker reads it, the API never opens it. */
  uploadMasterData(
    fileName: string,
    contentB64: string,
    idempotencyKey: string,
  ) {
    return this.post<"/api/v1/purchasing/master-data/imports", 202>(
      `${BASE}/master-data/imports`,
      { file_name: fileName, content_b64: contentB64 },
      idempotencyKey,
    );
  }

  masterImport(importId: string) {
    return this.get<"/api/v1/purchasing/master-data/imports/{import_id}">(
      `${BASE}/master-data/imports/${enc(importId)}`,
    );
  }

  /** "Gửi duyệt": the head's applies at once, anyone else's waits for the head. */
  submitMasterData(importId: string, idempotencyKey: string) {
    return this.post<"/api/v1/purchasing/master-data/imports/{import_id}/submit">(
      `${BASE}/master-data/imports/${enc(importId)}/submit`,
      undefined,
      idempotencyKey,
    );
  }
}
