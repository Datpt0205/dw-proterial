import type { SalesSchemas } from "@dw/api-client";

/**
 * `GET /sales/rules/process` as the server answered it on 2026-10-22 for a
 * caller holding `sales.price.read` (`process_settings.py`, the domain's
 * move tables). The tests build their variants from it.
 */
export const PROCESS: SalesSchemas["ProcessSettingsView"] = {
  lanes: [
    {
      kind: "order",
      nodes: [
        { status: "received", steps: ["O1"], holder: "dw" },
        { status: "checked", steps: ["O2"], holder: "dw" },
        { status: "in_review", steps: ["O6"], holder: "sales" },
        { status: "correction_requested", steps: ["O8"], holder: "customer" },
        { status: "prepared", steps: ["O7"], holder: "sales" },
        { status: "uploaded_to_bravo", steps: ["O3", "O7"], holder: "sales" },
        { status: "cross_checked", steps: ["O9"], holder: "sales" },
        { status: "confirmed", steps: ["O10"], holder: null },
        { status: "change_review", steps: [], holder: "sales" },
        { status: "closed", steps: [], holder: null },
      ],
      edges: [
        { from: "received", to: "checked" },
        { from: "received", to: "closed" },
        { from: "checked", to: "in_review" },
        { from: "checked", to: "closed" },
        { from: "in_review", to: "checked" },
        { from: "in_review", to: "correction_requested" },
        { from: "in_review", to: "prepared" },
        { from: "in_review", to: "closed" },
        { from: "correction_requested", to: "checked" },
        { from: "correction_requested", to: "in_review" },
        { from: "correction_requested", to: "closed" },
        { from: "prepared", to: "checked" },
        { from: "prepared", to: "in_review" },
        { from: "prepared", to: "uploaded_to_bravo" },
        { from: "prepared", to: "closed" },
        { from: "uploaded_to_bravo", to: "in_review" },
        { from: "uploaded_to_bravo", to: "cross_checked" },
        { from: "uploaded_to_bravo", to: "confirmed" },
        { from: "uploaded_to_bravo", to: "change_review" },
        { from: "cross_checked", to: "confirmed" },
        { from: "cross_checked", to: "change_review" },
        { from: "confirmed", to: "change_review" },
        { from: "change_review", to: "uploaded_to_bravo" },
      ],
      stateless_steps: ["O4", "O5", "O11"],
    },
    {
      kind: "quote",
      nodes: [
        { status: "received", steps: ["Q1"], holder: "sales" },
        { status: "ycbg_drafted", steps: ["Q2"], holder: "sales" },
        { status: "ycbg_recorded", steps: ["Q2"], holder: "sales" },
        { status: "sent_to_design", steps: ["Q3"], holder: "design" },
        { status: "design_replied", steps: ["Q4"], holder: "sales" },
        { status: "spec_discussion", steps: ["Q6"], holder: "customer" },
        { status: "priced", steps: ["Q7"], holder: "sales" },
        { status: "pending_approval", steps: ["Q9"], holder: "approver" },
        { status: "returned", steps: ["Q9"], holder: "sales" },
        { status: "approved", steps: ["Q9"], holder: "sales" },
        { status: "sent", steps: ["Q10"], holder: "sales" },
        { status: "master_list_recorded", steps: ["Q11"], holder: null },
        { status: "declined", steps: ["Q5"], holder: null },
      ],
      edges: [
        { from: "received", to: "ycbg_drafted" },
        { from: "received", to: "declined" },
        { from: "ycbg_drafted", to: "ycbg_recorded" },
        { from: "ycbg_drafted", to: "declined" },
        { from: "ycbg_recorded", to: "sent_to_design" },
        { from: "ycbg_recorded", to: "declined" },
        { from: "sent_to_design", to: "design_replied" },
        { from: "sent_to_design", to: "declined" },
        { from: "design_replied", to: "spec_discussion" },
        { from: "design_replied", to: "priced" },
        { from: "design_replied", to: "declined" },
        { from: "spec_discussion", to: "sent_to_design" },
        { from: "spec_discussion", to: "design_replied" },
        { from: "spec_discussion", to: "declined" },
        { from: "priced", to: "pending_approval" },
        { from: "priced", to: "declined" },
        { from: "pending_approval", to: "priced" },
        { from: "pending_approval", to: "returned" },
        { from: "pending_approval", to: "approved" },
        { from: "pending_approval", to: "declined" },
        { from: "returned", to: "priced" },
        { from: "returned", to: "declined" },
        { from: "approved", to: "priced" },
        { from: "approved", to: "sent" },
        { from: "approved", to: "declined" },
        { from: "sent", to: "master_list_recorded" },
      ],
      stateless_steps: ["Q8", "Q12"],
    },
  ],
  steps: [
    {
      step_id: "O1",
      coverage: "yes",
      settings: [
        { key: "sales_order_rules", path: "intake", lock: "bound_at_build" },
        {
          key: "sales_order_rules",
          path: "model_assist.message_intent",
          lock: "model_bar_unchecked",
        },
        {
          key: "sales_order_rules",
          path: "model_assist.unread_retry_hours",
          lock: "model_bar_unchecked",
        },
        {
          key: "sales_order_rules",
          path: "model_assist.reply_intent",
          lock: "model_bar_unchecked",
        },
        {
          key: "sales_order_rules",
          path: "model_assist.request_handoff",
          lock: "model_bar_unchecked",
        },
        {
          key: "sales_order_rules",
          path: "findings.duplicate_po",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.revised_po",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.revision_without_base",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.customer_unknown",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.customer_temporary",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.sender_unverified",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.legacy_encoding",
          lock: null,
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O1",
          lock: null,
        },
      ],
    },
    {
      step_id: "O2",
      coverage: "yes",
      settings: [
        {
          key: "sales_order_rules",
          path: "model_assist.description_attributes",
          lock: "model_bar_unchecked",
        },
        {
          key: "sales_order_rules",
          path: "findings.code_unmapped",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.code_ambiguous",
          lock: null,
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O2",
          lock: null,
        },
      ],
    },
    {
      step_id: "O3",
      coverage: "yes",
      settings: [
        {
          key: "sales_order_rules",
          path: "layout_onboarding.uncertain_first_pos",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "model_assist.layout_proposal",
          lock: "model_bar_unchecked",
        },
        {
          key: "sales_order_rules",
          path: "findings.value_uncertain",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.line_total_mismatch",
          lock: null,
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O3",
          lock: null,
        },
      ],
    },
    {
      step_id: "O4",
      coverage: "suggestion",
      settings: [
        { key: "sales_order_rules", path: "short_lead_time", lock: null },
        {
          key: "sales_order_rules",
          path: "findings.requested_date_short_lt",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.requested_date_missing",
          lock: null,
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O4",
          lock: null,
        },
      ],
    },
    {
      step_id: "O5",
      coverage: "out",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O5",
          lock: null,
        },
      ],
    },
    {
      step_id: "O6",
      coverage: "yes",
      settings: [
        {
          key: "sales_order_rules",
          path: "price.relative_tolerance",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "lme_band.months_before_po_date",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.quotation_missing",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.price_mismatch",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.currency_mismatch",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.uom_mismatch",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.lme_band_mismatch",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.moq_violation",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.pack_multiple",
          lock: null,
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O6",
          lock: null,
        },
      ],
    },
    {
      step_id: "O7",
      coverage: "yes",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O7",
          lock: null,
        },
      ],
    },
    {
      step_id: "O8",
      coverage: "yes",
      settings: [
        { key: "sales_followups", path: "waiting_customer", lock: null },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O8",
          lock: null,
        },
      ],
    },
    {
      step_id: "O9",
      coverage: "yes",
      settings: [
        {
          key: "sales_order_rules",
          path: "cross_check_required",
          lock: null,
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O9",
          lock: null,
        },
      ],
    },
    {
      step_id: "O10",
      coverage: "yes",
      settings: [
        {
          key: "sales_order_rules",
          path: "export_control_mode",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "export_control.denial_list_max_age_days",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "fiscal_year_start_month",
          lock: null,
        },
        {
          key: "sales_order_rules",
          path: "findings.missing_noc_esf",
          lock: null,
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O10",
          lock: null,
        },
      ],
    },
    {
      step_id: "O11",
      coverage: "out",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.O11",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q1",
      coverage: "yes",
      settings: [
        {
          key: "sales_order_rules",
          path: "model_assist.rfq_extraction",
          lock: "model_bar_unchecked",
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q1",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q2",
      coverage: "yes",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q2",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q3",
      coverage: "yes",
      settings: [
        { key: "sales_quote_rules", path: "design_mailboxes", lock: "trust" },
        {
          key: "sales_followups",
          path: "quote_waiting_design",
          lock: null,
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q3",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q4",
      coverage: "mock",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q4",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q5",
      coverage: "yes",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q5",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q6",
      coverage: "yes",
      settings: [
        { key: "sales_followups", path: "waiting_customer", lock: null },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q6",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q7",
      coverage: "yes",
      settings: [
        {
          key: "sales_quote_rules",
          path: "reference_price.band_below_percent",
          lock: null,
        },
        {
          key: "sales_quote_rules",
          path: "reference_price.band_above_percent",
          lock: null,
        },
        { key: "sales_quote_rules", path: "copper_basis", lock: null },
        { key: "sales_pricing", path: "copper_adders", lock: null },
        { key: "sales_pricing", path: "floor_margin", lock: null },
        { key: "sales_pricing", path: "freight", lock: null },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q7",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q8",
      coverage: "yes",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q8",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q9",
      coverage: "yes",
      settings: [
        { key: "sales_quote_rules", path: "validity_days", lock: null },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q9",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q10",
      coverage: "yes",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q10",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q11",
      coverage: "mock",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q11",
          lock: null,
        },
      ],
    },
    {
      step_id: "Q12",
      coverage: "mock",
      settings: [
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q12",
          lock: null,
        },
      ],
    },
  ],
  lane_settings: {
    order: [
      { key: "sales_followups", path: "order_unconfirmed", lock: null },
      {
        key: "sales_kpi",
        path: "order_confirmation_target_hours",
        lock: null,
      },
    ],
    quote: [
      { key: "sales_followups", path: "quote_deadline", lock: null },
      { key: "sales_kpi", path: "quotation_target_days", lock: null },
    ],
  },
  process_settings: [
    {
      key: "sales_followups",
      path: "working_hours.time_zone",
      lock: "two_owners",
    },
    { key: "sales_followups", path: "working_hours.days", lock: null },
    { key: "sales_followups", path: "working_hours.start", lock: null },
    { key: "sales_followups", path: "working_hours.end", lock: null },
    { key: "sales_followups", path: "morning_brief", lock: null },
  ],
};
