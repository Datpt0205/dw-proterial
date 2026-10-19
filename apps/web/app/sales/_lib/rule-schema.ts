/**
 * A rule key's JSON Schema (`GET /sales/rules/{key}/schema`, ticket 40), read
 * once into the few shapes the editor draws. The schema is the key's own
 * Pydantic model's, so this file decides how a shape is drawn, never what a
 * document may hold: the server validates every proposal again.
 *
 * The shapes Pydantic emits for these models, and what each becomes:
 *
 * - `properties` → an object, drawn as a section of fields;
 * - `additionalProperties` (+ `propertyNames` enum) or one `patternProperties`
 *   → a map, drawn as a key/value list;
 * - `items` → a list, drawn with add, remove and reorder;
 * - `anyOf: [number, decimal string]` → a number kept as text, exactly;
 * - `anyOf: [X, null]` → X that may be left out (null);
 * - `enum` → a choice; `const` → a fixed value shown, never edited;
 * - `type: string|integer|number|boolean` → text, number, switch.
 */

export interface JsonSchema {
  $ref?: string;
  $defs?: Record<string, JsonSchema>;
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  additionalProperties?: JsonSchema | boolean;
  patternProperties?: Record<string, JsonSchema>;
  propertyNames?: JsonSchema;
  items?: JsonSchema;
  anyOf?: JsonSchema[];
  enum?: unknown[];
  const?: unknown;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  minItems?: number;
  maxItems?: number;
  /** The placeholders a template field may name (`handoffs.py`, `_named`). */
  "x-placeholders"?: string[];
}

interface Base {
  /** May be null: the field is turned off rather than filled. */
  nullable: boolean;
}

export interface RuleField {
  name: string;
  required: boolean;
  node: RuleNode;
  default?: unknown;
}

export type RuleNode = Base &
  (
    | { kind: "object"; fields: RuleField[] }
    | {
        kind: "map";
        /** A closed key set (a finding code, a language), else free keys. */
        keyEnum?: string[];
        keyPattern?: string;
        value: RuleNode;
      }
    | { kind: "list"; item: RuleNode; minItems?: number; maxItems?: number }
    | {
        kind: "text";
        minLength?: number;
        maxLength?: number;
        pattern?: string;
        multiline: boolean;
        placeholders?: string[];
      }
    | {
        kind: "number";
        integer: boolean;
        /** Sent as text (`"0.18"`), so the number is read exactly. */
        decimal: boolean;
        min?: number;
        max?: number;
        exclusiveMin?: number;
        exclusiveMax?: number;
      }
    | { kind: "switch" }
    | { kind: "choice"; values: string[] }
    | { kind: "fixed"; value: unknown }
  );

/** One step into a document: a field or map key, or a list position. */
export type DocPath = (string | number)[];

function resolve(root: JsonSchema, schema: JsonSchema): JsonSchema {
  let current = schema;
  for (let guard = 0; current.$ref && guard < 32; guard++) {
    const name = current.$ref.replace(/^#\/\$defs\//, "");
    const target = root.$defs?.[name];
    if (!target) throw new Error(`unresolved $ref ${current.$ref}`);
    current = { ...target, ...withoutRef(current) };
  }
  return current;
}

function withoutRef(schema: JsonSchema): JsonSchema {
  const { $ref: _ref, ...rest } = schema;
  return rest;
}

/** Text that may hold a line break: long and with no pattern forbidding one. */
function multiline(schema: JsonSchema): boolean {
  return (schema.maxLength ?? 0) > 300 && !schema.pattern;
}

/** The schema of one key, as the shapes the editor draws. */
export function readSchema(root: JsonSchema): RuleNode {
  return node(root, root, false);
}

function node(root: JsonSchema, raw: JsonSchema, nullable: boolean): RuleNode {
  const schema = resolve(root, raw);
  if (schema.anyOf) {
    const branches = schema.anyOf.map((b) => resolve(root, b));
    const nonNull = branches.filter((b) => b.type !== "null");
    const isNullable = nonNull.length < branches.length;
    const numeric = nonNull.find(
      (b) => b.type === "number" || b.type === "integer",
    );
    if (
      numeric &&
      nonNull.length === 2 &&
      nonNull.some((b) => b.type === "string")
    )
      return {
        ...numberNode(numeric, true),
        nullable: nullable || isNullable,
      };
    if (nonNull.length === 1)
      return node(
        root,
        { ...nonNull[0]!, default: schema.default },
        nullable || isNullable,
      );
    throw new Error(`unsupported anyOf in ${schema.title ?? "schema"}`);
  }
  if ("const" in schema) return { kind: "fixed", value: schema.const, nullable };
  if (schema.enum)
    return { kind: "choice", values: schema.enum.map(String), nullable };
  switch (schema.type) {
    case "object":
      return objectNode(root, schema, nullable);
    case "array":
      return {
        kind: "list",
        item: node(root, schema.items ?? {}, false),
        minItems: schema.minItems,
        maxItems: schema.maxItems,
        nullable,
      };
    case "boolean":
      return { kind: "switch", nullable };
    case "integer":
    case "number":
      return { ...numberNode(schema, false), nullable };
    case "string":
      return {
        kind: "text",
        minLength: schema.minLength,
        maxLength: schema.maxLength,
        pattern: schema.pattern,
        multiline: multiline(schema),
        placeholders: schema["x-placeholders"],
        nullable,
      };
    default:
      throw new Error(`unsupported schema type ${String(schema.type)}`);
  }
}

function numberNode(
  schema: JsonSchema,
  decimal: boolean,
): Omit<Extract<RuleNode, { kind: "number" }>, "nullable"> {
  return {
    kind: "number",
    integer: schema.type === "integer",
    decimal,
    min: schema.minimum,
    max: schema.maximum,
    exclusiveMin: schema.exclusiveMinimum,
    exclusiveMax: schema.exclusiveMaximum,
  };
}

function objectNode(
  root: JsonSchema,
  schema: JsonSchema,
  nullable: boolean,
): RuleNode {
  if (schema.properties) {
    const required = new Set(schema.required ?? []);
    return {
      kind: "object",
      fields: Object.entries(schema.properties).map(([name, field]) => ({
        name,
        required: required.has(name),
        node: node(root, field, false),
        default: field.default,
      })),
      nullable,
    };
  }
  const patterns = Object.entries(schema.patternProperties ?? {});
  if (patterns.length === 1) {
    const [pattern, value] = patterns[0]!;
    return {
      kind: "map",
      keyPattern: pattern,
      value: node(root, value, false),
      nullable,
    };
  }
  if (typeof schema.additionalProperties === "object") {
    const names = schema.propertyNames
      ? resolve(root, schema.propertyNames)
      : undefined;
    return {
      kind: "map",
      keyEnum: names?.enum?.map(String),
      keyPattern: names?.pattern,
      value: node(root, schema.additionalProperties, false),
      nullable,
    };
  }
  throw new Error(`unsupported object in ${schema.title ?? "schema"}`);
}

// ------------------------------------------------------------ label paths --

/**
 * Where a label is looked up: the document path with each map key as `*` and
 * each list position as `[]`, so one label covers every entry
 * (`emails.*.*.subject`, `copper_adders[].band.low_usd_per_tonne`).
 */
export function labelPath(root: RuleNode, path: DocPath): string {
  let current: RuleNode | undefined = root;
  let out = "";
  for (const step of path) {
    if (!current) break;
    if (current.kind === "object") {
      const field: RuleField | undefined = current.fields.find(
        (f) => f.name === step,
      );
      out = out ? `${out}.${String(step)}` : String(step);
      current = field?.node;
    } else if (current.kind === "map") {
      out = `${out}.*`;
      current = current.value;
    } else if (current.kind === "list") {
      out = `${out}[]`;
      current = current.item;
    } else break;
  }
  return out;
}

/** Every field's label path in a key's schema: what the label table must cover. */
export function fieldPaths(root: RuleNode): string[] {
  const out: string[] = [];
  const walk = (n: RuleNode, prefix: string) => {
    if (n.kind === "object")
      for (const f of n.fields) {
        const path = prefix ? `${prefix}.${f.name}` : f.name;
        out.push(path);
        walk(f.node, path);
      }
    else if (n.kind === "map") {
      // A map of maps draws a heading for each inner map.
      if (n.value.kind === "map") out.push(`${prefix}.*`);
      walk(n.value, `${prefix}.*`);
    }
    else if (n.kind === "list") walk(n.item, `${prefix}[]`);
  };
  walk(root, "");
  return out;
}

/** Every value a choice or a closed map key may take, in a key's schema. */
export function enumValues(root: RuleNode): string[] {
  const out = new Set<string>();
  const walk = (n: RuleNode) => {
    if (n.kind === "choice") n.values.forEach((v) => out.add(v));
    if (n.kind === "object") n.fields.forEach((f) => walk(f.node));
    if (n.kind === "map") {
      n.keyEnum?.forEach((v) => out.add(v));
      walk(n.value);
    }
    if (n.kind === "list") walk(n.item);
  };
  walk(root);
  return [...out];
}

/** The node at a document path, if the schema has one there. */
export function nodeAt(root: RuleNode, path: DocPath): RuleNode | undefined {
  let current: RuleNode | undefined = root;
  for (const step of path) {
    if (!current) return undefined;
    if (current.kind === "object")
      current = current.fields.find((f) => f.name === step)?.node;
    else if (current.kind === "map") current = current.value;
    else if (current.kind === "list") current = current.item;
    else return undefined;
  }
  return current;
}

// ------------------------------------------------- document <-> form values --

/** A map entry as the form holds it: a key/value list keeps order and edits keys. */
export interface MapEntry {
  key: string;
  value: unknown;
}

/** A nullable section as the form holds it: on, and what it holds when on. */
export interface Toggled {
  on: boolean;
  value: unknown;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** What a field starts as when the document has nothing for it. */
function empty(n: RuleNode): unknown {
  switch (n.kind) {
    case "object":
      return Object.fromEntries(
        n.fields.map((f) => [f.name, f.default ?? empty(f.node)]),
      );
    case "map":
    case "list":
      return n.kind === "map" ? {} : [];
    case "text":
      return n.nullable ? null : "";
    case "switch":
      return false;
    case "fixed":
      return n.value;
    default:
      return null;
  }
}

/** A document value as the form holds it. */
export function toForm(n: RuleNode, value: unknown): unknown {
  if (n.nullable && n.kind !== "text") {
    const on = value !== null && value !== undefined;
    return {
      on,
      value: toForm({ ...n, nullable: false }, on ? value : empty(n)),
    } satisfies Toggled;
  }
  switch (n.kind) {
    case "object": {
      const record = isRecord(value) ? value : {};
      return Object.fromEntries(
        n.fields.map((f) => [
          f.name,
          toForm(f.node, f.name in record ? record[f.name] : (f.default ?? empty(f.node))),
        ]),
      );
    }
    case "map":
      return Object.entries(isRecord(value) ? value : {}).map(
        ([key, v]): MapEntry => ({ key, value: toForm(n.value, v) }),
      );
    case "list":
      return (Array.isArray(value) ? value : []).map((v) => toForm(n.item, v));
    case "number":
      if (value === null || value === undefined || value === "") return null;
      return n.decimal ? String(value) : Number(value);
    case "text":
      return value ?? "";
    default:
      return value;
  }
}

/** The form's values as the document a proposal sends. */
export function fromForm(n: RuleNode, value: unknown): unknown {
  if (n.nullable && n.kind !== "text") {
    const toggled = (value ?? { on: false }) as Toggled;
    return toggled.on ? fromForm({ ...n, nullable: false }, toggled.value) : null;
  }
  switch (n.kind) {
    case "object": {
      const record = isRecord(value) ? value : {};
      return Object.fromEntries(
        n.fields.map((f) => [f.name, fromForm(f.node, record[f.name])]),
      );
    }
    case "map":
      return Object.fromEntries(
        ((value as MapEntry[] | undefined) ?? [])
          .filter((e) => e && e.key !== undefined)
          .map((e) => [e.key, fromForm(n.value, e.value)]),
      );
    case "list":
      return ((value as unknown[] | undefined) ?? []).map((v) =>
        fromForm(n.item, v),
      );
    case "number":
      if (value === null || value === undefined || value === "") return null;
      return n.decimal ? String(value) : Number(value);
    case "text":
      return n.nullable && (value === "" || value == null) ? null : (value ?? "");
    case "switch":
      return Boolean(value);
    default:
      return value;
  }
}

/**
 * The form field a document path names: maps become key/value lists and a
 * nullable section holds its value under `value`, so a server refusal at
 * `findings.price_mismatch` lands on the right row. `null` where the form has
 * no such field (a refusal of the whole document, or of a key it lacks).
 */
export function formName(
  root: RuleNode,
  formValues: unknown,
  path: DocPath,
): (string | number)[] | null {
  const name: (string | number)[] = [];
  let n: RuleNode | undefined = root;
  let value: unknown = formValues;
  for (const step of path) {
    if (!n) return null;
    if (n.nullable && n.kind !== "text") {
      name.push("value");
      value = (value as Toggled | undefined)?.value;
    }
    if (n.kind === "object") {
      const field: RuleField | undefined = n.fields.find((f) => f.name === step);
      if (!field) return null;
      name.push(step);
      value = isRecord(value) ? value[String(step)] : undefined;
      n = field.node;
    } else if (n.kind === "map") {
      const entries = (value as MapEntry[] | undefined) ?? [];
      const index = entries.findIndex((e) => e?.key === String(step));
      if (index < 0) return null;
      name.push(index, "value");
      value = entries[index]?.value;
      n = n.value;
    } else if (n.kind === "list") {
      const index = Number(step);
      if (!Number.isInteger(index)) return null;
      name.push(index);
      value = (value as unknown[] | undefined)?.[index];
      n = n.item;
    } else return name.length ? name : null;
  }
  return name;
}

/** "price.relative_tolerance", "copper_adders.0.band" as a document path. */
export function parseLoc(loc: string): DocPath {
  if (!loc) return [];
  return loc
    .split(".")
    .filter((part) => part !== "" && !part.startsWith("["))
    .map((part) => (/^\d+$/.test(part) ? Number(part) : part));
}

// ------------------------------------------------------------ validation --

/** Python's regular expressions in these schemas, as JavaScript reads them. */
export function patternOf(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern);
  } catch {
    return null;
  }
}

/**
 * What is wrong with one value under its node, in words; null when nothing
 * is. Required-ness is the form's (it is asked on submit only, ui-quality
 * §9); this checks what was typed.
 */
export function problem(n: RuleNode, value: unknown): string | null {
  if (value === null || value === undefined || value === "") return null;
  if (n.kind === "number") {
    const number = Number(value);
    if (!Number.isFinite(number)) return "Phải là một số.";
    if (n.integer && !Number.isInteger(number)) return "Phải là số nguyên.";
    if (n.min !== undefined && number < n.min)
      return `Không được nhỏ hơn ${formatNumber(n.min)}.`;
    if (n.max !== undefined && number > n.max)
      return `Không được lớn hơn ${formatNumber(n.max)}.`;
    if (n.exclusiveMin !== undefined && number <= n.exclusiveMin)
      return `Phải lớn hơn ${formatNumber(n.exclusiveMin)}.`;
    if (n.exclusiveMax !== undefined && number >= n.exclusiveMax)
      return `Phải nhỏ hơn ${formatNumber(n.exclusiveMax)}.`;
  }
  if (n.kind === "text" && typeof value === "string") {
    if (n.minLength !== undefined && value.length < n.minLength)
      return `Cần ít nhất ${n.minLength} ký tự.`;
    if (n.maxLength !== undefined && value.length > n.maxLength)
      return `Tối đa ${n.maxLength} ký tự.`;
    const regex = n.pattern ? patternOf(n.pattern) : null;
    if (regex && !regex.test(value)) return patternProblem(n.pattern!);
  }
  if (n.kind === "list" && Array.isArray(value)) {
    if (n.minItems !== undefined && value.length < n.minItems)
      return `Cần ít nhất ${n.minItems} mục.`;
    if (n.maxItems !== undefined && value.length > n.maxItems)
      return `Tối đa ${n.maxItems} mục.`;
  }
  return null;
}

/** The patterns these schemas use, said in words; any other in general terms. */
function patternProblem(pattern: string): string {
  if (pattern === "^\\d+\\.\\d+\\.\\d+$")
    return "Số phiên bản gồm ba số cách nhau bằng dấu chấm, ví dụ 1.2.0.";
  if (pattern.startsWith("^[^\\x00-\\x1f"))
    return "Chỉ một dòng: không xuống dòng.";
  if (pattern.startsWith("^[a-z]"))
    return "Chỉ chữ thường không dấu, số và dấu gạch dưới, bắt đầu bằng một chữ.";
  if (pattern.startsWith("^[^\\[\\]"))
    return "Không dùng các ký tự [ ] : * ? / \\ '.";
  return "Giá trị chưa đúng định dạng.";
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 6 }).format(
    value,
  );
}

/** The field a document's version number is in: `policy_version`, else `version`. */
export function versionField(root: RuleNode): string | null {
  if (root.kind !== "object") return null;
  const names = root.fields.map((f) => f.name);
  return names.includes("policy_version")
    ? "policy_version"
    : names.includes("version")
      ? "version"
      : null;
}
