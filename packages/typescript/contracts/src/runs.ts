import { z } from "zod";

/** Mirrors dw_platform approval + dw_agent_runtime run/timeline views. */

export const approvalSchema = z.object({
  id: z.string().uuid(),
  approval_type: z.string(),
  reason: z.string(),
  status: z.enum(["pending", "approved", "rejected", "cancelled"]),
  run_id: z.string().uuid().nullable(),
  payload: z.record(z.string(), z.unknown()),
  created_at: z.string().nullable(),
  decided_at: z.string().nullable(),
  /** The server refuses a blank comment for these; the form must require one. */
  requires_comment: z.boolean(),
});
export type Approval = z.infer<typeof approvalSchema>;

export const runSchema = z.object({
  id: z.string().uuid(),
  status: z.enum([
    "pending",
    "running",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
  ]),
  worker_id: z.string(),
  worker_version: z.string(),
  graph_version: z.string(),
  result: z.record(z.string(), z.unknown()).nullable(),
  error: z.record(z.string(), z.unknown()).nullable(),
  approval_request_id: z.string().uuid().nullable(),
  release_manifest_ref: z.string().nullable(),
});
export type Run = z.infer<typeof runSchema>;

export const timelineEventSchema = z.object({
  action: z.string(),
  resource_type: z.string(),
  resource_id: z.string(),
  policy_decision: z.string().nullable(),
  occurred_at: z.string(),
  details: z.record(z.string(), z.unknown()),
});
export type TimelineEvent = z.infer<typeof timelineEventSchema>;
