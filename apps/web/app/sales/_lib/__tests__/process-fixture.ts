import type { SalesSchemas } from "@dw/api-client";

/**
 * `GET /sales/rules/process` as the server answered it on 2026-10-22 for a
 * caller holding `sales.price.read` (`process_settings.py`, the domain's
 * move tables), with the 2026-10-23 fields (each edge's action, actor and
 * guards; each step's model steps, uses and actors) from the server's view
 * of the demo tenant with every model step measured, over a sample role
 * catalog. The tests build their variants from it.
 */
export const PROCESS: SalesSchemas["ProcessSettingsView"] = {
  lanes: [
    {
      kind: "order",
      nodes: [
        {
          status: "received",
          steps: ["O1"],
          holder: "dw",
          ba_steps: [
            { code: "0-SP", label: "Sales tải PO từ cổng của khách lên DW1" },
            { code: "1", label: "Gom PO, phân loại, giao đúng PIC" },
          ],
        },
        {
          status: "checked",
          steps: ["O2"],
          holder: "dw",
          ba_steps: [
            { code: "2", label: "Đọc PO, trích xuất từng dòng" },
            { code: "2.1A", label: "Kiểm giá theo LME" },
            { code: "2.2A", label: "Đổi mã khách sang mã PRV" },
            { code: "3.1", label: "So PO với báo giá" },
          ],
        },
        {
          status: "in_review",
          steps: ["O6"],
          holder: "sales",
          ba_steps: [
            { code: "3", label: "PIC tự kiểm, quyết định từng sai lệch" },
          ],
        },
        {
          status: "correction_requested",
          steps: ["O8"],
          holder: "customer",
          ba_steps: [{ code: "4", label: "Đề nghị khách sửa PO, nhắc khách" }],
        },
        {
          status: "prepared",
          steps: ["O7"],
          holder: "sales",
          ba_steps: [
            { code: "5", label: "Xác nhận PO hợp lệ, lịch giao theo PC" },
          ],
        },
        {
          status: "uploaded_to_bravo",
          steps: ["O3", "O7"],
          holder: "sales",
          ba_steps: [{ code: "5-BR", label: "Nhập đơn vào Bravo, ghi số SO" }],
        },
        {
          status: "cross_checked",
          steps: ["O9"],
          holder: "sales",
          ba_steps: [{ code: "5-KC", label: "Kiểm chéo đơn hàng" }],
        },
        { status: "confirmed", steps: ["O10"], holder: null, ba_steps: [] },
        {
          status: "change_review",
          steps: [],
          holder: "sales",
          ba_steps: [
            { code: "6.2B", label: "Làm lại PO, kiểm lại bước 2 đến 3" },
          ],
        },
        {
          status: "closed",
          steps: [],
          holder: null,
          ba_steps: [{ code: "1-X", label: "Đóng hồ sơ PO không hợp lệ" }],
        },
      ],
      edges: [
        {
          from: "received",
          to: "checked",
          action: "check",
          actor: "dw",
          guards: [],
        },
        {
          from: "received",
          to: "closed",
          action: "close",
          actor: "sales",
          guards: [],
        },
        {
          from: "checked",
          to: "in_review",
          action: "start_review",
          actor: "sales",
          guards: [],
        },
        {
          from: "checked",
          to: "closed",
          action: "close",
          actor: "sales",
          guards: [],
        },
        {
          from: "in_review",
          to: "checked",
          action: "revise",
          actor: "customer",
          guards: [],
        },
        {
          from: "in_review",
          to: "correction_requested",
          action: "request_correction",
          actor: "sales",
          guards: ["ask_customer"],
        },
        {
          from: "in_review",
          to: "prepared",
          action: "prepare",
          actor: "sales",
          guards: ["blocking_findings"],
        },
        {
          from: "in_review",
          to: "closed",
          action: "close",
          actor: "sales",
          guards: [],
        },
        {
          from: "correction_requested",
          to: "checked",
          action: "revise",
          actor: "customer",
          guards: [],
        },
        {
          from: "correction_requested",
          to: "in_review",
          action: "resume_review",
          actor: "sales",
          guards: [],
        },
        {
          from: "correction_requested",
          to: "closed",
          action: "close",
          actor: "sales",
          guards: [],
        },
        {
          from: "prepared",
          to: "checked",
          action: "revise",
          actor: "customer",
          guards: [],
        },
        {
          from: "prepared",
          to: "in_review",
          action: "edit",
          actor: "sales",
          guards: [],
        },
        {
          from: "prepared",
          to: "uploaded_to_bravo",
          action: "record_bravo_entry",
          actor: "sales",
          guards: ["entry_compared"],
        },
        {
          from: "prepared",
          to: "closed",
          action: "close",
          actor: "sales",
          guards: [],
        },
        {
          from: "uploaded_to_bravo",
          to: "in_review",
          action: "return",
          actor: "sales",
          guards: ["approval", "maker_checker"],
        },
        {
          from: "uploaded_to_bravo",
          to: "cross_checked",
          action: "cross_check",
          actor: "sales",
          guards: ["approval", "maker_checker"],
        },
        {
          from: "uploaded_to_bravo",
          to: "confirmed",
          action: "confirm",
          actor: "sales",
          guards: [
            "cross_check_not_required",
            "export_control_hold",
            "pc_confirmed_date",
          ],
        },
        {
          from: "uploaded_to_bravo",
          to: "change_review",
          action: "revise",
          actor: "customer",
          guards: [],
        },
        {
          from: "cross_checked",
          to: "confirmed",
          action: "confirm",
          actor: "sales",
          guards: ["export_control_hold", "pc_confirmed_date"],
        },
        {
          from: "cross_checked",
          to: "change_review",
          action: "revise",
          actor: "customer",
          guards: [],
        },
        {
          from: "confirmed",
          to: "change_review",
          action: "revise",
          actor: "customer",
          guards: [],
        },
        {
          from: "change_review",
          to: "uploaded_to_bravo",
          action: "apply_change",
          actor: "sales",
          guards: ["blocking_findings", "entry_compared"],
        },
      ],
      stateless_steps: ["O4", "O5", "O11"],
      subflows: [
        {
          key: "thread",
          steps: [
            {
              step: "before_po",
              statuses: [],
              next: [],
              ba_steps: [
                {
                  code: "0-KH",
                  label: "Khách trao đổi trong luồng thư, rồi gửi PO",
                },
              ],
            },
          ],
        },
        {
          key: "pc_request",
          steps: [
            {
              step: "waiting_pc",
              statuses: ["in_review", "prepared"],
              next: [],
              ba_steps: [
                { code: "2.4B", label: "Hỏi PC lịch giao và cách tách dòng" },
              ],
            },
          ],
        },
        {
          key: "change_request",
          steps: [
            {
              step: "confirm_lines",
              statuses: [
                "in_review",
                "prepared",
                "confirmation_sent",
                "confirmed",
              ],
              next: [],
              ba_steps: [
                { code: "6.1A", label: "Khách xin điều chỉnh qua thư" },
                {
                  code: "6-DW1",
                  label: "Nhận ra yêu cầu, gắn với PO gốc, so thay đổi",
                },
              ],
            },
          ],
        },
        {
          key: "update",
          steps: [
            {
              step: "ask_pc",
              statuses: ["confirmation_sent", "confirmed"],
              next: ["waiting_pc"],
              ba_steps: [{ code: "6-DW2", label: "Soạn yêu cầu gửi PC" }],
            },
            {
              step: "waiting_pc",
              statuses: ["confirmation_sent", "confirmed"],
              next: ["answer_customer"],
              ba_steps: [{ code: "6-PC", label: "PC xem và trả lời" }],
            },
            {
              step: "answer_customer",
              statuses: ["confirmation_sent", "confirmed"],
              next: ["waiting_customer"],
              ba_steps: [
                {
                  code: "6-DW3",
                  label: "PC đề xuất khác: soạn thư phương án cho khách",
                },
                {
                  code: "6-DW4",
                  label: "PC làm được: soạn thư xác nhận điều chỉnh",
                },
              ],
            },
            {
              step: "waiting_customer",
              statuses: ["confirmation_sent", "confirmed"],
              next: ["ask_pc", "bravo_update"],
              ba_steps: [],
            },
            {
              step: "bravo_update",
              statuses: ["uploaded_to_bravo", "cross_checked", "change_review"],
              next: [],
              ba_steps: [
                { code: "6.2-SP", label: "Duyệt cập nhật đơn trên Bravo" },
              ],
            },
          ],
        },
      ],
    },
    {
      kind: "quote",
      nodes: [
        {
          status: "received",
          steps: ["Q1"],
          holder: "sales",
          ba_steps: [
            { code: "1-DW", label: "Gom RFQ, đọc, phân loại, giao PIC" },
          ],
        },
        {
          status: "ycbg_drafted",
          steps: ["Q2"],
          holder: "sales",
          ba_steps: [],
        },
        {
          status: "ycbg_recorded",
          steps: ["Q2"],
          holder: "sales",
          ba_steps: [{ code: "1.1.1", label: "Nhập RFQ lên Bravo" }],
        },
        {
          status: "sent_to_design",
          steps: ["Q3"],
          holder: "design",
          ba_steps: [
            { code: "1.1.2", label: "Gửi RFQ cho Design, nhắc khi chậm" },
          ],
        },
        {
          status: "design_replied",
          steps: ["Q4"],
          holder: "sales",
          ba_steps: [{ code: "1.1.4", label: "Ghi BP code và Base price" }],
        },
        {
          status: "spec_discussion",
          steps: ["Q6"],
          holder: "customer",
          ba_steps: [{ code: "1.1.3", label: "Hỏi lại khách về spec" }],
        },
        {
          status: "priced",
          steps: ["Q7"],
          holder: "sales",
          ba_steps: [
            { code: "2.1.1", label: "Tính giá theo LME và policy, chốt giá" },
          ],
        },
        {
          status: "pending_approval",
          steps: ["Q9"],
          holder: "approver",
          ba_steps: [{ code: "2.1.4", label: "In báo giá, trình ký" }],
        },
        { status: "returned", steps: ["Q9"], holder: "sales", ba_steps: [] },
        {
          status: "approved",
          steps: ["Q9"],
          holder: "sales",
          ba_steps: [{ code: "2.1.5", label: "Bản đã ký" }],
        },
        {
          status: "sent",
          steps: ["Q10"],
          holder: "sales",
          ba_steps: [{ code: "2.1.6", label: "Gửi thư báo giá" }],
        },
        {
          status: "master_list_recorded",
          steps: ["Q11"],
          holder: null,
          ba_steps: [{ code: "2.1.3", label: "Ghi báo giá vào master list" }],
        },
        {
          status: "declined",
          steps: ["Q5"],
          holder: null,
          ba_steps: [{ code: "1.1.5", label: "Sales quyết định đóng" }],
        },
      ],
      edges: [
        {
          from: "received",
          to: "ycbg_drafted",
          action: "draft_ycbg",
          actor: "sales",
          guards: ["request_findings"],
        },
        {
          from: "received",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "ycbg_drafted",
          to: "ycbg_recorded",
          action: "record_ycbg",
          actor: "sales",
          guards: [],
        },
        {
          from: "ycbg_drafted",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "ycbg_recorded",
          to: "sent_to_design",
          action: "send_to_design",
          actor: "sales",
          guards: [],
        },
        {
          from: "ycbg_recorded",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "sent_to_design",
          to: "design_replied",
          action: "record_design_reply",
          actor: "design",
          guards: [],
        },
        {
          from: "sent_to_design",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "design_replied",
          to: "spec_discussion",
          action: "discuss_spec",
          actor: "sales",
          guards: [],
        },
        {
          from: "design_replied",
          to: "priced",
          action: "price",
          actor: "sales",
          guards: [],
        },
        {
          from: "design_replied",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "spec_discussion",
          to: "sent_to_design",
          action: "send_to_design",
          actor: "sales",
          guards: [],
        },
        {
          from: "spec_discussion",
          to: "design_replied",
          action: "settle_spec",
          actor: "sales",
          guards: [],
        },
        {
          from: "spec_discussion",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "priced",
          to: "pending_approval",
          action: "submit",
          actor: "sales",
          guards: [],
        },
        {
          from: "priced",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "pending_approval",
          to: "priced",
          action: "price",
          actor: "sales",
          guards: [],
        },
        {
          from: "pending_approval",
          to: "returned",
          action: "return",
          actor: "approver",
          guards: ["approval", "maker_checker"],
        },
        {
          from: "pending_approval",
          to: "approved",
          action: "approve",
          actor: "approver",
          guards: ["approval", "maker_checker", "blocking_findings"],
        },
        {
          from: "pending_approval",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "returned",
          to: "priced",
          action: "price",
          actor: "sales",
          guards: [],
        },
        {
          from: "returned",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "approved",
          to: "priced",
          action: "price",
          actor: "sales",
          guards: [],
        },
        {
          from: "approved",
          to: "sent",
          action: "send",
          actor: "sales",
          guards: [],
        },
        {
          from: "approved",
          to: "declined",
          action: "decline",
          actor: "sales",
          guards: [],
        },
        {
          from: "sent",
          to: "master_list_recorded",
          action: "record_master_list",
          actor: "sales",
          guards: [],
        },
      ],
      stateless_steps: ["Q8", "Q12"],
      subflows: [],
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
          lock: "model_bar",
        },
        {
          key: "sales_order_rules",
          path: "model_assist.unread_retry_hours",
          lock: "model_bar",
        },
        {
          key: "sales_order_rules",
          path: "model_assist.reply_intent",
          lock: "model_bar",
        },
        {
          key: "sales_order_rules",
          path: "model_assist.request_handoff",
          lock: "model_bar",
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
      models: [
        {
          step: "message_intent",
          enabled: true,
          bar: 0.9,
          metric: "all.kind_accuracy",
          model: "qwen3.5-9b-dw",
          prompt: "sales.message_intent@1.0.0",
          latest: {
            value: 0.9,
            passed: true,
            model: "qwen3.5-9b-dw",
            prompt: "sales.message_intent@1.0.0",
            measured_at: "2026-10-05T03:00:00Z",
          },
          effective: true,
          live_share: { handled: 0, automatic: 0, share: null, window_days: 7 },
        },
        {
          step: "reply_intent",
          enabled: true,
          bar: 0.85,
          metric: "bar_set.intent_accuracy",
          model: "qwen3.5-9b-dw",
          prompt: "sales.reply_intent@2.0.0",
          latest: {
            value: 0.85,
            passed: true,
            model: "qwen3.5-9b-dw",
            prompt: "sales.reply_intent@2.0.0",
            measured_at: "2026-10-05T03:00:00Z",
          },
          effective: true,
          live_share: { handled: 0, automatic: 0, share: null, window_days: 7 },
        },
        {
          step: "request_handoff",
          enabled: true,
          bar: 0.85,
          metric: "all.right",
          model: "qwen3.5-9b-dw",
          prompt: "sales.request_handoff@1.0.0",
          latest: {
            value: 0.85,
            passed: true,
            model: "qwen3.5-9b-dw",
            prompt: "sales.request_handoff@1.0.0",
            measured_at: "2026-10-05T03:00:00Z",
          },
          effective: true,
          live_share: { handled: 0, automatic: 0, share: null, window_days: 7 },
        },
      ],
      uses: { lists: ["customers"], layouts: true },
      actors: [
        {
          kind: "role",
          key: "sales_dw1",
          name: "DW1",
          scopes: ["sales.inbox.process"],
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
          lock: "model_bar",
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
      models: [
        {
          step: "description_attributes",
          enabled: true,
          bar: 0.7,
          metric: "vi_en.gold_in_candidates",
          model: "qwen3.5-9b-dw",
          prompt: "sales.description_attributes@1.0.0",
          latest: {
            value: 0.7,
            passed: true,
            model: "qwen3.5-9b-dw",
            prompt: "sales.description_attributes@1.0.0",
            measured_at: "2026-10-05T03:00:00Z",
          },
          effective: true,
          live_share: { handled: 0, automatic: 0, share: null, window_days: 7 },
        },
      ],
      uses: { lists: ["convert_list", "items"], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.order.prepare"],
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
          lock: "model_bar",
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
      models: [
        {
          step: "layout_proposal",
          enabled: true,
          bar: 0.9,
          metric: "all.right",
          model: "qwen3.5-9b-dw",
          prompt: "sales.po_layout_proposal@1.0.0",
          latest: {
            value: 0.9,
            passed: true,
            model: "qwen3.5-9b-dw",
            prompt: "sales.po_layout_proposal@1.0.0",
            measured_at: "2026-10-05T03:00:00Z",
          },
          effective: true,
          live_share: { handled: 0, automatic: 0, share: null, window_days: 7 },
        },
      ],
      uses: { lists: [], layouts: true },
      actors: [
        {
          kind: "role",
          key: "sales_head",
          name: "Trưởng bộ phận Sales",
          scopes: ["sales.layout.approve"],
        },
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.order.prepare"],
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
      models: [],
      uses: { lists: ["items", "quotations"], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.order.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [],
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
      models: [],
      uses: { lists: ["items", "lme", "quotations"], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.order.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.order.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.order.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_head",
          name: "Trưởng bộ phận Sales",
          scopes: ["sales.order.cross_check"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.order.prepare"],
        },
        {
          kind: "permission_set",
          key: "export_control",
          name: "Kiểm soát xuất khẩu",
          scopes: ["sales.compliance.ack"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [],
    },
    {
      step_id: "Q1",
      coverage: "yes",
      settings: [
        {
          key: "sales_order_rules",
          path: "model_assist.rfq_extraction",
          lock: "model_bar",
        },
        {
          key: "sales_kpi",
          path: "manual_baseline_minutes.Q1",
          lock: null,
        },
      ],
      models: [
        {
          step: "rfq_extraction",
          enabled: true,
          bar: 0.85,
          metric: "vi_en.right_field",
          model: "qwen3.5-9b-dw",
          prompt: "sales.rfq_extraction@1.0.0",
          latest: {
            value: 0.85,
            passed: true,
            model: "qwen3.5-9b-dw",
            prompt: "sales.rfq_extraction@1.0.0",
            measured_at: "2026-10-05T03:00:00Z",
          },
          effective: true,
          live_share: { handled: 0, automatic: 0, share: null, window_days: 7 },
        },
      ],
      uses: { lists: ["convert_list", "customers", "items"], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_dw1",
          name: "DW1",
          scopes: ["sales.inbox.process"],
        },
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: ["convert_list", "customers", "items"], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: ["lme", "quotations"], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: ["customers"], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_head",
          name: "Trưởng bộ phận Sales",
          scopes: ["sales.quote.approve"],
        },
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: [], layouts: false },
      actors: [
        {
          kind: "role",
          key: "sales_pic",
          name: "Sales PIC",
          scopes: ["sales.quote.prepare"],
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
      models: [],
      uses: { lists: ["quotations"], layouts: false },
      actors: [],
    },
  ],
  head_settings: [
    {
      key: "sales_order_rules",
      path: "price.relative_tolerance",
      sentence:
        "Đơn giá trên PO được lệch bao nhiêu so với báo giá mà DW1 vẫn coi là khớp (0 là phải bằng đúng).",
    },
    {
      key: "sales_order_rules",
      path: "cross_check_required",
      sentence:
        "Bật thì mỗi đơn đã nhập Bravo cần người thứ hai kiểm chéo trước khi gửi xác nhận cho khách.",
    },
    {
      key: "sales_followups",
      path: "waiting_pc.remind.after_hours",
      sentence:
        "PC chưa trả ngày giao sau bấy nhiêu giờ thì DW1 nhắc Sales phụ trách.",
    },
    {
      key: "sales_followups",
      path: "waiting_customer.remind.after_hours",
      sentence:
        "Khách chưa trả lời sau bấy nhiêu giờ thì DW1 nhắc Sales phụ trách.",
    },
    {
      key: "sales_followups",
      path: "order_unconfirmed.remind.after_hours",
      sentence:
        "PO chưa được xác nhận sau bấy nhiêu giờ thì DW1 nhắc Sales phụ trách.",
    },
    {
      key: "sales_followups",
      path: "order_unconfirmed.escalate.after_hours",
      sentence:
        "PO chưa được xác nhận sau bấy nhiêu giờ thì DW1 báo Trưởng bộ phận.",
    },
    {
      key: "sales_followups",
      path: "quote_waiting_design.remind.after_hours",
      sentence:
        "Design chưa trả lời yêu cầu báo giá sau bấy nhiêu giờ thì DW1 nhắc Sales phụ trách.",
    },
    {
      key: "sales_followups",
      path: "quote_deadline.warn.hours_before_due",
      sentence:
        "Còn bấy nhiêu giờ đến hạn báo giá thì DW1 báo Sales phụ trách.",
    },
    {
      key: "sales_quote_rules",
      path: "validity_days",
      sentence:
        "Báo giá đã duyệt có hiệu lực bấy nhiêu ngày, tính cả ngày phát hành.",
    },
    {
      key: "sales_followups",
      path: "morning_brief.at",
      sentence: "Giờ DW1 gửi bản tin buổi sáng mỗi ngày làm việc.",
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
