// @vitest-environment node
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  ACTIVITY_PARAMS,
  knownReason,
  MODEL_STEP_IDS,
  modelStepLabel,
  reasonLabel,
} from "../activity";
import { LIST_NAME, TAB_OF } from "../catalog";
import { ACTIVITY_KIND, EDGE_ACTION, EDGE_GUARD, MOVE_ACTOR } from "../labels";
import { knownFieldWords } from "../rule-labels";

/**
 * Every code the process page and the activity screens receive has words.
 * The closed sets are read from the OpenAPI snapshot the client is generated
 * from, so a code the server adds turns this red, not a screen that shows a
 * raw code. Reason codes are not an enum in the API (a row holds any code of
 * its shape), so they are read from where the server makes them: the
 * literals and enums in `dw_sales`, by the patterns below, each of which must
 * still find something (a moved source fails here, not silently).
 */

const ROOT = resolve(__dirname, "../../../../../..");
const SPEC = JSON.parse(
  readFileSync(resolve(ROOT, "contracts/openapi/openapi.json"), "utf8"),
) as {
  components: {
    schemas: Record<
      string,
      {
        enum?: string[];
        properties?: Record<string, { enum?: string[] }>;
      }
    >;
  };
  paths: Record<string, { get: { parameters: { name: string }[] } }>;
};
const schema = (name: string) => SPEC.components.schemas[name]!;
const sorted = (values: Iterable<string>) => [...values].sort();

describe("the process page's words cover what the API sends", () => {
  it.each([
    ["EdgeAction", EDGE_ACTION, schema("EdgeAction").enum],
    ["EdgeGuard", EDGE_GUARD, schema("EdgeGuard").enum],
    [
      "ProcessEdgeView.actor",
      MOVE_ACTOR,
      schema("ProcessEdgeView").properties!.actor!.enum,
    ],
    [
      "ActivityEntry.kind",
      ACTIVITY_KIND,
      schema("ActivityEntry").properties!.kind!.enum,
    ],
    ["CatalogList", LIST_NAME, schema("CatalogList").enum],
    ["CatalogList (tabs)", TAB_OF, schema("CatalogList").enum],
  ])("names every %s, and no other", (_, words, codes) => {
    expect(codes!.length).toBeGreaterThan(0);
    expect(sorted(Object.keys(words))).toEqual(sorted(codes!));
    for (const text of Object.values(words)) expect(text).toBeTruthy();
  });

  it("names every model step by its switch in the order rules", () => {
    expect(sorted(MODEL_STEP_IDS)).toEqual(sorted(schema("ModelStep").enum!));
    for (const step of MODEL_STEP_IDS) {
      const words = knownFieldWords(
        "sales_order_rules",
        `model_assist.${step}`,
      );
      expect(words?.label, step).toBeTruthy();
      expect(modelStepLabel(step)).toBe(words!.label);
    }
  });

  it("reads the case list filter by the names the API serves it with", () => {
    expect(sorted(ACTIVITY_PARAMS)).toEqual(
      sorted(Object.keys(schema("ActivityFilter").properties!)),
    );
    for (const list of ["/api/v1/sales/orders", "/api/v1/sales/quotes"])
      expect(sorted(ACTIVITY_PARAMS)).toEqual(
        sorted(SPEC.paths[list]!.get.parameters.map((p) => p.name)),
      );
  });
});

const SALES = resolve(ROOT, "packages/python/dw_sales/src/dw_sales");
const source = (path: string) => readFileSync(resolve(SALES, path), "utf8");

/** Every capture of `pattern` in `text`; the pattern must find one. */
function captures(text: string, pattern: RegExp, what: string): string[] {
  const found = [...text.matchAll(pattern)].map((m) => m[1]!);
  expect(found.length, `${what} still finds codes`).toBeGreaterThan(0);
  return found;
}

/** The literals inside `Name = Literal[ … ]`. */
function literal(text: string, name: string): string[] {
  const block = new RegExp(`${name} = Literal\\[([\\s\\S]*?)\\]`).exec(text);
  expect(block, `${name} = Literal[…]`).not.toBeNull();
  return captures(block![1]!, /"([a-z_]+)"/g, name);
}

/** The values of `class Name(StrEnum):`. */
function strEnum(text: string, name: string): string[] {
  const block = new RegExp(
    `class ${name}\\(StrEnum\\):([\\s\\S]*?)\\n\\n\\n`,
  ).exec(text);
  expect(block, `class ${name}(StrEnum)`).not.toBeNull();
  return captures(block![1]!, /= "([a-z_]+)"/g, name);
}

/** The server's reason codes, as far as its sources name them. */
function serverReasonCodes(): string[] {
  const activity = source("domain/activity.py");
  const rfq = source("domain/rfq_reading.py");
  const handoffs = source("application/handoffs.py");
  // A request reader's refusal per field: `<field>_<what went wrong>`.
  const rfqFields = [
    ...captures(rfq, /within\([^,()]+,\s*"([a-z_]+)"\)/g, "rfq item fields"),
    ...captures(rfq, /verdict\.refused,\s*"([a-z_]+)"/g, "rfq header fields"),
    "line",
  ];
  return [
    ...literal(source("domain/description_reading.py"), "NotUnderstood"),
    ...strEnum(source("domain/dispositions.py"), "RoutingReason"),
    ...literal(source("domain/layouts.py"), "LayoutProblem"),
    ...captures(
      source("application/layouts.py"),
      /"problems": \("([a-z_]+)",\)/g,
      "a layout proposal's own problem",
    ),
    ...captures(activity, /^[A-Z_]+: Final = "([a-z_]+)"$/gm, "row codes"),
    ...captures(activity, /reason_code="([a-z_]+)"/g, "hand-off reason"),
    ...captures(activity, /_code\([^)]*"([a-z_]+)"\)/g, "layout fallback"),
    ...captures(rfq, /refused\["([a-z_]+)"\]/g, "rfq refusals"),
    ...rfqFields.flatMap((f) =>
      ["not_found", "repeated", "unparsed"].map((what) => `${f}_${what}`),
    ),
    ...captures(handoffs, /refused\["([a-z_]+)"\]/g, "hand-off refusals"),
    ...captures(handoffs, /refused,\s*"([a-z_]+)"\)/g, "hand-off quotes"),
  ];
}

describe("the activity's reasons, in words", () => {
  it("names every reason code the server makes", () => {
    const codes = [...new Set(serverReasonCodes())];
    expect(codes).toEqual(
      expect.arrayContaining([
        "no_item_fits",
        "nothing_located",
        "not_used",
        "other",
        "refused",
        "span_not_found",
        "customer_unknown",
        "description_not_found",
        "quote_due_unparsed",
        "po_no",
      ]),
    );
    const unnamed = codes.filter((code) => knownReason(code) === null);
    expect(unnamed).toEqual([]);
  });

  it("says a code it does not know as one, never as a blank", () => {
    expect(reasonLabel("brand_new_check")).toBe(
      "Lý do khác (mã brand_new_check)",
    );
    expect(reasonLabel("description_not_found")).toBe(
      "Mô tả: không tìm thấy trong thư chữ mô hình chỉ ra",
    );
    expect(reasonLabel("lot")).toBe("Số lô: DW1 không giữ giá trị mô hình đọc");
    expect(reasonLabel("span_repeated")).toBe(
      "Chữ mô hình chỉ ra xuất hiện hơn một lần",
    );
  });
});
