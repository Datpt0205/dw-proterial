import { z } from "zod";

/**
 * Sales CRM read models, mirrored from the Pydantic views in
 * dw_sales_crm/application (the OpenAPI snapshot is the source of truth;
 * these zod schemas are the runtime half of that contract).
 */

// ---- leads ---------------------------------------------------------------

// The BD's canonical lead statuses (NC-1, BA confirm 2026-08-21) — a
// vocabulary of the Lead only, distinct from Opportunity stages.
export const leadStatusSchema = z.enum([
  "new",
  "working_contacted",
  "unqualified_closed",
  "qualified_converted",
]);
export type LeadStatus = z.infer<typeof leadStatusSchema>;

// How the contact person is addressed (AC-LEADCREATE-002).
export const salutationSchema = z.enum(["mr", "ms", "mrs"]);
export type Salutation = z.infer<typeof salutationSchema>;

export const leadSchema = z.object({
  id: z.string().uuid(),
  // Composed from the three parts below whenever they are present; leads
  // created before the split form carry only this.
  contact_name: z.string(),
  company_name: z.string(),
  salutation: salutationSchema.nullish(),
  first_name: z.string().nullish(),
  last_name: z.string().nullish(),
  status: leadStatusSchema,
  version: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
  status_reason: z.string().nullish(),
  contact_role: z.string().nullish(),
  contact_email: z.string().nullish(),
  contact_phone: z.string().nullish(),
  industry: z.string().nullish(),
  website: z.string().nullish(),
  region: z.string().nullish(),
  size_estimate: z.string().nullish(),
  annual_revenue: z.number().nullish(),
  // Company facts that convert maps onto the Account. `region` is the sales
  // territory; `address` is the postal address.
  tax_code: z.string().nullish(),
  legal_name: z.string().nullish(),
  phone_office: z.string().nullish(),
  // The company's own inbox, not the contact person's.
  company_email: z.string().nullish(),
  address: z.string().nullish(),
  source: z.string().nullish(),
  description: z.string().nullish(),
  // Qualification facts the scoring rubric reads — free text stating the fact
  // ("board approved 8B on 05 Aug"), never a rubric level. Entered inline on
  // the lead page or written by the scoring agent quoting a document.
  it_spend: z.string().nullish(),
  financial_health: z.string().nullish(),
  consulting_experience: z.string().nullish(),
  budget: z.string().nullish(),
  timeline: z.string().nullish(),
  painpoint: z.string().nullish(),
  trigger_event: z.string().nullish(),
  owner_user_id: z.string().uuid().nullish(),
  account_id: z.string().uuid().nullish(),
  contact_id: z.string().uuid().nullish(),
  opportunity_id: z.string().uuid().nullish(),
  // Background AI enrichment (spec 002): absent on leads that never asked for
  // it. Drives only the spinner on the detail page — never a label.
  enrichment: z
    .object({
      status: z.enum(["pending", "done", "failed"]),
      requested_at: z.string().nullish(),
      finished_at: z.string().nullish(),
    })
    .nullish(),
  // Which fields AI filled and from where. Log-trail only, never rendered.
  ai_filled: z.record(z.string()).nullish(),
});
export type Lead = z.infer<typeof leadSchema>;

// ---- accounts ------------------------------------------------------------

export const accountSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  country: z.string(),
  version: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
  legal_name: z.string().nullish(),
  tax_code: z.string().nullish(),
  industry: z.string().nullish(),
  founded_year: z.number().nullish(),
  size: z.string().nullish(),
  website: z.string().nullish(),
  hq_address: z.string().nullish(),
  /** The administrative unit the list screen shows and filters by (spec 011).
   * Blank on every account until the create form or the detail screen learns
   * to write it - both are out of that spec's scope. */
  district: z.string().nullish(),
  owner_user_id: z.string().uuid().nullish(),
  parent_account_id: z.string().uuid().nullish(),
  source: z.string().nullish(),
  qualified: z.boolean(),
  qualified_at: z.string().nullish(),
  /** Sales-set "key account" flag; synced from Sugar, editable on the account. */
  key_account: z.boolean(),
  /** Set by convert; drives the "from Lead" link on the account hero. */
  converted_from_lead_id: z.string().uuid().nullish(),
  summary: z.string().nullish(),
  summary_updated_at: z.string().nullish(),
  open_opportunities: z.number().int().nullish(),
  won_opportunities: z.number().int().nullish(),
  // Background AI enrichment, same contract as the lead's: absent on accounts
  // that never asked for it. Drives only spinners — never a label.
  enrichment: z
    .object({
      status: z.enum(["pending", "done", "failed"]),
      requested_at: z.string().nullish(),
      finished_at: z.string().nullish(),
    })
    .nullish(),
});
export type Account = z.infer<typeof accountSchema>;

/** The Account Intelligence strip, read in one call rather than six. */
export const accountStatsSchema = z.object({
  account_id: z.string().uuid(),
  open_opportunities: z.number().int(),
  pipeline_amount: z.number(),
  won_opportunities: z.number().int(),
  won_amount: z.number(),
  contacts: z.number().int(),
  documents: z.number().int(),
  open_tasks: z.number().int(),
  last_activity_at: z.string().nullish(),
});
export type AccountStats = z.infer<typeof accountStatsSchema>;

// ---- contacts ------------------------------------------------------------

export const buyingRoleSchema = z.enum([
  "decision_maker",
  "influencer",
  "user",
  "gatekeeper",
]);
export type BuyingRole = z.infer<typeof buyingRoleSchema>;

// Three points since 0093 — "champion" is a buying role, not an attitude.
export const attitudeSchema = z.enum(["supporter", "neutral", "blocker"]);
export type Attitude = z.infer<typeof attitudeSchema>;

export const influenceSchema = z.enum(["high", "medium", "low"]);
export type Influence = z.infer<typeof influenceSchema>;

// One seat taken (0090): what and when — year only, the day is rarely printed.
// The source rides on the entry so the panel can show it at the end of the
// line it belongs to.
export const appointmentEntrySchema = z.object({
  title: z.string(),
  year: z.number().int().nullish(),
  source_url: z.string().nullish(),
});
export type AppointmentEntry = z.infer<typeof appointmentEntrySchema>;

// One "Thông tin khác" bullet (0090). `origin` says who wrote it — a person
// (manual) or the AI (person_research / ai_approved) — and the screen styles
// the bullet by it.
export const otherFactSchema = z.object({
  text: z.string(),
  source_url: z.string().nullish(),
  origin: z.string(),
});
export type OtherFact = z.infer<typeof otherFactSchema>;

export const crmContactSchema = z.object({
  account_name: z.string().nullish(),
  buying_role: buyingRoleSchema.nullish(),
  attitude: attitudeSchema.nullish(),
  influence: influenceSchema.nullish(),
  has_veto: z.boolean(),
  position_note: z.string().nullish(),
  id: z.string().uuid(),
  // Exactly one parent. A person recorded while the lead is still in the
  // funnel has no account yet - convert moves them across.
  account_id: z.string().uuid().nullish(),
  lead_id: z.string().uuid().nullish(),
  full_name: z.string(),
  version: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
  // The three parts full_name is composed from, moved off the lead (spec 008).
  salutation: z.string().nullish(),
  first_name: z.string().nullish(),
  last_name: z.string().nullish(),
  role_title: z.string().nullish(),
  email: z.string().nullish(),
  phone: z.string().nullish(),
  notes: z.string().nullish(),
  source: z.string().nullish(),
  /** This person is the lead's Contact — the one name the lead list shows.
   * Exactly one of a lead's people carries it, and it moves only through
   * POST /contacts/{id}/primary (spec 008). */
  is_primary: z.boolean(),
  /** "Đã tiếp cận" on the People grid: has anyone actually spoken to them. */
  contacted: z.boolean(),
  // The committee view (several roles per person) and the personal details
  // the stakeholder panel edits. Wider than buyingRoleSchema on purpose: the
  // multi-role list carries the extended vocabulary the map validates.
  buying_roles: z.array(z.string()),
  // male | female | null (0094) — how sources address them ("ông"/"bà"),
  // never guessed from the name; null renders the neutral avatar.
  gender: z.string().nullish(),
  birth_date: z.string().nullish(),
  birth_year: z.number().int().nullish(),
  linkedin_url: z.string().nullish(),
  /** A stored public portrait exists; fetch it from /crm/contacts/{id}/photo. */
  has_photo: z.boolean(),
  likes: z.array(z.string()),
  dislikes: z.array(z.string()),
  // The dossier facts (0088): editable on the person, inherited from the
  // Key people roster, with the citations that came along.
  expertise: z.string().nullish(),
  education: z.string().nullish(),
  profile: z.string().nullish(),
  appointments: z.array(appointmentEntrySchema),
  other_facts: z.array(otherFactSchema),
  source_urls: z.array(z.string()),
});
export type CrmContact = z.infer<typeof crmContactSchema>;

// ---- opportunities -------------------------------------------------------

/** The five stages the user fixed as final on 2026-08-27. A Kanban column is a
 * stage, so this list and the board's columns are the same list. */
export const opportunityStageSchema = z.enum([
  "prospecting",
  "proposal_quote",
  "negotiation",
  "close_won",
  "close_lost",
]);
export type OpportunityStage = z.infer<typeof opportunityStageSchema>;

/**
 * How sure the owner is that this deal lands in forecast revenue (BD 4.2.1).
 *
 * Optional everywhere by the user's decision of 2026-08-27: blank means "not
 * classified yet", which is a real answer rather than a gap. Never derived from
 * the stage - the BD's "Secured: Đã Closed Won" defines what the level MEANS so
 * a person picks the right one, it is not a rule the system runs.
 */
export const confidenceLevelSchema = z.enum([
  "potential",
  "likely",
  "committed",
  "secured",
]);
export type ConfidenceLevel = z.infer<typeof confidenceLevelSchema>;

/** A rival on an open deal: a name plus the owner's threat call, if made. */
export const competitivePotentialSchema = z.enum(["high", "medium", "low"]);
export type CompetitivePotential = z.infer<typeof competitivePotentialSchema>;
export const competitorSchema = z.object({
  name: z.string(),
  potential: competitivePotentialSchema.nullish(),
  // What they offer, at what price (document 4.2.2); old rows have neither.
  offer: z.string().nullish(),
  price: z.number().nullish(),
});
export type Competitor = z.infer<typeof competitorSchema>;

/** How the customer buys (4.2.2). NULL on the record means not chosen yet. */
export const purchaseProcessSchema = z.enum([
  "unknown",
  "bidding",
  "direct_selected",
]);
export type PurchaseProcess = z.infer<typeof purchaseProcessSchema>;

/** What a person wrote against one manual stage criterion. An unanswered
 * criterion has no entry at all, so there is no blank one to tell apart. */
export const stageCheckSchema = z.object({
  text: z.string(),
  updated_at: z.string(),
  updated_by: z.string().uuid().nullish(),
});
export type StageCheck = z.infer<typeof stageCheckSchema>;

/** One person on a deal's contact list, named from the account's pool. */
export const dealContactSchema = z.object({
  contact_id: z.string().uuid(),
  full_name: z.string(),
  role_title: z.string().nullish(),
  email: z.string().nullish(),
  phone: z.string().nullish(),
});
export type DealContact = z.infer<typeof dealContactSchema>;

export const opportunitySchema = z.object({
  id: z.string().uuid(),
  account_id: z.string().uuid(),
  name: z.string(),
  stage: opportunityStageSchema,
  version: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
  effective_probability: z.number().int(),
  account_name: z.string().nullish(),
  // The deal's contacts (0120): people from the account's pool that somebody
  // has reached. Many per deal; the list view omits them entirely.
  contacts: z.array(dealContactSchema),
  amount: z.number().nullish(),
  net_amount: z.union([z.number(), z.string()]).nullish(),
  priority: z.enum(["high", "medium", "low"]).nullish(),
  probability: z.number().nullish(),
  expected_close_date: z.string().nullish(),
  lost_reason: z.string().nullish(),
  confidence_level: confidenceLevelSchema.nullish(),
  purchase_process: purchaseProcessSchema.nullish(),
  description: z.string().nullish(),
  current_situation: z.string().nullish(),
  customer_needs: z.string().nullish(),
  proposed_solution: z.string().nullish(),
  competitors: z.array(competitorSchema),
  stage_checks: z.record(stageCheckSchema),
  collaborator_user_ids: z.array(z.string().uuid()),
  open_tasks: z.number().int().nullish(),
  overdue_tasks: z.number().int().nullish(),
  owner_user_id: z.string().uuid().nullish(),
});
export type Opportunity = z.infer<typeof opportunitySchema>;

// ---- stage criteria (spec 006 US3) ----------------------------------------

export const criterionSourceSchema = z.enum(["derived", "manual"]);
export type CriterionSource = z.infer<typeof criterionSourceSchema>;

/** One line of the stage pop-up. Both kinds carry a value: a derived line reads
 * it off the record, a manual one is the sentence a person wrote. `done` means
 * the same for both - something answers this criterion. */
export const stageCriterionSchema = z.object({
  code: z.string(),
  label: z.string(),
  source: criterionSourceSchema,
  done: z.boolean(),
  // The answer, shortened for one line ("1,200,000,000 ₫", "CMC, FPT", "They
  // want it before Tet"); null = Unknown. The full text of a manual answer
  // lives on the deal's own `stage_checks`, which is what the editor opens.
  value: z.string().nullish(),
});
export type StageCriterion = z.infer<typeof stageCriterionSchema>;

export const stageCriteriaSchema = z.object({
  stage: opportunityStageSchema,
  criteria: z.array(stageCriterionSchema),
});
export type StageCriteria = z.infer<typeof stageCriteriaSchema>;

// ---- opportunity stakeholder map (BD 05 v1.1, editable, 0116/0117) ---------

/** The 11 default buying-role codes of the BD catalogue. */
export const oppBuyingRoleSchema = z.enum([
  "executive_sponsor",
  "decision_maker",
  "economic_buyer",
  "technical_evaluator",
  "business_evaluator",
  "gatekeeper",
  "end_user",
  "champion",
  "blocker",
  "influencer",
  "coach",
]);
export type OppBuyingRole = z.infer<typeof oppBuyingRoleSchema>;
export const oppAttitudeSchema = z.enum([
  "supportive",
  "neutral",
  "negative",
  "unknown",
]);
export type OppAttitude = z.infer<typeof oppAttitudeSchema>;
export const oppInfluenceLevelSchema = z.enum([
  "high",
  "medium",
  "low",
  "unknown",
]);
export type OppInfluenceLevel = z.infer<typeof oppInfluenceLevelSchema>;
export const oppRelationshipStrengthSchema = z.enum([
  "strong",
  "moderate",
  "weak",
  "none",
]);
export type OppRelationshipStrength = z.infer<
  typeof oppRelationshipStrengthSchema
>;
export const oppIdentityStatusSchema = z.enum([
  "identified",
  "unidentified",
  "inactive",
]);
export type OppIdentityStatus = z.infer<typeof oppIdentityStatusSchema>;
/** How urgently a placeholder card's person must be found (doc 04 4.2.6):
 * must_find before Negotiation, should_find before Close. */
export const oppIdentifyPrioritySchema = z.enum(["must_find", "should_find"]);
export type OppIdentifyPriority = z.infer<typeof oppIdentifyPrioritySchema>;
export const oppCardOriginSchema = z.enum(["ai_generated", "manual", "synced"]);
// "conflicts" is the mutual one: the panel lists it under both people and
// the line carries no arrow (doc 04, nhóm Relationship).
export const oppRelKindSchema = z.enum([
  "reports_to",
  "influences",
  "conflicts",
]);
export type OppRelKind = z.infer<typeof oppRelKindSchema>;
export const oppReportLevelSchema = z.enum(["direct", "indirect"]);
export const oppEdgeStrengthSchema = z.enum(["strong", "medium", "weak"]);
export const oppEdgeNatureSchema = z.enum([
  "supportive",
  "neutral",
  "opposing",
]);

/** Person-stable facts, joined from the contact at read time - never copied. */
export const oppCardContactSchema = z.object({
  id: z.string().uuid(),
  full_name: z.string(),
  role_title: z.string().nullish(),
  email: z.string().nullish(),
  phone: z.string().nullish(),
  has_photo: z.boolean().optional(),
  gender: z.string().nullish(),
});
export type OppCardContact = z.infer<typeof oppCardContactSchema>;

/** One per-deal note entry; the stamp is the entry's, kept across edits. */
export const oppCardNoteSchema = z.object({
  id: z.string().nullish(),
  text: z.string(),
  created_at: z.string().nullish(),
  created_by: z.string().nullish(),
});
export type OppCardNote = z.infer<typeof oppCardNoteSchema>;

export const oppRoleGrantSchema = z.object({
  role_code: z.string(),
  assigned_by: z.enum(["ai", "user"]),
  assigned_at: z.string().nullish(),
});

// Doc 04 "Readiness Perception" — how ready this person believes the company
// is to change. No "unknown" member: null is the unassessed state.
export const oppReadinessSchema = z.enum([
  "growth",
  "urgent",
  "stability",
  "overconfidence",
]);
export type OppReadiness = z.infer<typeof oppReadinessSchema>;

export const oppCardSchema = z.object({
  id: z.string(),
  name: z.string(),
  title: z.string().nullish(),
  contact_id: z.string().nullish(),
  contact: oppCardContactSchema.nullish(),
  identity_status: oppIdentityStatusSchema,
  // Only an unidentified card carries one; bind_contact clears it.
  identify_priority: oppIdentifyPrioritySchema.nullish(),
  attitude: oppAttitudeSchema,
  influence: oppInfluenceLevelSchema,
  relationship_strength: oppRelationshipStrengthSchema,
  relationship_owner_user_id: z.string().nullish(),
  // Nhóm Concern của tab Persona: riêng cơ hội này.
  company_gain: z.string().nullish(),
  personal_concern: z.string().nullish(),
  readiness_perception: oppReadinessSchema.nullish(),
  notes: z.array(oppCardNoteSchema),
  origin: oppCardOriginSchema,
  ai_confidence: z.number().int().nullish(),
  roles: z.array(oppRoleGrantSchema),
  x: z.number(),
  y: z.number(),
  deleted_at: z.string().nullish(),
  // Whether THIS caller may edit the person's shared master data (the pool
  // ladder, computed server-side).
  shared_editable: z.boolean().optional(),
});
export type OppCard = z.infer<typeof oppCardSchema>;

export const oppRelationshipSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  target_id: z.string(),
  kind: oppRelKindSchema,
  report_level: oppReportLevelSchema.nullish(),
  strength: oppEdgeStrengthSchema.nullish(),
  nature: oppEdgeNatureSchema.nullish(),
  note: z.string().nullish(),
  origin: oppCardOriginSchema,
  is_confirmed: z.boolean(),
  ai_confidence: z.number().int().nullish(),
});
export type OppRelationship = z.infer<typeof oppRelationshipSchema>;

export const oppMapMetaSchema = z.object({
  id: z.string().uuid().nullish(),
  version: z.number().int(),
  status: z.enum(["active", "locked"]),
  updated_by: z.string().uuid().nullish(),
  last_ai_run_at: z.string().nullish(),
});

export const oppMapSchema = z.object({
  map: oppMapMetaSchema,
  cards: z.array(oppCardSchema),
  relationships: z.array(oppRelationshipSchema),
  can_edit: z.boolean(),
  pending_suggestions: z.number().int(),
  // The account's owner may run person research from the panel (owner-only).
  is_account_owner: z.boolean().optional(),
});
export type OppMap = z.infer<typeof oppMapSchema>;

export const oppMapMutationSchema = z.object({
  map: oppMapMetaSchema,
  cards: z.array(oppCardSchema),
  relationships: z.array(oppRelationshipSchema),
  warnings: z.array(z.string()),
  temp_map: z.record(z.string()),
  needs_choice: z.array(z.string()),
});
export type OppMapMutation = z.infer<typeof oppMapMutationSchema>;

export const oppRevisionSchema = z.object({
  version: z.number().int(),
  reason: z.string(),
  actor: z.string().uuid().nullish(),
  created_at: z.string(),
  card_count: z.number().int(),
});
export type OppRevision = z.infer<typeof oppRevisionSchema>;

export const oppSuggestionSchema = z.object({
  id: z.string().uuid(),
  batch_id: z.string().uuid(),
  kind: z.enum(["new_card", "new_relationship"]),
  payload: z.record(z.unknown()),
  confidence: z.number().int(),
  reason: z.string(),
  source_kind: z.enum(["crm", "ai_research"]),
  status: z.enum(["pending", "accepted", "rejected", "superseded"]),
  preselected: z.boolean(),
  low_confidence: z.boolean(),
  target_card_id: z.string().uuid().nullish(),
  created_at: z.string(),
});
export type OppSuggestion = z.infer<typeof oppSuggestionSchema>;

/** GET /contacts/{id}/usage - the delete-confirm dialog's blast radius. */
export const contactUsageSchema = z.object({
  deals: z.array(
    z.object({
      opportunity_id: z.string().uuid(),
      name: z.string(),
      owner_user_id: z.string().uuid().nullish(),
      open: z.boolean(),
      via_card: z.boolean(),
      via_primary: z.boolean(),
    }),
  ),
  on_key_people_map: z.boolean(),
  can_delete: z.boolean(),
  denial_code: z.string().nullish(),
  denial_message: z.string().nullish(),
});
export type ContactUsage = z.infer<typeof contactUsageSchema>;

/**
 * GET /contacts/duplicate - the person already on file, or null.
 *
 * The create form asks for this as the name is typed so its warning is the
 * very rule POST /contacts will judge the save by; `matched_on` says which of
 * the three tiers fired, because "trùng email" and "trùng tên" ask the reader
 * for quite different amounts of trust.
 */
export const duplicateContactSchema = z.object({
  contact_id: z.string().uuid(),
  full_name: z.string(),
  matched_on: z.enum(["email", "phone", "name"]),
  account_id: z.string().uuid().nullish(),
  lead_id: z.string().uuid().nullish(),
  account_name: z.string().nullish(),
});
export type DuplicateContact = z.infer<typeof duplicateContactSchema>;

/** Where a pool person came from — the add dialog's source badge. */
export const oppCandidateSourceSchema = z.enum([
  "contact",
  "ai_research",
  "map_people",
  "placeholder",
]);
export type OppCandidateSource = z.infer<typeof oppCandidateSourceSchema>;

export const oppPersonCandidateSchema = z.object({
  source_key: z.string(),
  contact_id: z.string().uuid().nullish(),
  name: z.string(),
  title: z.string().nullish(),
  phone: z.string().nullish(),
  org_tier: z.number().int().nullish(),
  // A string, not the enum: a source the server grows later still renders.
  source_label: z.string(),
  contacted: z.boolean(),
  already_on_map: z.boolean(),
  // Same name as someone already on the map — ask before adding.
  needs_confirm: z.boolean(),
  // Only with ?for_card_id: the ranking against one placeholder card.
  match_confidence: z.number().int().nullish(),
  match_reason: z.string().nullish(),
});
export type OppPersonCandidate = z.infer<typeof oppPersonCandidateSchema>;

export const oppSuggestRunSchema = z.object({
  batch_id: z.string().uuid(),
  created: z.number().int(),
  skipped: z.number().int(),
  // MSG01 when the account's people pool is empty.
  notice: z.string().nullish(),
  suggestions: z.array(oppSuggestionSchema),
});
export type OppSuggestRun = z.infer<typeof oppSuggestRunSchema>;

/** One ops-batch entry; the discriminant is `op`, mirroring the wire DTOs. */
export const oppMapOpSchema = z.discriminatedUnion("op", [
  z.object({
    op: z.literal("add_card"),
    temp_id: z.string().optional(),
    position: z.object({ x: z.number(), y: z.number() }),
    name: z.string().nullish(),
    title: z.string().nullish(),
    contact_id: z.string().uuid().nullish(),
    attitude: oppAttitudeSchema.optional(),
    influence: oppInfluenceLevelSchema.optional(),
    relationship_strength: oppRelationshipStrengthSchema.optional(),
    roles: z.array(z.string()).optional(),
    identify_priority: oppIdentifyPrioritySchema.nullish(),
  }),
  z.object({
    op: z.literal("update_card"),
    card_id: z.string(),
    name: z.string().optional(),
    title: z.string().optional(),
    attitude: oppAttitudeSchema.optional(),
    influence: oppInfluenceLevelSchema.optional(),
    relationship_strength: oppRelationshipStrengthSchema.optional(),
    relationship_owner_user_id: z.string().uuid().optional(),
    clear_relationship_owner: z.boolean().optional(),
    company_gain: z.string().max(2000).optional(),
    personal_concern: z.string().max(2000).optional(),
    readiness_perception: oppReadinessSchema.optional(),
    clear_company_gain: z.boolean().optional(),
    clear_personal_concern: z.boolean().optional(),
    clear_readiness: z.boolean().optional(),
    identify_priority: oppIdentifyPrioritySchema.nullish(),
    clear_identify_priority: z.boolean().optional(),
  }),
  z.object({
    op: z.literal("add_card_note"),
    card_id: z.string(),
    text: z.string(),
  }),
  z.object({
    op: z.literal("set_card_notes"),
    card_id: z.string(),
    notes: z.array(z.object({ id: z.string().nullish(), text: z.string() })),
  }),
  z.object({
    op: z.literal("update_contact_attrs"),
    card_id: z.string(),
    patch: z.record(z.unknown()),
  }),
  z.object({
    op: z.literal("append_contact_fact"),
    card_id: z.string(),
    text: z.string(),
  }),
  z.object({
    op: z.literal("set_roles"),
    card_id: z.string(),
    role_codes: z.array(z.string()),
  }),
  z.object({
    op: z.literal("bind_contact"),
    card_id: z.string(),
    contact_id: z.string().uuid(),
  }),
  z.object({
    op: z.literal("remove_card"),
    card_id: z.string(),
    // FC-08: where the subordinates go — true = up to the removed card's
    // manager, false = become roots; omitted parks a needs_choice question.
    reattach_reports: z.boolean().optional(),
  }),
  z.object({ op: z.literal("restore_card"), card_id: z.string() }),
  z.object({
    op: z.literal("move_card"),
    card_id: z.string(),
    position: z.object({ x: z.number(), y: z.number() }),
  }),
  z.object({
    op: z.literal("add_relationship"),
    temp_id: z.string().optional(),
    source_id: z.string(),
    target_id: z.string(),
    kind: oppRelKindSchema,
    report_level: oppReportLevelSchema.optional(),
    strength: oppEdgeStrengthSchema.optional(),
    nature: oppEdgeNatureSchema.optional(),
    note: z.string().optional(),
    replace_existing_manager: z.boolean().optional(),
  }),
  z.object({
    op: z.literal("update_relationship"),
    rel_id: z.string(),
    report_level: oppReportLevelSchema.optional(),
    strength: oppEdgeStrengthSchema.optional(),
    nature: oppEdgeNatureSchema.optional(),
    note: z.string().optional(),
    is_confirmed: z.boolean().optional(),
  }),
  z.object({ op: z.literal("remove_relationship"), rel_id: z.string() }),
]);
export type OppMapOp = z.infer<typeof oppMapOpSchema>;

// ---- home ----------------------------------------------------------------

/** Open tasks grouped the way a morning triage goes. */
export const taskBucketsSchema = z.object({
  overdue: z.number().int(),
  today: z.number().int(),
  this_week: z.number().int(),
  later: z.number().int(),
  undated: z.number().int(),
});
export type TaskBuckets = z.infer<typeof taskBucketsSchema>;

/**
 * `won_amount` is what the customer agreed to. The signed pair that used to sit
 * beside it went with migration 0113: "signed" meant *Close Won AND a signature
 * date*, and the date is a column the business document never defines.
 */
export const pipelineTotalsSchema = z.object({
  open_count: z.number().int(),
  open_amount: z.number(),
  won_count: z.number().int(),
  won_amount: z.number(),
});
export type PipelineTotals = z.infer<typeof pipelineTotalsSchema>;

export const funnelCountsSchema = z.object({
  leads: z.number().int(),
  qualified: z.number().int(),
  converted: z.number().int(),
  opportunities: z.number().int(),
  won: z.number().int(),
});
export type FunnelCounts = z.infer<typeof funnelCountsSchema>;

export const ownerPerformanceSchema = z.object({
  owner_user_id: z.string().uuid().nullish(),
  open_count: z.number().int(),
  open_amount: z.number(),
  won_count: z.number().int(),
  won_amount: z.number(),
});
export type OwnerPerformance = z.infer<typeof ownerPerformanceSchema>;

export const topAccountSchema = z.object({
  account_id: z.string().uuid(),
  name: z.string(),
  owner_user_id: z.string().uuid().nullish(),
  open_count: z.number().int(),
  open_amount: z.number(),
});
export type TopAccount = z.infer<typeof topAccountSchema>;

// ---- search --------------------------------------------------------------

export const accountHitSchema = z.object({
  account_id: z.string().uuid(),
  name: z.string(),
  industry: z.string().nullish(),
  tax_code: z.string().nullish(),
  owner_user_id: z.string().uuid().nullish(),
});

export const opportunityHitSchema = z.object({
  opportunity_id: z.string().uuid(),
  name: z.string(),
  account_id: z.string().uuid(),
  account_name: z.string().nullish(),
  stage: opportunityStageSchema,
  amount: z.number().nullish(),
});

export const contactHitSchema = z.object({
  contact_id: z.string().uuid(),
  full_name: z.string(),
  account_id: z.string().uuid(),
  account_name: z.string().nullish(),
  role_title: z.string().nullish(),
});

/** Three lists, not one ranked list: a score across three grains is invented. */
export const searchHitsSchema = z.object({
  accounts: z.array(accountHitSchema),
  opportunities: z.array(opportunityHitSchema),
  contacts: z.array(contactHitSchema),
});
export type SearchHits = z.infer<typeof searchHitsSchema>;
export type AccountHit = z.infer<typeof accountHitSchema>;
export type OpportunityHit = z.infer<typeof opportunityHitSchema>;
export type ContactHit = z.infer<typeof contactHitSchema>;

// ---- team feed -----------------------------------------------------------

export const teamFeedKindSchema = z.enum(["activity", "note", "document"]);
export type TeamFeedKind = z.infer<typeof teamFeedKindSchema>;

/** One thing a colleague did. Three sources, one row shape. */
export const teamFeedItemSchema = z.object({
  kind: teamFeedKindSchema,
  occurred_at: z.string(),
  actor_user_id: z.string().uuid().nullish(),
  summary: z.string(),
  subject_type: z.string(),
  subject_id: z.string().uuid(),
  subject_name: z.string().nullish(),
});
export type TeamFeedItem = z.infer<typeof teamFeedItemSchema>;

export const teamFeedSchema = z.object({
  items: z.array(teamFeedItemSchema),
});
export type TeamFeed = z.infer<typeof teamFeedSchema>;

// ---- broadcasts ----------------------------------------------------------

/** A notice a manager sent down the team. Posted or withdrawn, never edited. */
export const broadcastSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  posted_by: z.string().uuid(),
  created_at: z.string(),
  body: z.string().nullish(),
  company_name: z.string().nullish(),
  account_id: z.string().uuid().nullish(),
  account_name: z.string().nullish(),
});
export type Broadcast = z.infer<typeof broadcastSchema>;

// ---- dashboard -----------------------------------------------------------

/** Enough of a deal to name it and open it from a page that is not its own. */
export const dealRefSchema = z.object({
  opportunity_id: z.string().uuid(),
  name: z.string(),
  account_id: z.string().uuid(),
  account_name: z.string().nullish(),
  stage: opportunityStageSchema,
  amount: z.number(),
  owner_user_id: z.string().uuid().nullish(),
  days_idle: z.number().int().nullish(),
});
export type DealRef = z.infer<typeof dealRefSchema>;

export const stageSliceSchema = z.object({
  stage: opportunityStageSchema,
  count: z.number().int(),
  amount: z.number(),
});
export type StageSlice = z.infer<typeof stageSliceSchema>;

// Three different dates bound the three halves of this bundle, so a single
// period chip over the whole tab would assert a date that does not exist:
// `funnel` counts what was CREATED in the quarter, `stages` and `open_amount`
// what is expected to CLOSE in it, and `stagnant` is measured against
// `stagnant_as_of` and not bounded by the quarter at all.
//
// `undated_*` is not optional on purpose. `expected_close_date` is nullable, so
// those deals are open, are absent from `stages`, and this schema strips keys it
// does not name - a field left out here is a number the page can never show.
export const pipelineHealthBundleSchema = z.object({
  period: z.string(),
  funnel: funnelCountsSchema,
  stages: z.array(stageSliceSchema),
  open_amount: z.number(),
  undated_open_count: z.number().int(),
  undated_open_amount: z.number(),
  stagnant_after_days: z.number().int(),
  stagnant: z.array(dealRefSchema),
  stagnant_as_of: z.string(),
});
export type PipelineHealthBundle = z.infer<typeof pipelineHealthBundleSchema>;

// ---- tasks ---------------------------------------------------------------

// Three statuses since spec 006 (migration 0114). Completed is the tick;
// the other two are both "still owed".
export const taskStatusSchema = z.enum([
  "not_started",
  "in_progress",
  "completed",
]);
export type TaskStatus = z.infer<typeof taskStatusSchema>;
/** Overdue / Upcoming beside an unfinished task; nothing on a completed one. */
export const scheduleLabelSchema = z.enum(["overdue", "upcoming"]);
export type ScheduleLabel = z.infer<typeof scheduleLabelSchema>;
export const taskOriginSchema = z.enum(["manual", "ai"]);

// A follow-up owed, or a meeting in the diary (AC-LEADACT-001). Events share
// the task record because the BD asked for exactly that shape.
export const taskKindSchema = z.enum(["task", "event"]);
export type TaskKind = z.infer<typeof taskKindSchema>;

export const taskPrioritySchema = z.enum(["low", "medium", "high"]);
export type TaskPriority = z.infer<typeof taskPrioritySchema>;

export const salesTaskSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  status: taskStatusSchema,
  origin: taskOriginSchema,
  version: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
  rationale: z.string().nullish(),
  description: z.string().nullish(),
  // Always present: the column is NOT NULL, and a zod default here would
  // make the schema's input and output types differ.
  kind: taskKindSchema,
  priority: taskPrioritySchema.nullish(),
  // Events only: when the meeting starts, as an ISO timestamp.
  starts_at: z.string().nullish(),
  due_date: z.string().nullish(),
  // The deadline with a time of day (opportunity tasks); a row has one or the other.
  due_at: z.string().nullish(),
  done_at: z.string().nullish(),
  // Computed by the server at read time, never stored.
  schedule_label: scheduleLabelSchema.nullish(),
  assigned_to_user_id: z.string().uuid().nullish(),
  lead_id: z.string().uuid().nullish(),
  account_id: z.string().uuid().nullish(),
  opportunity_id: z.string().uuid().nullish(),
  // The record the task hangs off, ready for the "Related to" column: the kind
  // (which id is set) plus the resolved name. Both null for a free-standing task.
  related_type: z.enum(["opportunity", "account", "lead"]).nullish(),
  related_name: z.string().nullish(),
});
export type SalesTask = z.infer<typeof salesTaskSchema>;

/** How the edit form re-points a task: one of the records, or cleared. */
export const relatedRefSchema = z.object({
  type: z.enum(["opportunity", "account", "lead", "none"]),
  id: z.string().uuid().nullish(),
});
export type RelatedRef = z.infer<typeof relatedRefSchema>;

/** One message in the conversation under a task; attachments are document ids. */
export const taskCommentSchema = z.object({
  id: z.string().uuid(),
  task_id: z.string().uuid(),
  author_user_id: z.string().uuid(),
  body: z.string(),
  attachment_document_ids: z.array(z.string().uuid()),
  version: z.number().int(),
  created_at: z.string(),
});
export type TaskComment = z.infer<typeof taskCommentSchema>;

// ---- notes ---------------------------------------------------------------

/** What a person wrote down about one CRM record. */
export const crmNoteSchema = z.object({
  id: z.string().uuid(),
  body: z.string(),
  version: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
  author_user_id: z.string().uuid().nullish(),
  lead_id: z.string().uuid().nullish(),
  account_id: z.string().uuid().nullish(),
  opportunity_id: z.string().uuid().nullish(),
});
export type CrmNote = z.infer<typeof crmNoteSchema>;

// ---- timeline ------------------------------------------------------------

export const activitySubjectSchema = z.enum([
  "lead",
  "account",
  "contact",
  "opportunity",
]);
export type ActivitySubject = z.infer<typeof activitySubjectSchema>;

export const crmActivitySchema = z.object({
  id: z.string().uuid(),
  subject_type: activitySubjectSchema,
  subject_id: z.string().uuid(),
  verb: z.string(),
  actor_kind: z.enum(["user", "agent", "system"]),
  occurred_at: z.string(),
  actor_user_id: z.string().uuid().nullish(),
  payload: z.record(z.unknown()),
});
export type CrmActivity = z.infer<typeof crmActivitySchema>;

// ---- documents -----------------------------------------------------------

export const documentScopeSchema = z.enum(["lead", "account", "opportunity"]);
export type DocumentScope = z.infer<typeof documentScopeSchema>;

/** What kind of paper a file is; null on anything filed before categories. */
export const documentCategorySchema = z.enum([
  "contract",
  "proposal",
  "minutes",
  "other",
]);
export type DocumentCategory = z.infer<typeof documentCategorySchema>;

export const crmDocumentSchema = z.object({
  id: z.string().uuid(),
  scope_type: documentScopeSchema,
  scope_id: z.string().uuid(),
  filename: z.string(),
  mime: z.string(),
  size_bytes: z.number().int(),
  created_at: z.string(),
  uploaded_by: z.string().uuid().nullish(),
  // Set when the file was queued to be read for retrieval; poll the ingest
  // job to know when the assistant can answer about it.
  index_job_id: z.string().uuid().nullish(),
  category: documentCategorySchema.nullish(),
});
export type CrmDocument = z.infer<typeof crmDocumentSchema>;

// ---- funnel --------------------------------------------------------------

export const convertResultSchema = z.object({
  lead_id: z.string().uuid(),
  account_id: z.string().uuid(),
  contact_id: z.string().uuid().nullish(),
  opportunity_id: z.string().uuid().nullish(),
  already_converted: z.boolean(),
});
export type ConvertResult = z.infer<typeof convertResultSchema>;

export const duplicateCandidateSchema = z.object({
  account_id: z.string().uuid(),
  name: z.string(),
  tax_code: z.string().nullish(),
  website: z.string().nullish(),
  matched_by: z.string(),
});
export type DuplicateCandidate = z.infer<typeof duplicateCandidateSchema>;

/**
 * One filed entity a typed company name matched, as step 1 of the create form
 * shows it. "FPT" is three registered companies and "Heineken Việt Nam" four,
 * and which one somebody meant is not something evidence can settle - so it is
 * asked before anything else is looked up, and the answer decides what the rest
 * of the lookup is even about.
 */
export const companyMatchSchema = z.object({
  legal_name: z.string(),
  registration_number: z.string(),
  hq_address: z.string(),
  source_url: z.string(),
  // Only when the register's snippet already printed it (spec 002, R3).
  industry: z.string(),
});
export type CompanyMatch = z.infer<typeof companyMatchSchema>;

/** What the first pass found for a typed name. Empty is a normal answer. */
export const companyMatchesSchema = z.object({
  name: z.string(),
  matches: z.array(companyMatchSchema),
});
export type CompanyMatches = z.infer<typeof companyMatchesSchema>;

export const enrichmentDraftSchema = z.object({
  name: z.string(),
  legal_name: z.string().nullish(),
  tax_code: z.string().nullish(),
  industry: z.string().nullish(),
  website: z.string().nullish(),
  hq_address: z.string().nullish(),
  size: z.string().nullish(),
  summary: z.string().nullish(),
  // Year T-1 revenue as bare VND digits (spec 002, R4).
  annual_revenue_vnd: z.string().nullish(),
  company_email: z.string().nullish(),
  sources: z.record(z.string()),
});
export type EnrichmentDraft = z.infer<typeof enrichmentDraftSchema>;

// ---- lead scoring (read models the CRM UI shows) -------------------------

/**
 * Which scoring frame a number was computed in. Never omitted from a score:
 * since spec 012 every company writes its own template, and 46 means two
 * different things on an 87-point scale and a 60-point one.
 */
export const templateRefSchema = z.object({
  // null is the system default template, and means nothing else.
  id: z.string().uuid().nullable(),
  name: z.string(),
});
export type TemplateRef = z.infer<typeof templateRefSchema>;

/**
 * The "Đánh giá Lead (AI)" block — contract B7, for ONE template. What the lead
 * page reads; the rest of the record belongs to the detail screen, which asks
 * for it separately.
 *
 * `null` from the API means this lead has never been scored under this
 * template. An empty state, not a zero.
 */
export const leadAssessmentSchema = z.object({
  // Summed from the axes by the engine, never by the model.
  score: z.number(),
  // The template's total scale. Nothing renders `score` without it.
  scale: z.number(),
  // null on rows scored before the tier existed.
  confidence_tier: z.enum(["high", "medium", "low"]).nullable(),
  summary: z.string(),
  updated_at: z.string(),
  running: z.boolean(),
  template: templateRefSchema,
  // The score predates a change — to the lead, or to the template (FR-014).
  // The two call for different sentences, so the reason travels with the flag.
  stale: z.boolean(),
  stale_reason: z.enum(["lead_changed", "template_changed"]).nullable(),
  // How many criteria came back with no evidence on the run that produced it.
  unknown_count: z.number(),
});
export type LeadAssessment = z.infer<typeof leadAssessmentSchema>;

/**
 * Contract B8 — the "Detailed analysis" screen. Three rules the API enforces
 * and this schema therefore never has to: no group code at any level, an
 * unknown criterion scores 0 with a fixed reason, and every switched-on
 * criterion gets a row even when a warning fired.
 */
export const criterionRowSchema = z.object({
  criterion_id: z.string(),
  name: z.string(),
  points: z.number(),
  max: z.number(),
  reason: z.string(),
  citation: z.string().nullable(),
  is_unknown: z.boolean(),
  // Where this criterion was meant to be read from, so a reader knows where to
  // go and check rather than guessing which source was meant.
  evidence_source: z.string(),
});
export type CriterionRow = z.infer<typeof criterionRowSchema>;

/**
 * One axis of a scorecard, with both totals: `raw` is what the criteria earned
 * and `final` is what survived the flags that deduct from this axis. Equal when
 * nothing was deducted.
 */
export const axisSchema = z.object({
  axis_id: z.string(),
  name: z.string(),
  raw: z.number(),
  deduction: z.number(),
  final: z.number(),
  max: z.number(),
  criteria: z.array(criterionRowSchema),
});
export type Axis = z.infer<typeof axisSchema>;

export const assessmentDetailSchema = z.object({
  template: templateRefSchema,
  scale: z.number(),
  warnings: z.array(
    z.object({
      criterion_id: z.string(),
      name: z.string(),
      evidence: z.string(),
    }),
  ),
  // As many axes as the template declares, in its order and under its names.
  // FIT and INTENT were two fields here until spec 012; a company scoring on
  // "Chiến lược / Cấp bách / Quan hệ" has three, named its own way.
  axes: z.array(axisSchema),
  red_flags: z.array(
    z.object({
      flag_id: z.string(),
      name: z.string(),
      deduction: z.number(),
      evidence: z.string(),
    }),
  ),
  formula: z.string(),
  reference_action: z.string(),
  ai_filled_fields: z.array(
    z.object({
      field: z.string(),
      source_document: z.string(),
      status: z.string(),
    }),
  ),
  updated_at: z.string(),
});
export type AssessmentDetail = z.infer<typeof assessmentDetailSchema>;

export const scoringResultSchema = z.object({
  id: z.string().uuid(),
  lead_id: z.string(),
  run_id: z.string().uuid(),
  rubric_version: z.string(),
  criterion_scores: z.array(
    z.object({
      criterion_id: z.string(),
      // null = no evidence either way, which is not the same as a scored zero.
      points: z.number().nullish(),
      reason: z.string(),
      confidence: z.number(),
      // Where the evidence is, so a reader can check the claim.
      citation: z.string().nullish(),
    }),
  ),
  fit_score: z.number(),
  intent_raw: z.number(),
  intent_final: z.number(),
  // Internal, and never rendered: spec 001 section 6.3 says a reader cares about the
  // action, not the bucket. Kept on the read model because the leads list and
  // the history line still sort and group by it server-side.
  group_code: z.string(),
  // The rubric's default action for that group, verbatim from its YAML.
  group_action: z.string(),
  // Rubric warning criteria the agent flagged. A warning never stops a score
  // (spec 001 section 5.1 step 1) — it travels beside one.
  warnings: z.array(z.string()),
  // The agent's reasoning in prose, and how much of the rubric stood on real
  // evidence when it wrote it.
  summary: z.string(),
  confidence_tier: z.enum(["high", "medium", "low"]).nullish(),
  evidence_count: z.number().nullish(),
  low_confidence: z.boolean(),
  created_at: z.string(),
  // ---- which frame this row was scored in (spec 012) ----
  // null = the system default template.
  template_id: z.string().uuid().nullish(),
  // The definition's digest at scoring time; what "this score predates an
  // edit" is answered from, with no version number to compare.
  template_fingerprint: z.string().nullish(),
  evidence_fingerprint: z.string().nullish(),
  axis_scores: z
    .array(
      z.object({
        axis_id: z.string(),
        name: z.string(),
        raw: z.number(),
        deduction: z.number(),
        final: z.number(),
        max: z.number(),
      }),
    )
    .nullish(),
  // The scale this row was computed on. `fit_score`/`intent_*` above are the
  // default template's two-axis shape and stay 0 for any other template.
  scale: z.number().nullish(),
  group_name: z.string().nullish(),
});
export type ScoringResult = z.infer<typeof scoringResultSchema>;

// ---- score templates (spec 012) ------------------------------------------

/**
 * One row of the template picker and of the management list (contract B1).
 *
 * `can_edit` is computed on the server from ownership, so hiding a menu item
 * and refusing the write agree. Hiding a button is not authorization — B4
 * checks again.
 */
export const scoreTemplateSummarySchema = z.object({
  id: z.string().uuid().nullable(),
  name: z.string(),
  created_by: z.string().uuid().nullable(),
  updated_at: z.string().nullable(),
  is_default: z.boolean(),
  can_edit: z.boolean(),
  scale: z.number(),
  axis_names: z.array(z.string()),
  criteria_count: z.number(),
});
export type ScoreTemplateSummary = z.infer<typeof scoreTemplateSummarySchema>;

export const templateLevelSchema = z.object({
  points: z.number(),
  desc: z.string(),
});

export const templateCriterionSchema = z.object({
  id: z.string(),
  name: z.string(),
  axis_id: z.string(),
  enabled: z.boolean(),
  evidence_source: z.enum([
    "fields",
    "notes",
    "documents",
    "people",
    "timeline",
    "research",
  ]),
  guidance: z.string().nullable(),
  levels: z.array(templateLevelSchema),
  system_scored: z.boolean(),
});
export type TemplateCriterion = z.infer<typeof templateCriterionSchema>;

export const templateGroupSchema = z.object({
  id: z.string(),
  name: z.string(),
  action: z.string(),
  // An axis left out is not examined at all.
  min_by_axis: z.record(z.number()),
  // FR-006b: a lead that clears the thresholds but has a zero on one of the
  // heaviest criteria falls through to the next row that fits.
  require_top_weight_nonzero: z.boolean(),
  // Minimums on named criteria, for gates a per-axis threshold cannot express.
  // The shipped default template carries two; the editor round-trips them.
  // Always sent by the API, so required here: a default would make the parsed
  // type differ from the input type and every consumer would have to widen.
  min_by_criterion: z.record(z.number()),
});
export type TemplateGroup = z.infer<typeof templateGroupSchema>;

export const scoreTemplateDefinitionSchema = z.object({
  schema_version: z.string(),
  axes: z.array(z.object({ id: z.string(), name: z.string() })),
  criteria: z.array(templateCriterionSchema),
  warnings: z.array(
    z.object({ id: z.string(), rule: z.string(), source: z.string() }),
  ),
  red_flags: z.array(
    z.object({
      id: z.string(),
      rule: z.string(),
      deduct: z.number(),
      axis_id: z.string(),
    }),
  ),
  // The one flag code raises, from days of silence. A person edits the numbers;
  // nobody reports it, because counting days is arithmetic.
  silence_flag: z
    .object({
      id: z.string(),
      rule: z.string(),
      deduct_per_period: z.number(),
      period_days: z.number(),
      cap: z.number(),
      axis_id: z.string(),
    })
    .nullable(),
  groups: z.array(templateGroupSchema),
  benchmarks: z.object({
    minimum_annual_revenue_vnd: z.number(),
    deal_size_threshold_vnd: z.number(),
    it_spend_share_of_revenue: z.number(),
    served_regions: z.array(z.string()),
    industries: z.array(
      z.object({
        name: z.string(),
        tier: z.string(),
        revenue_median_vnd: z.number(),
        reference_cases: z.array(z.string()),
      }),
    ),
  }),
});
export type ScoreTemplateDefinition = z.infer<
  typeof scoreTemplateDefinitionSchema
>;

/**
 * One template in full (contract B2), plus the numbers the editor would
 * otherwise derive — so the scale on screen is the scale that will be scored
 * against, rather than a second calculation that could agree with itself.
 */
export const scoreTemplateSchema = z.object({
  id: z.string().uuid().nullable(),
  name: z.string(),
  created_by: z.string().uuid().nullable(),
  can_edit: z.boolean(),
  fingerprint: z.string(),
  updated_at: z.string().nullable(),
  definition: scoreTemplateDefinitionSchema,
  axis_scales: z.record(z.number()),
  scale: z.number(),
  top_weight_criteria: z.array(z.string()),
  // Measured ceilings, read from the API rather than repeated in the client.
  max_criteria: z.number(),
  max_flags: z.number(),
});
export type ScoreTemplate = z.infer<typeof scoreTemplateSchema>;

/** Which template the CALLER is scoring with (contracts B5/B6). */
export const templateSelectionSchema = z.object({
  template_id: z.string().uuid().nullable(),
  template_name: z.string(),
  // Set once, after somebody deleted the template this person was using. The
  // client shows one line and then clears it by writing the selection back.
  deleted_template_name: z.string().nullable(),
});
export type TemplateSelection = z.infer<typeof templateSelectionSchema>;

/**
 * Whether a scoring run is working on a lead right now.
 *
 * Separate from the scorecard because the two answer different questions and a
 * surface needs both: the scorecard says what was decided last time, this says
 * whether that answer is about to be replaced. A page holding only the first
 * cannot tell "never scored" from "being scored", and shows the second as if
 * it were a failure.
 */
export const leadScoringActivitySchema = z.object({
  running: z.boolean(),
  running_since: z.string().nullable(),
});

export type LeadScoringActivity = z.infer<typeof leadScoringActivitySchema>;

/**
 * What the lead scoring stream pushes. The finished event carries the scorecard
 * itself: the watcher is already authorized and the server has already read it,
 * so asking for it again would add a round trip at the one moment the person is
 * actually waiting.
 */
export const leadScoringEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("scoring_started"),
    data: z.object({ run_id: z.string() }),
  }),
  z.object({
    type: z.literal("scoring_finished"),
    data: z.object({ result: scoringResultSchema }),
  }),
  z.object({
    type: z.literal("scoring_failed"),
    data: z.object({ run_id: z.string() }),
  }),
]);

export type LeadScoringEvent = z.infer<typeof leadScoringEventSchema>;

/**
 * The screening frame the scorer applies, published so the lead form can show
 * it. An industry outside `industries` is a DQ3 candidate and a revenue under
 * `minimum_annual_revenue_vnd` is DQ1 outright - both end a lead before any
 * criterion is scored, so a form that hides them is letting people fail a rule
 * they were never shown.
 */
export const idealCustomerProfileSchema = z.object({
  benchmarks_version: z.string(),
  minimum_annual_revenue_vnd: z.number(),
  deal_size_threshold_vnd: z.number(),
  served_regions: z.array(z.string()),
  industries: z.array(
    z.object({
      name: z.string(),
      // "core" = trọng tâm, "adjacent" = lân cận.
      tier: z.string(),
      has_reference_case: z.boolean(),
    }),
  ),
  // The lead-source vocabulary the create form picks from, worst source
  // first — the rubric's own `lead_source` levels (FR-LEADCREATE-007).
  lead_sources: z.array(z.string()),
  // The Industry dropdown's vocabulary (spec 002, R10) — a coverage catalogue,
  // deliberately separate from `industries` (the screening law above).
  industry_catalogue: z.array(z.string()),
});
export type IdealCustomerProfile = z.infer<typeof idealCustomerProfileSchema>;

// ---- pages ---------------------------------------------------------------

export function pageOf<T extends z.ZodTypeAny>(item: T) {
  return z.object({
    items: z.array(item),
    total: z.number().int(),
    limit: z.number().int(),
    offset: z.number().int(),
  });
}

export const leadPageSchema = pageOf(leadSchema);
export const accountPageSchema = pageOf(accountSchema);
export const contactPageSchema = pageOf(crmContactSchema);
export const opportunityPageSchema = pageOf(opportunitySchema);

/**
 * The opportunity list's headline figures, computed by the database over the
 * same filter the table is showing. Never summed in the browser: a page holds
 * ten rows, so a browser-side total would be a total of ten rows.
 */
export const pipelineSummaryRowSchema = z.object({
  stage: opportunityStageSchema,
  probability: z.number().int(),
  /** True when the percentage is the stage's default rather than one typed on
   *  the deal. */
  from_stage_default: z.boolean(),
  opportunity_count: z.number().int(),
  amount_total: z.number().int(),
  estimated_revenue: z.number().int(),
});
export type PipelineSummaryRow = z.infer<typeof pipelineSummaryRowSchema>;

export const pipelineSummarySchema = z.object({
  total_pipeline: z.number().int(),
  opportunity_count: z.number().int(),
  /** The arithmetic behind `total_pipeline`, so the figure can be opened and
   *  checked rather than believed. The rows sum to it exactly. */
  rows: z.array(pipelineSummaryRowSchema),
});
export type PipelineSummary = z.infer<typeof pipelineSummarySchema>;
export const homeBriefSchema = z.object({
  priority_tasks: z.array(salesTaskSchema),
  task_buckets: taskBucketsSchema,
  pipeline: pipelineTotalsSchema,
  leads_open: z.number().int(),
});
export type HomeBrief = z.infer<typeof homeBriefSchema>;

export const homeTeamSchema = z.object({
  pipeline: pipelineTotalsSchema,
  funnel: funnelCountsSchema,
  by_owner: z.array(ownerPerformanceSchema),
  top_accounts: z.array(topAccountSchema),
});
export type HomeTeam = z.infer<typeof homeTeamSchema>;

export const taskPageSchema = pageOf(salesTaskSchema);
export const activityPageSchema = pageOf(crmActivitySchema);
export const documentPageSchema = pageOf(crmDocumentSchema);
export const notePageSchema = pageOf(crmNoteSchema);

export type LeadPage = z.infer<typeof leadPageSchema>;
export type AccountPage = z.infer<typeof accountPageSchema>;
export type ContactPage = z.infer<typeof contactPageSchema>;
export type OpportunityPage = z.infer<typeof opportunityPageSchema>;
export type TaskPage = z.infer<typeof taskPageSchema>;
export type ActivityPage = z.infer<typeof activityPageSchema>;
export type DocumentPage = z.infer<typeof documentPageSchema>;
export type NotePage = z.infer<typeof notePageSchema>;

// ---- stakeholder map -----------------------------------------------------
// The decision-power tree on one account (SRS-STK-001). Ops travel loosely
// typed — the server's discriminated union is the validator of record — but
// everything coming BACK is checked here, because the canvas renders it.

export const stakeholderUnitSchema = z.object({
  id: z.string(),
  name: z.string(),
  parent_unit_id: z.string().nullish(),
  x: z.number(),
  y: z.number(),
  width: z.number().nullish(),
  height: z.number().nullish(),
  source: z.string(),
  evidence: z.record(z.string(), z.unknown()),
});
export type StakeholderUnit = z.infer<typeof stakeholderUnitSchema>;

/** One card on the Key People map. Since 0120 `id` IS the person's contact id:
 * the account's pool is the map, so a card and a person are one thing and
 * `contact_id` is kept only as the name the client already reads it by. */
export const stakeholderNodeSchema = z.object({
  id: z.string(),
  contact_id: z.string(),
  unit_id: z.string().nullish(),
  x: z.number(),
  y: z.number(),
  engagement: z.string().nullish(),
  org_tier: z.number().int().nullish(),
  description: z.string().nullish(),
  source: z.string(),
  field_sources: z.record(z.string(), z.unknown()),
});
export type StakeholderNode = z.infer<typeof stakeholderNodeSchema>;

export const stakeholderEdgeSchema = z.object({
  id: z.string(),
  source_id: z.string(),
  target_id: z.string(),
  kind: z.string(),
  note: z.string().nullish(),
  inferred: z.boolean(),
  source: z.string(),
  confidence: z.number().nullish(),
  evidence: z.record(z.string(), z.unknown()),
});
export type StakeholderEdge = z.infer<typeof stakeholderEdgeSchema>;

// The newest AI paragraph about the roster, kept on the map (0092) with the
// version it was written for.
export const stakeholderMapDigestSchema = z.object({
  summary: z.string(),
  gaps: z.array(z.string()),
  version: z.number().int(),
  generated_at: z.string(),
});
export type StakeholderMapDigest = z.infer<typeof stakeholderMapDigestSchema>;

export const stakeholderMapMetaSchema = z.object({
  // Null until the first write creates the row; version 0 is "no map yet".
  id: z.string().uuid().nullish(),
  version: z.number().int(),
  updated_by: z.string().uuid().nullish(),
  last_ai_run_at: z.string().nullish(),
  digest: stakeholderMapDigestSchema.nullish(),
});

export const stakeholderMapSchema = z.object({
  map: stakeholderMapMetaSchema,
  units: z.array(stakeholderUnitSchema),
  nodes: z.array(stakeholderNodeSchema),
  edges: z.array(stakeholderEdgeSchema),
  contacts: z.array(crmContactSchema),
  pending_proposals: z.number().int(),
  can_edit: z.boolean(),
});
export type StakeholderMap = z.infer<typeof stakeholderMapSchema>;

export const stakeholderMutationSchema = z.object({
  map: stakeholderMapMetaSchema,
  units: z.array(stakeholderUnitSchema),
  nodes: z.array(stakeholderNodeSchema),
  edges: z.array(stakeholderEdgeSchema),
  contacts: z.array(crmContactSchema),
  warnings: z.array(z.string()),
  temp_map: z.record(z.string(), z.string()),
  needs_choice: z.array(z.string()),
  imported: z.number().int(),
  skipped: z.number().int(),
});
export type StakeholderMutation = z.infer<typeof stakeholderMutationSchema>;

export const stakeholderRevisionSchema = z.object({
  version: z.number().int(),
  reason: z.string(),
  actor: z.string().uuid().nullish(),
  created_at: z.string(),
  node_count: z.number().int(),
});
export type StakeholderRevision = z.infer<typeof stakeholderRevisionSchema>;

export const riskWarningSchema = z.object({
  code: z.string(),
  severity: z.string(),
  message_vi: z.string(),
  subject_ids: z.array(z.string()),
  suggested_task_title: z.string(),
});
export const riskReportSchema = z.object({
  insufficient: z.boolean(),
  warnings: z.array(riskWarningSchema),
  total_people: z.number().int(),
  engaged_people: z.number().int(),
  covered_roles: z.number().int(),
  watched_roles: z.number().int(),
});
export type RiskReport = z.infer<typeof riskReportSchema>;
export type RiskWarning = z.infer<typeof riskWarningSchema>;

export const keyPeopleCandidateSchema = z.object({
  id: z.string(),
  name: z.string(),
  title: z.string().nullish(),
  tier: z.number().int().nullish(),
  linkedin_url: z.string().nullish(),
  birth_year: z.number().int().nullish(),
  source_urls: z.array(z.string()),
  already_on_map: z.boolean(),
});
export type KeyPeopleCandidate = z.infer<typeof keyPeopleCandidateSchema>;

// One person's web-research run (0089): what the panel polls after the
// "Nghiên cứu người này" click. status "none" = never researched.
export const personResearchSchema = z.object({
  run_id: z.string().uuid().nullish(),
  status: z.string(),
  error: z.string().nullish(),
  filled: z.array(z.string()),
  proposed: z.number().int(),
  finished_at: z.string().nullish(),
});
export type PersonResearch = z.infer<typeof personResearchSchema>;

// The shape of one entry in a node's `field_sources`: written only by the AI
// paths (research, proposal accept), removed by the server the moment a
// person edits that field — so "a stamp exists" means "the AI wrote this and
// nobody has touched it since".
export const fieldSourceSchema = z
  .object({
    origin: z.string().nullish(),
    source_url: z.string().nullish(),
    quote: z.string().nullish(),
    document_id: z.string().nullish(),
  })
  .passthrough();
export type FieldSource = z.infer<typeof fieldSourceSchema>;

// POST .../arrange: the model levels the whole roster — it decides how many
// levels this company's chart has and what each is called; top level first.
// The canvas lays the rows out and writes positions back as one ops batch.
export const stakeholderArrangeLevelSchema = z.object({
  label: z.string(),
  node_ids: z.array(z.string()),
});
export type StakeholderArrangeLevel = z.infer<
  typeof stakeholderArrangeLevelSchema
>;

export const stakeholderArrangeSchema = z.object({
  version: z.number().int(),
  // done | empty | timeout — timeout means fall back to the line layout.
  status: z.string(),
  levels: z.array(stakeholderArrangeLevelSchema),
});
export type StakeholderArrange = z.infer<typeof stakeholderArrangeSchema>;

// POST .../digest: the roster in a paragraph, written fresh and not stored.
export const stakeholderDigestSchema = z.object({
  // done | empty | timeout
  status: z.string(),
  summary: z.string(),
  gaps: z.array(z.string()),
  people: z.number().int(),
  version: z.number().int(),
  generated_at: z.string().nullish(),
});
export type StakeholderDigest = z.infer<typeof stakeholderDigestSchema>;

export const stakeholderProposalSchema = z.object({
  id: z.string().uuid(),
  batch_id: z.string().uuid(),
  kind: z.string(),
  payload: z.record(z.string(), z.unknown()),
  target_contact_id: z.string().uuid().nullish(),
  evidence: z.record(z.string(), z.unknown()),
  confidence: z.number(),
  status: z.string(),
  created_at: z.string(),
});
export type StakeholderProposal = z.infer<typeof stakeholderProposalSchema>;

export const proposalDecisionSchema = z.object({
  id: z.string().uuid(),
  status: z.string(),
});

export const stakeholderExtractResultSchema = z.object({
  run_id: z.string().uuid().nullish(),
  status: z.string(),
  proposals: z.number().int(),
  reason: z.string().nullish(),
});
export type StakeholderExtractResult = z.infer<
  typeof stakeholderExtractResultSchema
>;

/** One op the canvas sends; the server's discriminated union validates it. */
export type StakeholderOp = Record<string, unknown> & { op: string };

// ---- people profile: private notes, memorable dates, the bell (0126/0127) --

// One sale's own note on a person (contact_private_notes). The API only ever
// returns the caller's rows — RLS on app.user_id — so there is no author
// field on the wire: every note you can see is yours.
export const privateNoteSchema = z.object({
  id: z.string().uuid(),
  contact_id: z.string().uuid(),
  body: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type PrivateNote = z.infer<typeof privateNoteSchema>;

// The five kinds of memorable date the domain names (domain/reminders.py).
export const reminderKindSchema = z.enum([
  "birthday",
  "family",
  "memorial",
  "anniversary",
  "custom",
]);
export type ReminderKind = z.infer<typeof reminderKindSchema>;

export const reminderStatusSchema = z.enum(["active", "dismissed", "done"]);
export type ReminderStatus = z.infer<typeof reminderStatusSchema>;

export const reminderVisibilitySchema = z.enum(["shared", "private"]);
export type ReminderVisibility = z.infer<typeof reminderVisibilitySchema>;

export const reminderSchema = z.object({
  id: z.string().uuid(),
  contact_id: z.string().uuid(),
  title: z.string(),
  kind: reminderKindSchema,
  month: z.number().int(),
  day: z.number().int(),
  year_hint: z.number().int().nullish(),
  recurrence: z.enum(["yearly", "once"]),
  lead_days: z.number().int(),
  // Only the owner may edit or dismiss; colleagues see shared dates read-only.
  owner_user_id: z.string().uuid(),
  visibility: reminderVisibilitySchema,
  origin: z.enum(["manual", "ai"]),
  status: reminderStatusSchema,
  // Evidence when the agent extracted it: which field, which sentence.
  source_field: z.string().nullish(),
  source_quote: z.string().nullish(),
  // Computed at read time by the server (VN calendar): never stored.
  next_date: z.string(),
  days_until: z.number().int(),
});
export type ContactReminder = z.infer<typeof reminderSchema>;

/** Trợ lý còn đang đọc hồ sơ người này không — đọc từ outbox, nên đúng cả
 *  khi lượt chạy do người khác kích hoặc panel vừa mở lại. */
export const extractionStatusSchema = z.object({ running: z.boolean() });
export type ExtractionStatus = z.infer<typeof extractionStatusSchema>;

// One line of the in-app bell (notifications, 0127). RLS already narrowed the
// rows to the caller.
export const notificationSchema = z.object({
  id: z.string().uuid(),
  kind: z.string(),
  title: z.string(),
  body: z.string(),
  link: z.string().nullish(),
  created_at: z.string(),
  read_at: z.string().nullish(),
});
export type AppNotification = z.infer<typeof notificationSchema>;

export const bellPageSchema = z.object({
  items: z.array(notificationSchema),
  unread: z.number().int(),
});
export type BellPage = z.infer<typeof bellPageSchema>;

// ---- account sharing team -------------------------------------------------

/** The ladder for the Account record itself, and everything mirroring it. */
export const accountAccessSchema = z.enum([
  "none",
  "read",
  "read_write",
  "all",
]);
export type AccountAccess = z.infer<typeof accountAccessSchema>;

/**
 * The deal axis, configured separately from the account one.
 *
 * Deliberately not a ladder: "manage own" and "read only - all" do not compare,
 * so the server reasons about them as independent facts and only the STORED
 * value is one of these four names.
 */
export const opportunityAccessSchema = z.enum([
  "none",
  "manage_own",
  "read_all",
  "manage_all",
]);
export type OpportunityAccess = z.infer<typeof opportunityAccessSchema>;

export const sharingMemberSchema = z.object({
  principal_type: z.string(),
  principal_id: z.string().uuid(),
  display_name: z.string(),
  email: z.string().nullish(),
  account_access: z.string(),
  opportunity_access: z.string(),
  /** ownership | manual | sharing_rule | role_setting — the "Shared via" column. */
  source: z.string(),
  /**
   * Computed on the server from the caller's own level, so hiding a menu item
   * and refusing the write agree. Hiding a button is not authorization.
   */
  can_edit: z.boolean(),
  /** Null on a derived row (the owner): there is no stored grant to edit. */
  share_id: z.string().uuid().nullish(),
  version: z.number().int().nullish(),
});
export type SharingMember = z.infer<typeof sharingMemberSchema>;

export const sharingTeamSchema = z.object({
  account_id: z.string().uuid(),
  members: z.array(sharingMemberSchema),
  can_share: z.boolean(),
});
export type SharingTeam = z.infer<typeof sharingTeamSchema>;

/** MSG01 and MSG06: what landed, and who did not and why. */
export const shareOutcomeSchema = z.object({
  added: z.array(z.string().uuid()),
  skipped: z.array(
    z.object({ principal_id: z.string().uuid(), reason: z.string() }),
  ),
});
export type ShareOutcome = z.infer<typeof shareOutcomeSchema>;
