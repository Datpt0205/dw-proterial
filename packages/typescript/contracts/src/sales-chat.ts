import { z } from "zod";
import { leadStatusSchema, opportunityStageSchema } from "./sales-crm";

export const conversationScopeSchema = z.enum([
  "workspace",
  "lead",
  "account",
  "opportunity",
]);
export type ConversationScope = z.infer<typeof conversationScopeSchema>;

export const conversationSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  channel: z.string(),
  status: z.string(),
  scope_type: conversationScopeSchema,
  scope_ref: z.string().uuid().nullish(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const chatMessageSchema = z.object({
  id: z.string().uuid(),
  seq: z.number().int(),
  role: z.enum(["user", "assistant", "tool"]),
  content: z.string(),
  tool_name: z.string().nullable(),
  citations: z.array(z.record(z.unknown())),
  created_at: z.string(),
});

export const transcriptSchema = z.object({
  conversation: conversationSchema,
  messages: z.array(chatMessageSchema),
  /**
   * The approval this thread is parked on, when it is parked on one.
   *
   * Part of where the conversation currently is, not of the turn that paused
   * it: until it is decided the thread refuses every message, so a client that
   * did not stream that turn - a reload, a second tab, a colleague - still has
   * to be able to find the card.
   */
  waiting_approval_id: z.string().uuid().nullish(),
});

/**
 * What the user is looking at when they send a turn.
 *
 * Enums and UUIDs only: this reaches the assistant's system prompt, so a free
 * string here would be a way to write instructions the model trusts. The
 * backend validates the same shape again and re-reads every id under the
 * caller's own access context before naming anything.
 */
export const viewRouteSchema = z.enum([
  "leads_list",
  "lead_detail",
  "accounts_list",
  "account_detail",
  "pipeline_board",
  "opportunity_detail",
  "contacts_list",
  "tasks_list",
  "dashboard",
  "team",
  "inbox",
  "other",
]);

export const viewRecordRefSchema = z.object({
  record_type: z.enum(["lead", "account", "contact", "opportunity", "task"]),
  record_id: z.string().uuid(),
});

export const viewFiltersSchema = z.object({
  lead_status: leadStatusSchema.optional(),
  stage: opportunityStageSchema.optional(),
  // Mirrors the CRM's three statuses since spec 006 (migration 0114).
  task_status: z.enum(["not_started", "in_progress", "completed"]).optional(),
  owner: z.enum(["me", "anyone"]).optional(),
  open_only: z.boolean().optional(),
});

export const viewContextSchema = z.object({
  route: viewRouteSchema,
  record: viewRecordRefSchema.optional(),
  filters: viewFiltersSchema.optional(),
  selection: z.array(viewRecordRefSchema).max(5).optional(),
});

export type ViewRoute = z.infer<typeof viewRouteSchema>;
export type ViewRecordRef = z.infer<typeof viewRecordRefSchema>;
export type ViewFilters = z.infer<typeof viewFiltersSchema>;
export type ViewContext = z.infer<typeof viewContextSchema>;

/**
 * What a turn emits while it runs. `approval_required` means the turn paused
 * and a human has to decide before it can continue.
 */
export const chatEventSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("token"), data: z.object({ text: z.string() }) }),
  // The model's summary of thinking it already did and was already billed for.
  // Display-only: it is never stored, because it is model output derived from
  // CRM notes and pasted text, which the prompt classifies as untrusted.
  z.object({
    type: z.literal("reasoning"),
    data: z.object({ text: z.string() }),
  }),
  // A step the turn just finished. Name only - the arguments and the result
  // arrive with the transcript. It exists so a turn that spends thirty seconds
  // reading records shows that it is doing so.
  z.object({ type: z.literal("tool"), data: z.object({ name: z.string() }) }),
  // A step inside another worker's graph, while it runs. `intel.ask` sends the
  // research worker away for minutes, and one "tool started" line followed by
  // silence is indistinguishable from a hang. Display-only: the transcript
  // keeps the answer, not the searches that led to it.
  z.object({
    type: z.literal("progress"),
    data: z.object({
      step: z.string(),
      query: z.string(),
      sources: z.array(z.object({ title: z.string(), url: z.string() })),
    }),
  }),
  // Up to three things the user could usefully say next, proposed by a model
  // once the turn is over. Display-only, like `reasoning` and `progress`: they
  // describe the turn that just ended, so a thread reloaded later comes back
  // without them rather than offering next steps for an older answer.
  z.object({
    type: z.literal("suggestions"),
    data: z.object({ suggestions: z.array(z.string()) }),
  }),
  // A produced output the panel renders as an editable card. The body is not
  // here on purpose: it lives in the artifact row, so the panel fetches it
  // rather than the stream carrying a copy that can go stale.
  z.object({
    type: z.literal("artifact"),
    // Two kinds of produced output share this event, told apart by `kind`
    // rather than by which keys are present: a card picked by key-sniffing
    // renders the wrong thing the first time a third kind arrives.
    data: z.discriminatedUnion("kind", [
      z.object({
        kind: z.literal("email_draft"),
        artifact_id: z.string(),
        version: z.number(),
        subject: z.string(),
        preview: z.string(),
        recipient_name: z.string(),
      }),
      z.object({
        kind: z.literal("meeting_minutes"),
        artifact_id: z.string(),
        version: z.number(),
        title: z.string(),
        preview: z.string(),
        source_filename: z.string(),
        // The file was longer than one read returns, so these are minutes of
        // its first part. The card says so; silence here would hand over
        // minutes of half a meeting as minutes of the meeting.
        source_truncated: z.boolean(),
      }),
      z.object({
        kind: z.literal("meeting_brief"),
        artifact_id: z.string(),
        version: z.number(),
        title: z.string(),
        preview: z.string(),
      }),
      // A real file rather than an editable body: the card offers opening and
      // downloading, not inline editing. `template_tier` and `template_name`
      // are on the card because whoever sends this document onward has to be
      // able to see whose identity it carries.
      z.object({
        kind: z.literal("document"),
        artifact_id: z.string(),
        version: z.number(),
        title: z.string(),
        filename: z.string(),
        size_bytes: z.number(),
        template_tier: z.enum(["account", "workspace", "built_in"]),
        template_name: z.string(),
        // Figures the document states that nothing in the conversation
        // supplied. On the card because the person reading it is the one who
        // can tell whether a number is a mistake or something they said aloud.
        unsupported_numbers: z.array(z.string()).default([]),
      }),
    ]),
  }),
  z.object({
    type: z.literal("approval_required"),
    data: z.object({
      approval_type: z.string().optional(),
      reason: z.string().optional(),
      tool: z.string().optional(),
    }),
  }),
  z.object({
    type: z.literal("done"),
    data: z.object({ run_id: z.string() }),
  }),
  // The turn failed. `error` is a sentence for the person reading it, not an
  // exception class: "APIStatusError" told a user to do nothing in particular,
  // and the dropped connection behind it told them to blame their network.
  z.object({
    type: z.literal("error"),
    data: z.object({ error: z.string() }),
  }),
]);

export type Conversation = z.infer<typeof conversationSchema>;
export type ChatMessage = z.infer<typeof chatMessageSchema>;
export type Transcript = z.infer<typeof transcriptSchema>;
export type ChatEvent = z.infer<typeof chatEventSchema>;

/**
 * One uploaded Word template.
 *
 * `checksum` is what a generated document records, so "which template produced
 * this file" survives a rename. Archived rows stay in the listing: a document
 * generated last quarter names one of them, and hiding it makes that document
 * unexplainable.
 */
export const documentTemplateSchema = z.object({
  id: z.string(),
  scope_type: z.enum(["workspace", "account"]),
  scope_id: z.string().nullable(),
  name: z.string(),
  filename: z.string(),
  checksum: z.string(),
  is_default: z.boolean(),
  archived: z.boolean(),
  created_at: z.string(),
});
export type DocumentTemplate = z.infer<typeof documentTemplateSchema>;

/**
 * The line an empty thread opens with, written server-side for whoever asked.
 *
 * One field rather than a route-keyed map: the greeting is about the person's
 * own book - what they carry, what is overdue, what closes soon - and none of
 * that changes when they open a different record.
 */
export const chatGreetingSchema = z.object({
  greeting: z.string(),
});
export type ChatGreeting = z.infer<typeof chatGreetingSchema>;
