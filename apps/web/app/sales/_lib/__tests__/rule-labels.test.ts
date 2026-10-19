import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { RULE_KEY, type RuleKey } from "../rules";
import {
  fieldWords,
  humanise,
  knownFieldWords,
  knownValueLabel,
  pathLabel,
  valueLabel,
} from "../rule-labels";
import {
  enumValues,
  fieldPaths,
  readSchema,
  type JsonSchema,
} from "../rule-schema";

/**
 * Every field of every key's schema has Vietnamese words (ticket 40). The
 * schemas are `contracts/jsonschema/sales_rules.json`, which
 * `scripts/generate_contracts.py` writes from the Pydantic models and CI
 * checks is current: a field added to a model fails here until labelled.
 */
const SCHEMAS = JSON.parse(
  readFileSync(
    resolve(
      __dirname,
      "../../../../../../contracts/jsonschema/sales_rules.json",
    ),
    "utf-8",
  ),
) as Record<RuleKey, JsonSchema>;

describe("the rules editor's words (ticket 40)", () => {
  it("has a schema for exactly the keys the API names", () => {
    expect(Object.keys(SCHEMAS).sort()).toEqual(Object.keys(RULE_KEY).sort());
  });

  it("labels every field path of every key's schema", () => {
    const missing: string[] = [];
    for (const [key, schema] of Object.entries(SCHEMAS) as [
      RuleKey,
      JsonSchema,
    ][])
      for (const path of fieldPaths(readSchema(schema)))
        if (!knownFieldWords(key, path)) missing.push(`${key}: ${path}`);
    expect(missing).toEqual([]);
  });

  it("walks deep enough to see the nested fields (the check can fail)", () => {
    const paths = fieldPaths(readSchema(SCHEMAS.sales_pricing));
    expect(paths).toContain("copper_adders[].band.low_usd_per_tonne");
    expect(fieldPaths(readSchema(SCHEMAS.sales_emails))).toContain(
      "emails.*.*.subject",
    );
    expect(
      fieldPaths(readSchema(SCHEMAS.sales_order_rules)).length,
    ).toBeGreaterThan(30);
  });

  it("names every value a choice or a closed map key may take", () => {
    const missing: string[] = [];
    for (const schema of Object.values(SCHEMAS))
      for (const value of enumValues(readSchema(schema)))
        if (!knownValueLabel(value)) missing.push(value);
    expect(missing).toEqual([]);
    expect(valueLabel("error")).toBe("Chặn");
    expect(valueLabel("O3")).toBe("Đơn hàng, bước 3 (O3)");
  });

  it("falls back to the humanised field name for a field not labelled yet", () => {
    expect(knownFieldWords("sales_kpi", "a_new_target_hours")).toBeNull();
    expect(fieldWords("sales_kpi", "a_new_target_hours").label).toBe(
      "A new target hours",
    );
    expect(fieldWords("sales_pricing", "freight[].a_new_field").label).toBe(
      "A new field",
    );
    expect(humanise("max_cells")).toBe("Max cells");
    expect(valueLabel("not_a_code")).toBe("not_a_code");
  });

  it("reads a document path in words, map keys and list positions included", () => {
    const pricing = readSchema(SCHEMAS.sales_pricing);
    expect(
      pathLabel("sales_pricing", pricing, [
        "copper_adders",
        1,
        "band",
        "low_usd_per_tonne",
      ]),
    ).toBe("Phụ phí đồng theo mức LME › Mức LME 2 › Khoảng giá LME › Từ (gồm)");
    const orders = readSchema(SCHEMAS.sales_order_rules);
    expect(
      pathLabel("sales_order_rules", orders, ["findings", "price_mismatch"]),
    ).toBe("Mức độ của từng cờ › Đơn giá lệch báo giá");
    const emails = readSchema(SCHEMAS.sales_emails);
    expect(
      pathLabel("sales_emails", emails, [
        "emails",
        "confirmation_draft",
        "vi",
        "subject",
      ]),
    ).toBe("Mẫu thư › Thư xác nhận PO (nháp) › tiếng Việt › Tiêu đề");
  });
});
