import type { SalesSchemas } from "@dw/api-client";

type Order = SalesSchemas["OrderCaseView"];
type Finding = SalesSchemas["OrderFindingView"];
type Quote = SalesSchemas["QuoteCaseView"];

export const AN = "015577d5-b1d4-5c30-9092-7936c9888334";
export const DIEU = "94003cd3-83a4-5c3f-bf38-133699d5d64b";
export const GIANG = "6b1f5c1e-0000-4000-8000-000000000003";

const SHA = "f".repeat(64);

function anchor(field: number) {
  return {
    attachment_id: "M03-A1",
    attachment_sha256: SHA,
    cell_ref: null,
    page: 1,
    boxes: [{ x: 0.1, y: 0.1 * field, w: 0.1, h: 0.02 }],
    quote: null,
  };
}

export function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    key: "quotation_missing:2",
    code: "quotation_missing",
    severity: "error",
    blocking: true,
    line_no: 2,
    expected: "valid on 2026-09-23",
    actual: null,
    rule_version: "sales_order_rules@1.0.0",
    disposition: {
      kind: "open",
      reason: null,
      value: null,
      source: null,
      by: null,
      at: null,
    },
    allowed: ["accepted", "ask_customer"],
    ...overrides,
  };
}

/** A fictional order shaped like the API's answer for M03. */
export function order(overrides: Partial<Order> = {}): Order {
  const line = {
    line_no: 1,
    customer_item_code: "BRN-W-0007",
    description: "HOOK-UP WIRE 1C AWG24",
    quantity: "6100",
    uom: "m",
    unit_price: "1150",
    amount: "7015000",
    requested_date: "2026-11-16",
    anchors: {
      line_no: anchor(1),
      description: anchor(2),
      unit_price: anchor(3),
    },
    flags: [],
    value_states: { line_no: "dw", description: "dw", unit_price: "dw" },
    mapping: {
      status: "exact",
      prv_code: "HW-1001",
      candidates: [],
      confirmed_by: null,
      confirmed_at: null,
      hand_entered: false,
    },
    basis: {
      convert_prv_code: "HW-1001",
      candidates: [],
      item: {
        prv_code: "HW-1001",
        uom: "m",
        moq: "6100",
        pack_multiple: "610",
        standard_lead_time_days: 21,
      },
      quotation: null,
      lme: null,
      lead_time_days: 21,
      lead_time_source: "item_standard",
      checks_run: ["read"],
    },
    suggested_delivery_date: "2026-10-14",
    confirmed_delivery_date: null,
    pc_confirmed_by: null,
    pc_confirmed_at: null,
  } as Order["lines"][number];
  return {
    case_id: "01a10aa0-c939-7000-8539-31fd3e621660",
    case_version: 3,
    status: "in_review",
    customer_code: "BRN",
    message_id: "M03",
    received_at: "2026-09-23T03:05:00Z",
    assigned_to: AN,
    po_no: "BRN-PO-2609-031",
    revision: 0,
    po_date: "2026-09-23",
    currency: "VND",
    attachment_id: "M03-A1",
    attachment_sha256: SHA,
    header_anchors: { po_no: anchor(1) },
    header_flags: [],
    buyer: null,
    buyer_anchor: null,
    total: "94115000",
    total_anchor: anchor(4),
    coverage: {
      lines_printed: 1,
      lines_read: 1,
      regions: ["page 1"],
      unchecked_regions: [],
      checks_run: 9,
      findings: 1,
    },
    findings: [],
    changes: [],
    superseded: [],
    rules_version: "sales_order_rules@1.0.0",
    parser_version: "pdf_po_reader@1.1.0",
    catalog_as_of: "2026-10-02T11:00:00Z",
    release_manifest_ref: null,
    cross_check_required: true,
    export_control_mode: "warn",
    duplicate_of_case: null,
    duplicate_of_so: null,
    base_so_no: null,
    prepared_by: null,
    prepared_at: null,
    bravo_so_no: null,
    bravo_recorded_by: null,
    bravo_recorded_at: null,
    bravo_entry_compared: false,
    cross_checked_by: null,
    cross_checked_at: null,
    returned_reason: null,
    returned_by: null,
    returned_at: null,
    confirmed_by: null,
    confirmed_at: null,
    close_reason: null,
    closed_by: null,
    closed_at: null,
    superseded_by_case: null,
    makers: [],
    lines: [line],
    ...overrides,
  };
}

/** An order An prepared and recorded in Bravo, waiting for its cross-check. */
export function orderInBravo(): Order {
  return order({
    status: "uploaded_to_bravo",
    case_version: 7,
    prepared_by: AN,
    prepared_at: "2026-10-05T03:00:00Z",
    bravo_so_no: "SO-2610-0001",
    bravo_recorded_by: AN,
    bravo_recorded_at: "2026-10-05T03:10:00Z",
    bravo_entry_compared: true,
    makers: [AN],
    // The cross-check approval DW1's run paused on.
    decision: {
      approval_id: "01a10aa0-fe9a-7000-a7de-ed21190d4c0c",
      approval_type: "sales.order.cross_check",
    },
  });
}

/** A quote Diệu priced and submitted, waiting for approval. */
export function pendingQuote(): Quote {
  return {
    case_id: "01a10aa0-fe9a-7000-a7de-ed21190d450f",
    case_version: 9,
    status: "pending_approval",
    customer_code: "KMH",
    customer_from: "sender_domain",
    message_id: "M10",
    received_at: "2026-09-30T09:20:00+07:00",
    sender: "buyer@vn.kumohana.example",
    assigned_to: DIEU,
    rfq_no: "KMH-RFQ-260930-02",
    rfq_date: "2026-09-30",
    quote_due: "2026-10-07",
    overdue: false,
    currency: "USD",
    attachment_id: "M10-A1",
    attachment_sha256: SHA,
    rules_version: "sales_quote_rules@1.1.0",
    parser_version: "excel_rfq_reader@1.0.0",
    catalog_as_of: "2026-10-02T18:00:00+07:00",
    release_manifest_ref: null,
    findings: [],
    lines: [],
    ycbg_no: "YCBG-2609-030",
    ycbg_recorded_by: DIEU,
    ycbg_recorded_at: "2026-10-01T02:00:00Z",
    design_reply: null,
    design_replies: 1,
    pricing: {
      decided_by: DIEU,
      decided_at: "2026-10-05T04:00:00Z",
      lines: [
        {
          line_no: 1,
          unit_price: { hidden: true },
          moq: "3000",
          lead_time_days: 35,
          copper_basis: { kind: "fixed" },
        },
      ],
      lme: null,
      management_guidance: null,
    },
    earlier_pricing: 0,
    returns: [],
    submission: {
      document_sha256: "a".repeat(64),
      issued_on: "2026-10-05",
      priced_by: DIEU,
      quote_no: "Q26-0301",
      recipients: ["buyer@vn.kumohana.example"],
      submitted_at: "2026-10-05T04:10:00Z",
      submitted_by: DIEU,
      valid_to: "2026-12-31",
    },
    approval: null,
    sent: null,
    master_list: null,
    decline: null,
    evidence: null,
    // The approval DW1's run paused on at submit.
    decision: {
      approval_id: "01a10aa0-fe9a-7000-a7de-ed21190d4a99",
      approval_type: "sales.quote",
    },
  };
}
