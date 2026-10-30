import type { CaseListActivity, SalesSchemas } from "@dw/api-client";
import { formatDate } from "../../../lib/dates";
import {
  ACTIVITY_FIELD,
  ACTIVITY_KIND,
  AI_STATE,
  ACTIVITY_REASON,
  ACTIVITY_RESULT,
  FIELD,
  INTENT_KIND,
  label,
  LANGUAGE,
  READ_ATTRIBUTE,
  READING_REASON,
  REPLY_KIND,
  ROUTING_REASON,
} from "./labels";
import { humanise, knownFieldWords } from "./rule-labels";

/**
 * What DW1's model steps did (slice 3), as the screens say it: the process
 * page's AI state per step, a case's "DW1 đã làm gì", and the activity
 * page's counts, each linking to the case list they stand for. The API sends
 * codes and the filter each count stands for; the words and the links are
 * built here, once.
 */

type ModelStep = SalesSchemas["ModelStep"];
type StepModel = SalesSchemas["StepModelView"];
type Entry = SalesSchemas["ActivityEntry"];
type Filter = SalesSchemas["ActivityFilter"];

/** Every model step the API names; one it adds fails to compile here. */
const MODEL_STEPS: Record<ModelStep, null> = {
  description_attributes: null,
  message_intent: null,
  rfq_extraction: null,
  reply_intent: null,
  request_handoff: null,
  layout_proposal: null,
  po_body_extraction: null,
};
export const MODEL_STEP_IDS = Object.keys(MODEL_STEPS) as ModelStep[];

/**
 * A model step's name: the words of its switch in the order rules
 * (`model_assist.<step>`), the one place it is named.
 */
export function modelStepLabel(step: ModelStep): string {
  return (
    knownFieldWords("sales_order_rules", `model_assist.${step}`)?.label ??
    humanise(step)
  );
}

/** On and passing, on and not passing (a person does it), or off. */
export function aiState(model: StepModel): keyof typeof AI_STATE {
  if (!model.enabled) return "off";
  return model.effective ? "on" : "failing";
}

// ------------------------------------------------------------- reasons --

const PER_FIELD = {
  not_found: "không tìm thấy trong thư chữ mô hình chỉ ra",
  repeated: "chữ mô hình chỉ ra xuất hiện hơn một lần",
  unparsed: "DW1 không đọc được giá trị từ chữ đó",
} as const;

/** A field an activity row names, in words; null when no table names it. */
function knownField(field: string): string | null {
  return (
    (ACTIVITY_FIELD as Record<string, string>)[field] ??
    (FIELD as Record<string, string>)[field] ??
    (READ_ATTRIBUTE as Record<string, string>)[field] ??
    null
  );
}

const capitalised = (words: string) =>
  words ? words[0]!.toUpperCase() + words.slice(1) : words;

/**
 * Why DW1 left an item to a person, or refused a value inside one, in words;
 * null for a code no table names. A request reader's refusal per field
 * (`description_not_found`, `quote_due_unparsed`) is the field and what went
 * wrong; a hand-off's refusal is the field alone.
 */
export function knownReason(code: string): string | null {
  const exact =
    ACTIVITY_REASON[code] ??
    (READING_REASON as Record<string, string>)[code] ??
    (ROUTING_REASON as Record<string, string>)[code];
  if (exact) return capitalised(exact);
  const part = /^(.+)_(not_found|repeated|unparsed)$/.exec(code);
  const field = part ? knownField(part[1]!) : null;
  if (part && field)
    return `${field}: ${PER_FIELD[part[2] as keyof typeof PER_FIELD]}`;
  const named = knownField(code);
  return named ? `${named}: DW1 không giữ giá trị mô hình đọc` : null;
}

/** `knownReason`, or the code itself said as an unnamed reason. */
export function reasonLabel(code: string): string {
  return knownReason(code) ?? `Lý do khác (mã ${code})`;
}

// -------------------------------------------------------- case entries --

/** Kết quả: DW1 carried it, a person does it, or no answer came. */
export function entryResult(entry: Entry): keyof typeof ACTIVITY_RESULT {
  if (entry.check.result === "not_run") return "unavailable";
  return entry.handled_by === "dw1" ? "accepted" : "to_person";
}

/** Why it went to a person, in words; null when it did not. */
export function entryReason(entry: Entry): string | null {
  if (entry.check.reason_code) return reasonLabel(entry.check.reason_code);
  if (entry.kind === "to_person") return ACTIVITY_KIND.to_person;
  return null;
}

/** A value read's field, in words. */
export function producedField(field: string): string {
  return knownField(field) ?? humanise(field);
}

/** A value read, in words: a kind or a language by its label, a day as a day. */
export function producedValue(
  step: ModelStep,
  field: string,
  value: string,
): string {
  if (field === "kind")
    return label(step === "reply_intent" ? REPLY_KIND : INTENT_KIND, value);
  if (field === "language") return label(LANGUAGE, value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return formatDate(value);
  return value;
}

// ---------------------------------------------- the case list's filter --

/** The case list parameters a count on the activity page stands for. */
export const ACTIVITY_PARAMS = [
  "step",
  "handled_by",
  "result",
  "reason_code",
  "lane",
  "from",
  "to",
] as const;

/**
 * The activity filter a list's URL carries, as the API takes it; null when
 * it carries none. Passed on whole: the server refuses (422) one that names
 * no step or no window, and the list draws that refusal.
 */
export function activityFromUrl(
  params: URLSearchParams,
): CaseListActivity | null {
  const found: Record<string, string> = {};
  for (const name of ACTIVITY_PARAMS) {
    const value = params.get(name);
    if (value) found[name] = value;
  }
  return Object.keys(found).length ? (found as CaseListActivity) : null;
}

/**
 * The case list a count stands for: its lane's list, every tab (a count
 * covers closed cases too), narrowed by the filter the server served with it.
 */
export function activityHref(lane: "order" | "quote", filter: Filter): string {
  const query = new URLSearchParams({ tab: "all" });
  for (const name of ACTIVITY_PARAMS) {
    const value = filter[name];
    if (value) query.set(name, value);
  }
  return `/sales/${lane === "order" ? "orders" : "quotes"}?${query}`;
}

const OUTCOME: Record<string, string> = {
  "handled_by:dw1": "DW1 làm",
  "handled_by:person": ACTIVITY_RESULT.to_person,
  "result:accepted": ACTIVITY_RESULT.accepted,
  "result:refused": "Kiểm tra không nhận",
  "result:unavailable": ACTIVITY_RESULT.unavailable,
};

/** "Đọc mô tả hàng… · Chuyển cho người · 17/10/2026 – 23/10/2026". */
export function describeActivity(filter: CaseListActivity): string {
  const parts: string[] = [];
  if (filter.step) parts.push(modelStepLabel(filter.step));
  if (filter.handled_by)
    parts.push(OUTCOME[`handled_by:${filter.handled_by}`] ?? filter.handled_by);
  if (filter.result)
    parts.push(OUTCOME[`result:${filter.result}`] ?? filter.result);
  if (filter.reason_code) parts.push(reasonLabel(filter.reason_code));
  if (filter.from || filter.to)
    parts.push(`${formatDate(filter.from)} – ${formatDate(filter.to)}`);
  return parts.join(" · ");
}
