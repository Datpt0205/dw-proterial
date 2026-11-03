// @vitest-environment node
import { describe, expect, it } from "vitest";
import type { PurchasingMasterImport } from "@dw/api-client";
import { changeWords, submitBlocked, toBase64 } from "../master-data";

function item(over: Partial<PurchasingMasterImport>): PurchasingMasterImport {
  return {
    import_id: "i",
    file_name: "a.xlsx",
    status: "parsed",
    uploaded_by: "u",
    uploaded_at: "2026-11-02T00:00:00Z",
    read_at: null,
    rejected: [],
    rejected_total: 0,
    failure: null,
    version_ref: null,
    changes: [],
    dropped: {},
    blocked: null,
    ...over,
  };
}

describe("master data page words", () => {
  it("says a list left out of the file stays as it is", () => {
    const base = {
      list: "budgets" as const,
      sheet: "Ngân sách",
      rows: 4,
      in_force: 4,
    };
    expect(
      changeWords({
        ...base,
        in_file: false,
        added: 0,
        removed: 0,
        changed: 0,
      }),
    ).toBe("Giữ nguyên 4 dòng (không có trong tệp)");
    expect(
      changeWords({ ...base, in_file: true, added: 1, removed: 2, changed: 3 }),
    ).toBe("4 dòng · Mới 1 · Bỏ 2 · Đổi 3");
  });

  it("gives the reason Gửi duyệt is disabled, and none when it is not", () => {
    expect(submitBlocked(item({}), true)).toBeNull();
    expect(submitBlocked(item({}), false)).toMatch(/người cấu hình DW2/);
    expect(submitBlocked(item({ blocked: "đang chờ duyệt" }), true)).toBe(
      "đang chờ duyệt",
    );
  });

  it("encodes a file larger than one call can spread", () => {
    const bytes = new Uint8Array(0x8000 * 2 + 3).map((_, i) => i % 251);
    expect(
      Buffer.from(toBase64(bytes), "base64").equals(Buffer.from(bytes)),
    ).toBe(true);
  });
});
