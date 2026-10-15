import { z } from "zod";

/** `support` is the support team acting under a customer's grant (ADR 0024). */
export const auditActorKindSchema = z.enum(["user", "support"]);
export type AuditActorKind = z.infer<typeof auditActorKindSchema>;

export const auditEventSchema = z.object({
  actor_id: z.string(),
  /** The actor's name today; null for an actor that is no user (a lane). */
  actor_display_name: z.string().nullable(),
  actor_kind: auditActorKindSchema,
  action: z.string(),
  resource_type: z.string(),
  resource_id: z.string(),
  policy_decision: z.string().nullable(),
  trace_id: z.string().nullable(),
  occurred_at: z.string(),
  details: z.record(z.string(), z.unknown()),
});
export type AuditEvent = z.infer<typeof auditEventSchema>;
