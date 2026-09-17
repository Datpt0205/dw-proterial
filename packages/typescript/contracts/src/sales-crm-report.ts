import { z } from "zod";

/**
 * Tab Report (spec 013). Its own file rather than more lines in
 * `sales-crm.ts`, which is already 1800 lines: reports are one screen group
 * with one vocabulary, and nothing else in the CRM refers to them.
 *
 * Everything the server sends is already formatted — a money cell arrives as
 * `$1,234.56`, a date as the column's own format — so the CSV, the PDF and the
 * screen can never disagree about what a cell says.
 */

/** The four modules a report can be built on. */
export const reportRootModuleSchema = z.enum([
  "accounts",
  "opportunities",
  "tasks",
  "leads",
]);
export type ReportRootModule = z.infer<typeof reportRootModuleSchema>;

/** The five columns the report list can be ordered by. */
export const reportListSortSchema = z.enum([
  "name",
  "root_module",
  "assigned_to",
  "created_at",
  "updated_at",
]);
export type ReportListSort = z.infer<typeof reportListSortSchema>;

export const reportFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  display: z.boolean(),
  link: z.boolean(),
  function: z.enum(["count", "min", "max", "sum", "avg"]).nullish(),
  sort: z.enum(["asc", "desc"]).nullish(),
  format: z.string().nullish(),
  total: z.enum(["count", "sum", "avg"]).nullish(),
  /** The catalog no longer has this field: the column shows, the cells are
   *  blank, and saving refuses until the row is removed. Always sent — a
   *  default here would split the schema's input and output types. */
  missing: z.boolean(),
});
export type ReportField = z.infer<typeof reportFieldSchema>;

/** The nine operators, in the order the dropdown lists them. */
export const reportOperatorSchema = z.enum([
  "eq",
  "ne",
  "gt",
  "lt",
  "gte",
  "lte",
  "contains",
  "starts_with",
  "ends_with",
]);
export type ReportOperator = z.infer<typeof reportOperatorSchema>;

/** The six value types, in the order the Type dropdown lists them. */
export const reportValueTypeSchema = z.enum([
  "value",
  "field",
  "date",
  "period",
  "multi",
  "current_user",
]);
export type ReportValueType = z.infer<typeof reportValueTypeSchema>;

/** How a row joins what stands before it. Absent on the first row of a level. */
export const reportLogicOpSchema = z.enum(["and", "or"]);
export type ReportLogicOp = z.infer<typeof reportLogicOpSchema>;

export const OPERATOR_LABELS: Record<ReportOperator, string> = {
  eq: "Equal To",
  ne: "Not Equal To",
  gt: "Greater Than",
  lt: "Less Than",
  gte: "Greater Than or Equal To",
  lte: "Less Than or Equal To",
  contains: "Contains",
  starts_with: "Starts With",
  ends_with: "Ends With",
};

export const VALUE_TYPE_LABELS: Record<ReportValueType, string> = {
  value: "Value",
  field: "Field",
  date: "Date",
  period: "Period",
  multi: "Multi",
  current_user: "Current User",
};

export const reportConditionSchema = z.object({
  /** The server fills this in on the way out, even for a definition saved
   *  before conditions could be grouped — so it is always here. A default
   *  would split the schema's input and output types. */
  kind: z.literal("condition"),
  key: z.string(),
  operator: reportOperatorSchema,
  value_type: reportValueTypeSchema,
  /** A `multi` condition keeps its ticked codes here as a JSON array. */
  value: z.string().nullish(),
  /** Editable in the Parameters panel; anything else is fixed by the
   *  definition. */
  is_parameter: z.boolean(),
  logic_op: reportLogicOpSchema,
  /** The catalog no longer knows this field or code: the row shows in red and
   *  running the report leaves it out. */
  missing: z.boolean(),
});
export type ReportCondition = z.infer<typeof reportConditionSchema>;

/**
 * Half of a bracket pair, standing as its own row.
 *
 * The table is a flat list, the way SuiteCRM stores it, so dragging a row is
 * moving one item — no tree to rebuild on every gesture.
 */
export const reportParenthesisSchema = z.object({
  kind: z.literal("paren"),
  side: z.enum(["open", "close"]),
  /** Both halves of one pair carry the same number. */
  pair: z.number().int().positive(),
  logic_op: reportLogicOpSchema,
});
export type ReportParenthesis = z.infer<typeof reportParenthesisSchema>;

export const reportConditionRowSchema = z.discriminatedUnion("kind", [
  reportConditionSchema,
  reportParenthesisSchema,
]);
export type ReportConditionRow = z.infer<typeof reportConditionRowSchema>;

/** A row that carries a condition, as opposed to half a bracket pair. */
export function isConditionRow(
  row: ReportConditionRow,
): row is ReportCondition {
  return row.kind === "condition";
}

/**
 * Just the conditions, in order — what the Parameters panel numbers and what a
 * run override's `index` counts. Bracket rows are structure, not content.
 */
export function conditionsOf(rows: ReportConditionRow[]): ReportCondition[] {
  return rows.filter(isConditionRow);
}

export const reportDefinitionSchema = z.object({
  fields: z.array(reportFieldSchema),
  conditions: z.array(reportConditionRowSchema),
  main_group: z.string().nullish(),
});
export type ReportDefinition = z.infer<typeof reportDefinitionSchema>;

export const reportSummarySchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  root_module: reportRootModuleSchema,
  assigned_to_user_id: z.string().uuid().nullish(),
  assigned_to_name: z.string().nullish(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type ReportSummary = z.infer<typeof reportSummarySchema>;

export const reportPageSchema = z.object({
  items: z.array(reportSummarySchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type ReportPage = z.infer<typeof reportPageSchema>;

export const reportViewSchema = reportSummarySchema.extend({
  description: z.string().nullish(),
  definition: reportDefinitionSchema,
  version: z.number().int(),
  created_by_name: z.string().nullish(),
  updated_by_name: z.string().nullish(),
  /** "(n of N)" on the button row — null when the report was opened by URL
   *  rather than from a list, because then there is no list to stand in. */
  position: z.number().int().nullish(),
  count: z.number().int().nullish(),
  /** Whether this viewer may edit the definition. Greying the pencil is
   *  navigation; the server still refuses a PUT without the scope. */
  can_edit: z.boolean(),
  /** Worth saying after a save, not worth refusing it — "over_30_conditions"
   *  means the report will be slow. Empty on the read path. */
  warnings: z.array(z.string()),
});
export type ReportView = z.infer<typeof reportViewSchema>;

export const reportNeighboursSchema = z.object({
  previous_id: z.string().uuid().nullish(),
  next_id: z.string().uuid().nullish(),
  position: z.number().int().nullish(),
  count: z.number().int(),
});
export type ReportNeighbours = z.infer<typeof reportNeighboursSchema>;

/** Column filters on the report list and inside a result block. The shape
 *  mirrors the lead list's, because it is the same toolbar. */
export type ReportColumnFilter =
  | {
      kind: "text";
      key: string;
      op: "is" | "isnt" | "contain" | "not_contain";
      value: string;
    }
  | { kind: "values"; key: string; values: string[] }
  | {
      kind: "date";
      key: string;
      date_from?: string | null;
      date_to?: string | null;
    }
  | {
      kind: "number";
      key: string;
      minimum?: number | null;
      maximum?: number | null;
    };

// ---- running a report -----------------------------------------------------

/**
 * One row of the Parameters panel, as the reader left it.
 *
 * `index` counts conditions and ignores bracket rows: it is the position the
 * panel numbers from one, so a bracket dropped in between never shifts which
 * condition a saved link changes.
 */
export interface ReportParamOverride {
  index: number;
  operator?: ReportOperator | null;
  value_type?: ReportValueType | null;
  value?: string | null;
  /** The ticked codes of a `multi` row. Ignored for every other type. */
  values?: string[] | null;
}

export interface ReportRunRequest {
  params?: ReportParamOverride[];
  /** Which block; null is a report with no Main Group, or the "nobody" block. */
  group?: string | null;
  limit?: number;
  offset?: number;
  sort?: { key: string; descending: boolean } | null;
  search?: string | null;
  filters?: ReportColumnFilter[];
}

export const runGroupSchema = z.object({
  value: z.string().nullish(),
  label: z.string(),
  total: z.number().int(),
});
export type RunGroup = z.infer<typeof runGroupSchema>;

export const runColumnSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.string(),
  link: z.boolean(),
  format: z.string().nullish(),
  /** The catalog no longer has this field: the header carries a warning and
   *  every cell below it is blank. */
  missing: z.boolean(),
  /** The field exists, but this system has not imported a single value for it
   *  yet: the header says so, and the blanks below are expected, not a bug. */
  no_data: z.boolean(),
  total: z.string().nullish(),
});
export type RunColumn = z.infer<typeof runColumnSchema>;

export const runCellSchema = z.object({
  /** Already formatted by the server, so the screen, the CSV and the PDF
   *  cannot disagree about what a number says. */
  text: z.string(),
  href: z.string().nullish(),
  raw: z.string().nullish(),
});
export type RunCell = z.infer<typeof runCellSchema>;

export const reportRunPageSchema = z.object({
  /** Always at least one: no Main Group means one block called REPORT. */
  groups: z.array(runGroupSchema),
  group: z.string().nullish(),
  columns: z.array(runColumnSchema),
  rows: z.array(z.object({ cells: z.record(z.string(), runCellSchema) })),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
  totals: z.record(z.string(), z.string()),
});
export type ReportRunPage = z.infer<typeof reportRunPageSchema>;

// ---- editing a definition -------------------------------------------------

export interface SaveReportCommand {
  name: string;
  description?: string | null;
  assigned_to_user_id?: string | null;
  root_module: ReportRootModule;
  definition: {
    fields: Omit<ReportField, "missing">[];
    conditions: ReportConditionRow[];
    main_group?: string | null;
  };
  /** Optimistic lock: a stale number is a 409 naming who edited it. */
  expected_version: number;
}

export const reportChangeSchema = z.object({
  field_name: z.string(),
  old_value: z.string().nullish(),
  new_value: z.string().nullish(),
  changed_at: z.string(),
  /** Blank when the row came from the import gate, which does not know who. */
  changed_by_name: z.string().nullish(),
  source: z.string(),
});
export type ReportChange = z.infer<typeof reportChangeSchema>;

export const catalogFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  type: z.string(),
  linkable: z.boolean(),
  formats: z.array(z.string()),
  functions: z.array(z.string()),
  totals: z.array(z.string()),
  operators: z.array(reportOperatorSchema),
  value_types: z.array(reportValueTypeSchema),
  /** (code, label) of a picklist field, for the Value box and the tick list. */
  enum_values: z.array(z.tuple([z.string(), z.string()])),
  /** False means this system has no value for the field yet: the column runs
   *  blank and a condition on it matches nothing. Still pickable — the mark
   *  goes away by itself once the import gate brings values in. */
  has_data: z.boolean(),
  /** A field of this system that SugarCRM does not have. */
  local_only: z.boolean(),
});
export type CatalogField = z.infer<typeof catalogFieldSchema>;

export const reportCatalogSchema = z.object({
  root_module: reportRootModuleSchema,
  modules: z.array(
    z.object({
      path: z.string(),
      label: z.string(),
      fields: z.array(catalogFieldSchema),
    }),
  ),
});
export type ReportCatalog = z.infer<typeof reportCatalogSchema>;
export type CatalogModule = ReportCatalog["modules"][number];
