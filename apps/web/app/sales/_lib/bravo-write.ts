import { formatDate } from "../../../lib/dates";
import { formatQuantity } from "../../../lib/money";
import {
  BRAVO_WRITE_FIELD,
  BRAVO_WRITE_REASON,
  BRAVO_WRITE_UNMEASURED,
} from "./labels";

/** What a Bravo write changes on an SO line (`BravoLineWriteView.field`). */
export type BravoWriteField = keyof typeof BRAVO_WRITE_FIELD;

/**
 * A proposed Bravo write's value as a person reads it, on the order page's
 * panel and on the approval alike: a day, a quantity, or a cancel, whose
 * `after` reads "Hủy: <reason>" and whose `before` is the quantity it ends.
 */
export function bravoWriteValue(
  field: BravoWriteField,
  value: string | null,
): string {
  if (value === null) return "—";
  if (field === "confirmed_date") return formatDate(value);
  if (field === "cancel" && value.startsWith("Hủy")) return value;
  return formatQuantity(value);
}

/** DW's suffix on a refusal that came after an earlier send lost its answer. */
const LOST_ANSWER = " after a lost answer";
/** Codes the gateway ends with a value: `no_right_on_<column>`, `gateway_<status>`. */
const ENDS_WITH_VALUE = ["no_right_on", "gateway"] as const;
/** Codes whose detail is the Bravo screen rules' own names. */
const NAMES_RULES = new Set(["blocked", "undecided"]);

function reasonWords(said: string): string {
  const cut = said.indexOf(": ");
  const code = cut < 0 ? said : said.slice(0, cut);
  const detail = cut < 0 ? "" : said.slice(cut + 2);
  const words = (BRAVO_WRITE_REASON as Record<string, string>)[code];
  if (words !== undefined) {
    if (NAMES_RULES.has(code) && detail) return `${words}: ${detail}`;
    if (code === "unmeasured")
      return (
        (BRAVO_WRITE_UNMEASURED as Record<string, string>)[detail] ?? words
      );
    return words;
  }
  for (const prefix of ENDS_WITH_VALUE) {
    if (code.startsWith(`${prefix}_`)) {
      const value = code.slice(prefix.length + 1);
      return prefix === "no_right_on"
        ? `${BRAVO_WRITE_REASON[prefix]} ${value}`
        : BRAVO_WRITE_REASON[prefix];
    }
  }
  return `Lý do chưa có lời giải thích, báo IT kèm mã: ${said}`;
}

/**
 * Why a Bravo write was refused or stopped, as a person reads it: the
 * gateway's code in words (`BRAVO_WRITE_REASON`), and, where DW sent again
 * after an answer was lost, that Bravo may have written the first time.
 */
export function bravoWriteReason(reason: string): string {
  if (!reason.endsWith(LOST_ANSWER)) return reasonWords(reason);
  return `${reasonWords(reason.slice(0, -LOST_ANSWER.length))} (sau một lần gửi mất câu trả lời: có thể Bravo đã ghi, kiểm tra trong Bravo)`;
}

/**
 * One of a write's warnings or differences as a person reads it: a Bravo
 * screen rule's warning by the rule's own name, and what the gateway read
 * back differently (`pipeline._reconcile`) in words, at the table and row it
 * names.
 */
export function bravoWriteWarning(warning: string): string {
  if (warning === "read_back_failed")
    return "Không đọc lại được SO sau khi ghi để so";
  const notPlanned = /^a line not planned: Id (.+)$/.exec(warning);
  if (notPlanned)
    return `Bravo có thêm dòng DW1 không ghi (Id ${notPlanned[1]})`;
  const unchecked = /^(.+) \(could not check\)$/.exec(warning);
  if (unchecked) return `${unchecked[1]} (chưa kiểm được)`;
  const gone = /^(\S+#\d+): row gone$/.exec(warning);
  if (gone) return `${gone[1]}: dòng không còn trong Bravo`;
  const unfilled = /^(\S+#\d+)\.(\S+): not filled$/.exec(warning);
  if (unfilled) return `${unfilled[1]}, cột ${unfilled[2]}: Bravo chưa điền`;
  const differs = /^(\S+#\d+)\.(\S+)$/.exec(warning);
  if (differs)
    return `${differs[1]}, cột ${differs[2]}: Bravo lưu khác giá trị đã ghi`;
  return warning;
}
