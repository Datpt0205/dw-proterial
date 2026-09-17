import { z } from "zod";

/**
 * The Trợ lý tab: a thread, its messages, and the events one turn streams.
 *
 * A separate file from `sales-intel` because it is a separate surface added on
 * top of one that is running. Nothing here changes the shape of a tender, a
 * scan or an analytics response.
 */

/**
 * The two filter chips above the transcript.
 *
 * Sent with a question and returned with every stored message. An answer's
 * numbers only mean something beside the set they were computed over, and a
 * person scrolling back next week cannot reconstruct which chips were pressed.
 */
export const screenFilterSchema = z.object({
  year: z.number().int().nullish(),
  scope: z.enum(["all", "cntt", "pref"]),
});

/**
 * Every colour a figure may name. Tokens, not colours: the browser maps these to
 * CSS variables, so light mode, dark mode and the colourblind-safe slot ordering
 * are decided here and never by the model.
 */
export const figureColorSchema = z.enum([
  "series1",
  "series2",
  "series3",
  "series4",
  "series5",
  "series6",
  "series7",
  "series8",
  "ink",
  "muted",
  "grid",
  "surface",
  "positive",
  "negative",
  "highlight",
]);

export const figureTextSizeSchema = z.enum(["xs", "sm", "md", "lg"]);

const coordinate = z.number().finite();

/**
 * The six marks a figure is built from.
 *
 * A discriminated union rather than one permissive object, and every field a
 * number or a token - there is no field here for markup, script or a colour.
 * That is the point: the agent composes the picture, and the renderer maps each
 * `type` through a closed switch to an element it wrote itself. A model that
 * could emit markup a browser then executed would have found the one place it
 * goes unnoticed, because a chart is meant to look like something rather than
 * read like something.
 *
 * The server validates all of it - bounds, counts, wedge angles, at least one
 * text mark - so the client renders rather than re-checks. These schemas exist
 * to keep the payload honest at the boundary, not to repeat the rules.
 *
 * `tip` is the one field that is not geometry: the sentence a reader gets when
 * they point at the mark. It is how the tooltip a chart library used to provide
 * comes back without the model writing any code for it - the model says what the
 * mark means, and this file's renderer decides when and how that appears.
 */
export const figureMarkSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("rect"),
    tip: z.string().nullish(),
    x: coordinate,
    y: coordinate,
    width: z.number().finite().nonnegative(),
    height: z.number().finite().nonnegative(),
    color: figureColorSchema,
    opacity: z.number().finite().optional(),
    radius: z.number().finite().optional(),
  }),
  z.object({
    type: z.literal("line"),
    tip: z.string().nullish(),
    x1: coordinate,
    y1: coordinate,
    x2: coordinate,
    y2: coordinate,
    color: figureColorSchema.optional(),
    width: z.number().finite().optional(),
    dashed: z.boolean().optional(),
  }),
  z.object({
    type: z.literal("polyline"),
    tip: z.string().nullish(),
    points: z.array(z.tuple([coordinate, coordinate])).min(2),
    color: figureColorSchema,
    width: z.number().finite().optional(),
    dashed: z.boolean().optional(),
    fill: z.boolean().optional(),
    baseline: coordinate.nullish(),
    opacity: z.number().finite().optional(),
  }),
  z.object({
    type: z.literal("circle"),
    tip: z.string().nullish(),
    cx: coordinate,
    cy: coordinate,
    radius: z.number().finite().positive(),
    color: figureColorSchema,
    opacity: z.number().finite().optional(),
  }),
  z.object({
    type: z.literal("slice"),
    tip: z.string().nullish(),
    cx: coordinate,
    cy: coordinate,
    radius: z.number().finite().positive(),
    inner_radius: z.number().finite().nonnegative().optional(),
    start_deg: z.number().finite(),
    end_deg: z.number().finite(),
    color: figureColorSchema,
    opacity: z.number().finite().optional(),
  }),
  z.object({
    type: z.literal("text"),
    tip: z.string().nullish(),
    x: coordinate,
    y: coordinate,
    text: z.string(),
    color: figureColorSchema.optional(),
    size: figureTextSizeSchema.optional(),
    anchor: z.enum(["start", "middle", "end"]).optional(),
    weight: z.enum(["normal", "medium", "bold"]).optional(),
    rotate: z.number().finite().optional(),
  }),
]);

/**
 * A whole drawing.
 *
 * `summary` is not decoration: it is what a screen reader is given and what is
 * shown if the marks cannot be drawn, so it states the finding rather than
 * describing the picture. `footnote` carries the data's scope, because a figure
 * gets screenshotted away from the paragraph that said which set it covered.
 */
export const figureSpecSchema = z.object({
  title: z.string(),
  summary: z.string(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  marks: z.array(figureMarkSchema),
  footnote: z.string().nullish(),
});

/**
 * One thing the answer was computed from: a query, or a read of the Analysis
 * panel.
 *
 * Kept beside the answer so a reader can check it rather than believe it.
 * `status` is three-valued for the reason the whole backend is: `empty` means
 * the query ran and the data is genuinely absent, `error` means the SQL was
 * wrong, and showing them the same way would let a typo read as a fact.
 *
 * A panel read has no `sql` - it runs a computation rather than a statement -
 * and arrives in this same shape on purpose, so the chip stays one component
 * instead of two that drift.
 */
export const analystToolCallSchema = z.object({
  tool: z.string(),
  sql: z.string(),
  purpose: z.string(),
  status: z.string(),
  row_count: z.number(),
  truncated: z.boolean(),
  error: z.string().nullish(),
  columns: z.array(z.string()),
  /** A sample for the chip, never the whole result set. */
  rows: z.array(z.array(z.unknown())),
});

export const analystThreadSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  created_at: z.string().nullish(),
  updated_at: z.string().nullish(),
});

export const analystMessageSchema = z.object({
  id: z.string().uuid(),
  role: z.enum(["user", "assistant"]),
  content: z.string(),
  tool_calls: z.array(analystToolCallSchema),
  /** Stored on the message that drew it, so a reload redraws rather than re-runs. */
  figure: figureSpecSchema.nullish(),
  /** What the chips were set to for this turn. Absent on turns from before they were carried. */
  screen_filter: screenFilterSchema.nullish(),
  created_at: z.string(),
});

export const analystEventSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("token"), data: z.object({ text: z.string() }) }),
  z.object({ type: z.literal("tool_call"), data: analystToolCallSchema }),
  z.object({ type: z.literal("figure"), data: figureSpecSchema }),
  z.object({
    type: z.literal("done"),
    data: z.object({ run_id: z.string() }),
  }),
  z.object({
    type: z.literal("error"),
    data: z.object({ error: z.string() }),
  }),
]);

export type ScreenFilter = z.infer<typeof screenFilterSchema>;
export type FigureColor = z.infer<typeof figureColorSchema>;
export type FigureTextSize = z.infer<typeof figureTextSizeSchema>;
export type FigureMark = z.infer<typeof figureMarkSchema>;
export type FigureSpec = z.infer<typeof figureSpecSchema>;
export type AnalystToolCall = z.infer<typeof analystToolCallSchema>;
export type AnalystThread = z.infer<typeof analystThreadSchema>;
export type AnalystMessage = z.infer<typeof analystMessageSchema>;
export type AnalystEvent = z.infer<typeof analystEventSchema>;
