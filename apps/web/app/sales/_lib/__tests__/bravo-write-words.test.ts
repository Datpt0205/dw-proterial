import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { bravoWriteReason, bravoWriteWarning } from "../bravo-write";
import {
  BRAVO_WRITE_CHECK,
  BRAVO_WRITE_REASON,
  BRAVO_WRITE_UNMEASURED,
} from "../labels";
import { SALES_REFUSALS } from "../../_meta/refusals";

const REPO = resolve(__dirname, "../../../../../..");
const read = (path: string) => readFileSync(resolve(REPO, path), "utf8");

/** Where a reason has no words: the code shown for IT, never alone. */
const NO_WORDS = /^Lý do chưa có lời giải thích/;

/**
 * Every literal reason the gateway, its token check, its target check and
 * DW's own settlement answer with, read from their source so a reason added
 * there without words here goes red (failure-modes #2: two copies disagree
 * loudly). f-strings are listed below with each value their Literal allows.
 */
function literalReasons(): string[] {
  const sources = [
    [
      "apps/bravo-gateway/src/dw_bravo_gateway/pipeline.py",
      /_RefusedError\(\s*"\w+",\s*"([^"]+)"/g,
    ],
    [
      "apps/bravo-gateway/src/dw_bravo_gateway/pipeline.py",
      /WriteResult\("\w+", (?:"\w+"|None), "([^"]+)"/g,
    ],
    [
      "packages/python/dw_bravo/src/dw_bravo/approval_token.py",
      /TokenRefusedError\("([^"]+)"\)/g,
    ],
    [
      "apps/bravo-gateway/src/dw_bravo_gateway/targets.py",
      /TargetRefusedError\("([^"]+)"\)/g,
    ],
    [
      "packages/python/dw_sales/src/dw_sales/application/bravo_line_writes.py",
      /"reason": "([^"]+)"/g,
    ],
  ] as const;
  const found = new Set<string>();
  for (const [path, pattern] of sources) {
    for (const match of read(path).matchAll(pattern)) found.add(match[1]!);
  }
  return [...found];
}

describe("a Bravo write's reason in words (DW1 review, ui)", () => {
  it("reads every literal reason the gateway and DW answer with", () => {
    const reasons = literalReasons();
    // The scan itself must see the reasons, or this test checks nothing.
    expect(reasons).toEqual(
      expect.arrayContaining([
        "target_changed",
        "expired",
        "target_unconfigured",
        "no_token_on_the_decision",
        "line_locked_or_could_not_check",
        "unmeasured: a cancel of a split line",
        "no_answer_after_send",
      ]),
    );
    for (const reason of reasons) {
      expect(bravoWriteReason(reason), reason).not.toMatch(NO_WORDS);
      expect(bravoWriteReason(reason), reason).not.toContain(reason);
    }
  });

  // The f-strings, with each value their Literal allows (`SwitchState`,
  // `CommandRight`, `LedgerStatus`) or a sample detail.
  it.each([
    ["write_kind_off", /đang tắt/],
    ["write_kind_paused", /tạm dừng/],
    ["command_right_denied", /không có quyền sửa SO/],
    ["command_right_unknown", /Chưa đọc được quyền/],
    ["approval_already_claimed", /đang được dùng/],
    ["approval_already_refused", /đã bị từ chối/],
    ["approval_already_in_doubt", /chưa rõ kết quả/],
    ["approval_already_reconcile_failed", /đọc lại thấy khác/],
    ["no_right_on_Quantity9", /không có quyền sửa cột Quantity9$/],
    ["gateway_422", /không đúng dạng/],
    ["pending: not traced", /chưa ghi được loại thay đổi này/],
    ["layout_could_not_be_read: SO_X", /Chưa đọc được màn hình SO/],
    ["rules_could_not_decide: boom", /không quyết được/],
    ["blocked: SO_B1, SO_B2", /chặn thay đổi này: SO_B1, SO_B2$/],
    ["undecided: SO_B3", /Chưa kiểm được quy tắc .*: SO_B3$/],
    ["provisional: template x is not in hand", /chưa có đủ mẫu/],
    ["unmeasured: the columns a new line of B30 holds", /chưa đo được/],
  ])("%s", (reason, words) => {
    expect(bravoWriteReason(reason)).toMatch(words);
  });

  it("says a refusal after a lost answer may have been written", () => {
    expect(bravoWriteReason("expired after a lost answer")).toBe(
      "Phiếu duyệt đã hết hạn trước khi ghi: đề xuất lại (sau một lần gửi mất câu trả lời: có thể Bravo đã ghi, kiểm tra trong Bravo)",
    );
  });

  it("shows a reason it has no words for as a sentence for IT, with the code", () => {
    expect(bravoWriteReason("something_new")).toBe(
      "Lý do chưa có lời giải thích, báo IT kèm mã: something_new",
    );
  });
});

describe("a Bravo write's warnings in words (DW1 review, ui)", () => {
  it.each([
    // `pipeline._reconcile`'s differences.
    [
      "Detail#0.Quantity9",
      "Detail#0, cột Quantity9: Bravo lưu khác giá trị đã ghi",
    ],
    ["Detail#1.RowId: not filled", "Detail#1, cột RowId: Bravo chưa điền"],
    ["Detail#2: row gone", "Detail#2: dòng không còn trong Bravo"],
    ["a line not planned: Id 77", "Bravo có thêm dòng DW1 không ghi (Id 77)"],
    ["read_back_failed", "Không đọc lại được SO sau khi ghi để so"],
    // A screen rule's warning keeps the rule's own name.
    ["SO_W12 (could not check)", "SO_W12 (chưa kiểm được)"],
    ["SO_W12", "SO_W12"],
  ])("%s", (warning, words) => {
    expect(bravoWriteWarning(warning)).toBe(words);
  });
});

describe("Sales words a person reads carry no internal English (DW1 review, ui)", () => {
  // "workspace" is "không gian làm việc" in Sales; the gateway is DW's own
  // part, which a Sales head reading a refusal does not know by that name.
  it.each([
    ["SALES_REFUSALS", SALES_REFUSALS],
    ["BRAVO_WRITE_CHECK", BRAVO_WRITE_CHECK],
    ["BRAVO_WRITE_REASON", BRAVO_WRITE_REASON],
    ["BRAVO_WRITE_UNMEASURED", BRAVO_WRITE_UNMEASURED],
  ] as const)("%s", (_, table) => {
    for (const words of Object.values(table))
      expect(words).not.toMatch(/\b(workspace|gateway)\b/i);
  });
});
