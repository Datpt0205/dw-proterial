import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { RuleKey } from "../rules";
import { diffDocuments } from "../rule-diff";
import {
  formName,
  fromForm,
  nodeAt,
  parseLoc,
  problem,
  readSchema,
  toForm,
  versionField,
  type JsonSchema,
  type RuleNode,
} from "../rule-schema";
import { placeholdersIn, unknownPlaceholders } from "../rule-templates";

const SCHEMAS = JSON.parse(
  readFileSync(
    resolve(__dirname, "../../../../../../contracts/jsonschema/sales_rules.json"),
    "utf-8",
  ),
) as Record<RuleKey, JsonSchema>;

const node = (key: RuleKey) => readSchema(SCHEMAS[key]);

const PRICING = {
  schema_version: "1.0",
  policy_id: "sales_pricing",
  policy_version: "1.0.0",
  copper_adders: [
    {
      band: { kind: "lme_band", low_usd_per_tonne: "9000", high_usd_per_tonne: "9500" },
      adder_usd_per_tonne: "310",
    },
    {
      band: { kind: "lme_band", low_usd_per_tonne: "9500", high_usd_per_tonne: "10000" },
      adder_usd_per_tonne: "335",
    },
  ],
  floor_margin: "0.18",
  freight: [{ incoterm: "EXW", destination: "factory", usd_per_km: "0" }],
};

const QUOTE = {
  schema_version: "1.0",
  policy_id: "sales_quote_rules",
  policy_version: "1.1.0",
  reference_price: { band_below_percent: "3", band_above_percent: "10" },
  copper_basis: "lme_band",
  validity_days: 90,
  design_mailboxes: ["design@seller.example"],
};

const HANDOFFS = {
  schema_version: "1.0",
  copy_id: "sales_handoffs",
  version: "1.0.0",
  unknown: "(chưa rõ)",
  line: "- Dòng {line_no}",
  quote: "«{text}»",
  templates: {
    complaint: { to: "qa", subject: "Khách {customer}", body: "PO {po}" },
  },
};

describe("a key's schema, read into what the editor draws (ticket 40)", () => {
  it("reads each shape Pydantic emits", () => {
    const pricing = node("sales_pricing");
    expect(nodeAt(pricing, ["floor_margin"])).toMatchObject({
      kind: "number",
      decimal: true,
      min: 0,
      exclusiveMax: 1,
    });
    expect(nodeAt(pricing, ["copper_adders"])).toMatchObject({ kind: "list", minItems: 1 });
    expect(nodeAt(pricing, ["copper_adders", 0, "band", "kind"])).toMatchObject({
      kind: "fixed",
      value: "lme_band",
    });
    const orders = node("sales_order_rules");
    expect(nodeAt(orders, ["cross_check_required"])).toMatchObject({ kind: "switch" });
    expect(nodeAt(orders, ["export_control_mode"])).toMatchObject({
      kind: "choice",
      values: ["warn", "block_confirmation"],
    });
    const findings = nodeAt(orders, ["findings"]) as Extract<RuleNode, { kind: "map" }>;
    expect(findings.kind).toBe("map");
    expect(findings.keyEnum).toContain("price_mismatch");
    expect(findings.value).toMatchObject({ kind: "choice", values: ["error", "warning"] });
    expect(nodeAt(orders, ["fiscal_year_start_month"])).toMatchObject({
      kind: "number",
      integer: true,
      min: 1,
      max: 12,
    });
    expect(nodeAt(node("sales_quote_rules"), ["reference_price"])).toMatchObject({
      kind: "object",
      nullable: true,
    });
    const emails = node("sales_emails");
    expect(nodeAt(emails, ["emails"])).toMatchObject({ kind: "map", keyPattern: "^[a-z][a-z0-9_]{2,47}$" });
    expect(nodeAt(emails, ["emails", "x", "vi", "body"])).toMatchObject({ kind: "text", multiline: true });
    expect(nodeAt(emails, ["emails", "x", "vi", "subject"])).toMatchObject({ kind: "text", multiline: false });
    expect(nodeAt(emails, ["emails", "x", "vi", "line"])).toMatchObject({ kind: "text", nullable: true });
    expect(nodeAt(node("sales_handoffs"), ["templates", "complaint", "body"])).toMatchObject({
      placeholders: expect.arrayContaining(["{customer}", "{po}"]),
    });
    expect(versionField(pricing)).toBe("policy_version");
    expect(versionField(emails)).toBe("version");
  });

  it("turns a document into form values and back unchanged", () => {
    for (const [key, document] of [
      ["sales_pricing", PRICING],
      ["sales_quote_rules", QUOTE],
      ["sales_handoffs", HANDOFFS],
    ] as const) {
      const root = node(key);
      expect(fromForm(root, toForm(root, document)), key).toEqual(document);
    }
    // A section turned off is null, as the schema allows.
    const root = node("sales_quote_rules");
    const values = toForm(root, QUOTE) as Record<string, unknown>;
    values.reference_price = { on: false, value: values.reference_price };
    expect((fromForm(root, values) as Record<string, unknown>).reference_price).toBeNull();
    expect(toForm(root, { ...QUOTE, reference_price: null })).toMatchObject({
      reference_price: { on: false },
    });
  });

  it("checks what was typed against the schema, in words", () => {
    const orders = node("sales_order_rules");
    const month = nodeAt(orders, ["fiscal_year_start_month"])!;
    expect(problem(month, 13)).toBe("Không được lớn hơn 12.");
    expect(problem(month, 0)).toBe("Không được nhỏ hơn 1.");
    expect(problem(month, 4.5)).toBe("Phải là số nguyên.");
    expect(problem(month, 4)).toBeNull();
    const margin = nodeAt(node("sales_pricing"), ["floor_margin"])!;
    expect(problem(margin, "1")).toBe("Phải nhỏ hơn 1.");
    const version = nodeAt(orders, ["policy_version"])!;
    expect(problem(version, "1.2")).toMatch(/ba số/);
    const subject = nodeAt(node("sales_emails"), ["emails", "k", "vi", "subject"])!;
    expect(problem(subject, "a\nb")).toBe("Chỉ một dòng: không xuống dòng.");
    const adders = nodeAt(node("sales_pricing"), ["copper_adders"])!;
    expect(problem(adders, [])).toBe("Cần ít nhất 1 mục.");
    // Empty is the required rule's to say, on submit.
    expect(problem(month, null)).toBeNull();
  });

  it("finds the form field a server refusal names, maps and lists included", () => {
    const orders = node("sales_order_rules");
    const values = toForm(orders, {
      price: { relative_tolerance: "0" },
      findings: { code_unmapped: "error", price_mismatch: "error" },
    });
    expect(formName(orders, values, parseLoc("findings.price_mismatch"))).toEqual([
      "findings",
      1,
      "value",
    ]);
    expect(formName(orders, values, parseLoc("price.relative_tolerance"))).toEqual([
      "price",
      "relative_tolerance",
    ]);
    expect(formName(orders, values, parseLoc("findings.nothing"))).toBeNull();
    const pricing = node("sales_pricing");
    expect(
      formName(pricing, toForm(pricing, PRICING), parseLoc("copper_adders.1.band.low_usd_per_tonne")),
    ).toEqual(["copper_adders", 1, "band", "low_usd_per_tonne"]);
    const quote = node("sales_quote_rules");
    expect(
      formName(quote, toForm(quote, QUOTE), parseLoc("reference_price.band_below_percent")),
    ).toEqual(["reference_price", "value", "band_below_percent"]);
    expect(parseLoc("findings.price_mismatch.[key]")).toEqual(["findings", "price_mismatch"]);
    expect(parseLoc("")).toEqual([]);
  });
});

describe("what a version changes (ticket 40)", () => {
  it("names each changed field, and nothing else", () => {
    const next = structuredClone(PRICING);
    next.floor_margin = "0.2";
    next.policy_version = "1.0.1";
    expect(diffDocuments(PRICING, next)).toEqual([
      { kind: "changed", path: ["policy_version"], before: "1.0.0", after: "1.0.1" },
      { kind: "changed", path: ["floor_margin"], before: "0.18", after: "0.2" },
    ]);
    // A decimal written another way is the same number.
    expect(diffDocuments({ a: "0.10" }, { a: 0.1 })).toEqual([]);
  });

  it("reads an inserted list item as one added item, not every later one changed", () => {
    const next = structuredClone(PRICING);
    const middle = {
      band: { kind: "lme_band", low_usd_per_tonne: "9200", high_usd_per_tonne: "9300" },
      adder_usd_per_tonne: "320",
    };
    next.copper_adders.splice(1, 0, middle);
    expect(diffDocuments(PRICING, next)).toEqual([
      { kind: "added", path: ["copper_adders", 1], after: middle },
    ]);
    const fewer = structuredClone(PRICING);
    fewer.copper_adders.splice(0, 1);
    expect(diffDocuments(PRICING, fewer)).toEqual([
      { kind: "removed", path: ["copper_adders", 0], before: PRICING.copper_adders[0] },
    ]);
  });

  it("compares an edited list item field by field, and map keys added and removed", () => {
    const next = structuredClone(PRICING);
    next.copper_adders[1]!.adder_usd_per_tonne = "340";
    expect(diffDocuments(PRICING, next)).toEqual([
      {
        kind: "changed",
        path: ["copper_adders", 1, "adder_usd_per_tonne"],
        before: "335",
        after: "340",
      },
    ]);
    expect(
      diffDocuments({ m: { a: 1, b: 2 } }, { m: { b: 2, c: 3 } }),
    ).toEqual([
      { kind: "removed", path: ["m", "a"], before: 1 },
      { kind: "added", path: ["m", "c"], after: 3 },
    ]);
    expect(diffDocuments({ xs: ["a", "b"] }, { xs: ["a", "c"] })).toEqual([
      { kind: "changed", path: ["xs", 1], before: "b", after: "c" },
    ]);
  });
});

describe("a template's placeholders (ticket 40)", () => {
  it("lists the ${…} a text uses, and flags names outside a set", () => {
    expect(placeholdersIn("PO ${po_no} lần ${revision}, ${po_no}")).toEqual([
      "${po_no}",
      "${revision}",
    ]);
    expect(unknownPlaceholders("Khách {customer} {customer:>9} {x}", ["{customer}"], "braces")).toEqual([
      "{customer:>9}",
      "{x}",
    ]);
    expect(unknownPlaceholders("{{literal}} {po}", ["{po}"], "braces")).toEqual([]);
    expect(unknownPlaceholders("${po_no} ${nope}", ["${po_no}"], "dollar")).toEqual(["${nope}"]);
  });
});
