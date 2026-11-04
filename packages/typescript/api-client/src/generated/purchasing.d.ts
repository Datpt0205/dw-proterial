/**
 * Auto-generated types for context "purchasing" — do not edit.
 * Regenerate with `make generate-contracts`.
 */
export interface paths {
    "/api/v1/purchasing/assistant/ask": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Assistant Ask */
        post: operations["assistant_ask_api_v1_purchasing_assistant_ask_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/assistant/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Assistant Sessions */
        get: operations["assistant_sessions_api_v1_purchasing_assistant_sessions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/assistant/sessions/{session_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Assistant Session */
        get: operations["assistant_session_api_v1_purchasing_assistant_sessions__session_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/automation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Automation */
        get: operations["automation_api_v1_purchasing_automation_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/mail": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Mailbox */
        get: operations["mailbox_api_v1_purchasing_mail_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/mail/{message_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Read Mail */
        post: operations["read_mail_api_v1_purchasing_mail__message_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/master-data": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Master Data */
        get: operations["master_data_api_v1_purchasing_master_data_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/master-data/imports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Master Upload */
        post: operations["master_upload_api_v1_purchasing_master_data_imports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/master-data/imports/{import_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Master Import */
        get: operations["master_import_api_v1_purchasing_master_data_imports__import_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/master-data/imports/{import_id}/submit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Master Submit */
        post: operations["master_submit_api_v1_purchasing_master_data_imports__import_id__submit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/master-data/template.xlsx": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Master Template */
        get: operations["master_template_api_v1_purchasing_master_data_template_xlsx_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/orders/late": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Late Lines */
        get: operations["late_lines_api_v1_purchasing_orders_late_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Requests */
        get: operations["list_requests_api_v1_purchasing_requests_get"];
        put?: never;
        /** Submit Request */
        post: operations["submit_request_api_v1_purchasing_requests_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/mine": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Send My Request */
        post: operations["send_my_request_api_v1_purchasing_requests_mine_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/mine/draft": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Draft My Request */
        post: operations["draft_my_request_api_v1_purchasing_requests_mine_draft_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Request */
        get: operations["get_request_api_v1_purchasing_requests__case_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Check Request */
        get: operations["check_request_api_v1_purchasing_requests__case_id__check_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/comparison": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Comparison */
        get: operations["comparison_api_v1_purchasing_requests__case_id__comparison_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/offers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record Offer */
        post: operations["record_offer_api_v1_purchasing_requests__case_id__offers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/offers/from-mail/{message_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Read Offer Mail */
        post: operations["read_offer_mail_api_v1_purchasing_requests__case_id__offers_from_mail__message_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/po": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Draft Orders */
        post: operations["draft_orders_api_v1_purchasing_requests__case_id__po_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/po/bravo.xlsx": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Bravo File */
        get: operations["bravo_file_api_v1_purchasing_requests__case_id__po_bravo_xlsx_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/po/confirmations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Confirmation Mails */
        get: operations["confirmation_mails_api_v1_purchasing_requests__case_id__po_confirmations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/po/confirmations/from-mail/{message_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Read Confirmation */
        post: operations["read_confirmation_api_v1_purchasing_requests__case_id__po_confirmations_from_mail__message_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/po/{po_ref}/bravo-number": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record Bravo No */
        post: operations["record_bravo_no_api_v1_purchasing_requests__case_id__po__po_ref__bravo_number_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/po/{po_ref}/confirmation/accept": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Accept Confirmation */
        post: operations["accept_confirmation_api_v1_purchasing_requests__case_id__po__po_ref__confirmation_accept_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/po/{po_ref}/receipts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record Receipt */
        post: operations["record_receipt_api_v1_purchasing_requests__case_id__po__po_ref__receipts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Review Request */
        post: operations["review_request_api_v1_purchasing_requests__case_id__review_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/rfq": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Draft Rfq */
        post: operations["draft_rfq_api_v1_purchasing_requests__case_id__rfq_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/rfq/mails": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rfq Mails */
        get: operations["rfq_mails_api_v1_purchasing_requests__case_id__rfq_mails_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/rfq/replies": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rfq Replies */
        get: operations["rfq_replies_api_v1_purchasing_requests__case_id__rfq_replies_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/rfq/{supplier_code}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Write Rfq */
        post: operations["write_rfq_api_v1_purchasing_requests__case_id__rfq__supplier_code__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/rfq/{supplier_code}/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Send Rfq */
        post: operations["send_rfq_api_v1_purchasing_requests__case_id__rfq__supplier_code__send_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/selection": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Select Suppliers */
        post: operations["select_suppliers_api_v1_purchasing_requests__case_id__selection_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/requests/{case_id}/submit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit Request For Approval */
        post: operations["submit_request_for_approval_api_v1_purchasing_requests__case_id__submit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/rules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rules In Force */
        get: operations["rules_in_force_api_v1_purchasing_rules_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/rules/{key}/schema": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rule Schema */
        get: operations["rule_schema_api_v1_purchasing_rules__key__schema_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/rules/{key}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Propose Rules */
        post: operations["propose_rules_api_v1_purchasing_rules__key__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/rules/{key}/words": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Rule In Words */
        post: operations["rule_in_words_api_v1_purchasing_rules__key__words_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/purchasing/suppliers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Suppliers */
        get: operations["suppliers_api_v1_purchasing_suppliers_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * ApprovalAsked
         * @description Who the case was sent to, stamped when it was sent: the approval, the
         *     scope its decider must hold and who that is, the version of the case the
         *     approver is shown, and who sent it. A later reader takes this stamp, never
         *     the rules in force today.
         */
        ApprovalAsked: {
            /**
             * Approval Id
             * Format: uuid
             */
            approval_id: string;
            /** Case Version */
            case_version: number;
            /** Limit */
            limit: string | null;
            /** Limit Currency */
            limit_currency: string;
            /** Required Scope */
            required_scope: string;
            /**
             * Submitted At
             * Format: date-time
             */
            submitted_at: string;
            /**
             * Submitted By
             * Format: uuid
             */
            submitted_by: string;
            /** Tier Label */
            tier_label: string;
        };
        /** AssistantAnswerView */
        AssistantAnswerView: {
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            turn: components["schemas"]["AssistantTurnView"];
        };
        /**
         * AssistantAskBody
         * @description A question, and the session it continues (None opens one).
         */
        AssistantAskBody: {
            /** Question */
            question: string;
            /** Session Id */
            session_id?: string | null;
        };
        /** AssistantCaseRef */
        AssistantCaseRef: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Label */
            label: string;
        };
        /**
         * AssistantQuestionKind
         * @description What DW2 answers, and everything else.
         * @enum {string}
         */
        AssistantQuestionKind: "request_status" | "my_work" | "late_orders" | "out_of_scope";
        /** AssistantSessionDetailView */
        AssistantSessionDetailView: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Last Turn At
             * Format: date-time
             */
            last_turn_at: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            /** Title */
            title: string;
            /** Turns */
            turns: components["schemas"]["AssistantTurnView"][];
        };
        /** AssistantSessionView */
        AssistantSessionView: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Last Turn At
             * Format: date-time
             */
            last_turn_at: string;
            /**
             * Session Id
             * Format: uuid
             */
            session_id: string;
            /** Title */
            title: string;
        };
        /** AssistantStepView */
        AssistantStepView: {
            /** Key */
            key: string;
            /** Title */
            title: string;
        };
        /** AssistantTurnView */
        AssistantTurnView: {
            /** Answer */
            answer: string;
            /**
             * Answered By
             * @enum {string}
             */
            answered_by: "model" | "code";
            /**
             * Asked At
             * Format: date-time
             */
            asked_at: string;
            /** Cites */
            cites: components["schemas"]["AssistantCaseRef"][];
            kind: components["schemas"]["AssistantQuestionKind"];
            /** Question */
            question: string;
            /** Seq */
            seq: number;
            /** Steps */
            steps: components["schemas"]["AssistantStepView"][];
        };
        /**
         * AutomationLevel
         * @enum {string}
         */
        AutomationLevel: "ai_auto" | "ai_review" | "person";
        /**
         * AutomationStep
         * @description The steps of DW2 that have a switch: each one code reads where the
         *     step happens. The other steps of the twelve (CONTEXT.md, "Automation")
         *     get theirs the day they are built, never before (failure-modes #1).
         * @enum {string}
         */
        AutomationStep: "mail_sorting" | "pr_drafting" | "submission" | "rfq" | "po_drafting";
        /** BravoColumn */
        BravoColumn: {
            /**
             * Field
             * @enum {string}
             */
            field: "po_ref" | "pr_no" | "order_date" | "supplier_code" | "supplier_name" | "item_code" | "description" | "quantity" | "unit" | "unit_price" | "currency" | "amount" | "need_by" | "budget_code" | "department";
            /** Header */
            header: string;
        };
        /** BravoNoBody */
        BravoNoBody: {
            /** Bravo No */
            bravo_no: string;
            /** Case Version */
            case_version: number;
        };
        /**
         * BravoPoLayout
         * @description The import file's shape, as the tenant's Bravo expects it.
         */
        BravoPoLayout: {
            /** Columns */
            columns: components["schemas"]["BravoColumn"][];
            /**
             * Date Format
             * @enum {string}
             */
            date_format: "dd/mm/yyyy" | "yyyy-mm-dd" | "mm/dd/yyyy";
            /**
             * Mock
             * @default false
             */
            mock: boolean;
            /** Sheet */
            sheet: string;
        };
        /**
         * CaseChange
         * @description What a mutation answers: ids only, so an idempotent replay keeps no
         *     request content.
         */
        CaseChange: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            status: components["schemas"]["CaseStatus"];
        };
        /** CasePage */
        CasePage: {
            /** Items */
            items: components["schemas"]["PurchaseCase"][];
            /** Next Before At */
            next_before_at: string | null;
            /** Next Before Id */
            next_before_id: string | null;
        };
        /**
         * CaseStatus
         * @description Where a purchase case stands (CONTEXT.md, "Purchase case").
         * @enum {string}
         */
        CaseStatus: "received" | "awaiting_approval" | "approved" | "rejected" | "rfq_drafted" | "awaiting_reapproval" | "supplier_selected" | "po_drafted";
        /**
         * CaseVersionBody
         * @description The version of the case the caller saw: a stale one is refused (409).
         */
        CaseVersionBody: {
            /** Case Version */
            case_version: number;
        };
        /** Choice */
        Choice: {
            /** Line No */
            line_no: number;
            /** Supplier Code */
            supplier_code: string;
        };
        /** ComparedLine */
        ComparedLine: {
            /** Description */
            description: string;
            /** Line No */
            line_no: number;
            /** Need By */
            need_by: string | null;
            /** Offers */
            offers: components["schemas"]["ComparedOffer"][];
            /** Quantity */
            quantity: string;
        };
        /** ComparedOffer */
        ComparedOffer: {
            /** Cheapest */
            cheapest: boolean;
            /** Lead Time Days */
            lead_time_days: number;
            /** Meets Need By */
            meets_need_by: boolean;
            /** Supplier Code */
            supplier_code: string;
            /** Total */
            total: string;
            /** Unit Price */
            unit_price: string;
        };
        /** ComparisonView */
        ComparisonView: {
            /** Approved Limit */
            approved_limit: string | null;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            /** Currency */
            currency: string;
            /** Lines */
            lines: components["schemas"]["ComparedLine"][];
        };
        /**
         * Confirmation
         * @description A supplier's confirmation of one order, read from one mail.
         */
        Confirmation: {
            /** Accepted At */
            accepted_at?: string | null;
            /** Accepted By */
            accepted_by?: string | null;
            /** Differences */
            differences: components["schemas"]["Difference"][];
            /** Lines */
            lines: components["schemas"]["ConfirmedLine"][];
            /**
             * Read At
             * Format: date-time
             */
            read_at: string;
            /**
             * Read By
             * Format: uuid
             */
            read_by: string;
            /** Source Ref */
            source_ref: string;
        };
        /**
         * ConfirmationMail
         * @description A verified mail from the supplier of one of a case's orders that names
         *     the order, not read yet: what a buyer presses "DW2 đọc" on.
         */
        ConfirmationMail: {
            /** Message Id */
            message_id: string;
            /** Po Ref */
            po_ref: string;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Sender */
            sender: string;
            /** Subject */
            subject: string;
        };
        /**
         * ConfirmedLine
         * @description One line as the supplier confirmed it; None where the mail says
         *     nothing of that value.
         */
        ConfirmedLine: {
            /** Delivery On */
            delivery_on?: string | null;
            /** Line No */
            line_no: number;
            /** Quantity */
            quantity?: string | null;
            /** Unit Price */
            unit_price?: string | null;
        };
        /**
         * CrossCheck
         * @description What code found, stamped on the case when it goes to its approver.
         */
        CrossCheck: {
            /** Amount */
            amount: string | null;
            /**
             * Checked On
             * Format: date
             */
            checked_on: string;
            /** Currency */
            currency: string;
            /** Findings */
            findings: components["schemas"]["Finding"][];
            /** Lines */
            lines: components["schemas"]["LineCheck"][];
        };
        /**
         * Decided
         * @description The approver's decision, as the approval recorded it.
         */
        Decided: {
            /** Approved */
            approved: boolean;
            /**
             * Comment
             * @default
             */
            comment: string;
            /**
             * Decided At
             * Format: date-time
             */
            decided_at: string;
            /**
             * Decided By
             * Format: uuid
             */
            decided_by: string;
        };
        /**
         * Difference
         * @description Where a confirmation and its order part, as text a buyer reads.
         */
        Difference: {
            /** Confirmed */
            confirmed: string | null;
            /**
             * Field
             * @enum {string}
             */
            field: "quantity" | "unit_price" | "delivery_on" | "missing" | "not_ordered";
            /** Line No */
            line_no: number;
            /** Ordered */
            ordered: string | null;
        };
        /**
         * Disposition
         * @description What DW2 did with one mail.
         * @enum {string}
         */
        Disposition: "opened" | "to_person";
        /**
         * DraftView
         * @description What the requester's page shows after DW2 read their words: the
         *     draft, what the form rules still ask for, or why there is none.
         */
        DraftView: {
            draft: components["schemas"]["RequestDraft"] | null;
            /** Missing */
            missing: ("budget_code" | "need_by" | "estimated_unit_price")[];
            /** Not Read */
            not_read: string | null;
        };
        /** Finding */
        Finding: {
            code: components["schemas"]["PurchaseFindingCode"];
            /** Line No */
            line_no?: number | null;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * InboxItem
         * @description One mail in the list a buyer works from.
         */
        InboxItem: {
            /** Case Id */
            case_id: string | null;
            disposition: components["schemas"]["Disposition"] | null;
            /** Message Id */
            message_id: string;
            /** Reason */
            reason: string | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Sender */
            sender: string;
            /** Subject */
            subject: string;
        };
        /**
         * LateLine
         * @description One line past its date with less arrived than ordered.
         */
        LateLine: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /**
             * Due On
             * Format: date
             */
            due_on: string;
            /** Line No */
            line_no: number;
            /** Owed */
            owed: string;
            /** Po Ref */
            po_ref: string;
            /** Pr No */
            pr_no: string;
            /** Supplier Code */
            supplier_code: string;
        };
        /** LineCheck */
        LineCheck: {
            /** Amount */
            amount: string | null;
            /** Basis */
            basis: ("quote" | "history" | "estimate") | null;
            /** Line No */
            line_no: number;
            /** Reference Price */
            reference_price: string | null;
            /** Supplier Code */
            supplier_code: string | null;
        };
        /**
         * ListChange
         * @description One list of a new version beside the one in force.
         */
        ListChange: {
            /** Added */
            added: number;
            /** Changed */
            changed: number;
            /** In File */
            in_file: boolean;
            /** In Force */
            in_force: number;
            /**
             * List
             * @enum {string}
             */
            list: "items" | "suppliers" | "quotes" | "history" | "budgets";
            /** Removed */
            removed: number;
            /** Rows */
            rows: number;
            /** Sheet */
            sheet: string;
        };
        /** ListCount */
        ListCount: {
            /** List */
            list: string;
            /** Rows */
            rows: number;
            /** Sheet */
            sheet: string;
        };
        /**
         * MasterDataView
         * @description The page: the lists in force and whose, the version waiting to be
         *     decided if any, and the latest uploads.
         */
        MasterDataView: {
            /** Can Upload */
            can_upload: boolean;
            /** Imports */
            imports: components["schemas"]["MasterImportView"][];
            /**
             * Layer
             * @enum {string}
             */
            layer: "platform" | "tenant";
            /** Lists */
            lists: components["schemas"]["ListCount"][];
            /** Ref */
            ref: string;
            /** Waiting */
            waiting: string | null;
        };
        /**
         * MasterImportView
         * @description An import as the page shows it: the file, how far it got, and, once
         *     read, what it would change beside the lists in force now.
         */
        MasterImportView: {
            /** Blocked */
            blocked: string | null;
            /** Changes */
            changes: components["schemas"]["ListChange"][];
            /** Dropped */
            dropped: {
                [key: string]: number;
            };
            /** Failure */
            failure: string | null;
            /** File Name */
            file_name: string;
            /**
             * Import Id
             * Format: uuid
             */
            import_id: string;
            /** Read At */
            read_at: string | null;
            /** Rejected */
            rejected: components["schemas"]["Rejected"][];
            /** Rejected Total */
            rejected_total: number;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "parsed" | "failed" | "submitted";
            /**
             * Uploaded At
             * Format: date-time
             */
            uploaded_at: string;
            /**
             * Uploaded By
             * Format: uuid
             */
            uploaded_by: string;
            /** Version Ref */
            version_ref: string | null;
        };
        /**
         * MasterUploadBody
         * @description A master-data workbook: its name and its bytes, base64. Decoded here
         *     and never opened: the worker reads it in the reader sandbox.
         */
        MasterUploadBody: {
            /** Content B64 */
            content_b64: string;
            /** File Name */
            file_name: string;
        };
        /**
         * MyRequest
         * @description What a requester sends: no PR number and no requester name, which are
         *     code's and the directory's. ``department`` is read only where the
         *     directory names none for them.
         */
        MyRequest: {
            /** Budget Code */
            budget_code?: string | null;
            /** Currency */
            currency: string;
            /** Department */
            department?: string | null;
            /** Lines */
            lines: components["schemas"]["PrLine-Input"][];
            /** Need By */
            need_by?: string | null;
            /**
             * Note
             * @default
             */
            note: string;
        };
        /**
         * Offer
         * @description What one supplier offers for one line.
         */
        Offer: {
            /** Currency */
            currency: string;
            /** Lead Time Days */
            lead_time_days: number;
            /** Line No */
            line_no: number;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /**
             * Recorded By
             * Format: uuid
             */
            recorded_by: string;
            /**
             * Source
             * @enum {string}
             */
            source: "form" | "mail";
            /** Source Ref */
            source_ref?: string | null;
            /** Supplier Code */
            supplier_code: string;
            /** Unit Price */
            unit_price: string;
            /** Valid Until */
            valid_until?: string | null;
        };
        /** OfferBody */
        OfferBody: {
            /** Case Version */
            case_version: number;
            offer: components["schemas"]["OfferForm"];
        };
        /**
         * OfferForm
         * @description An offer a buyer types (a supplier answered by phone, or on paper).
         */
        OfferForm: {
            /** Currency */
            currency: string;
            /** Lead Time Days */
            lead_time_days: number;
            /** Line No */
            line_no: number;
            /** Supplier Code */
            supplier_code: string;
            /** Unit Price */
            unit_price: number | string;
            /** Valid Until */
            valid_until?: string | null;
        };
        /**
         * OrderTracking
         * @description What happened to one drafted order, by its `po_ref`.
         */
        OrderTracking: {
            /** Bravo At */
            bravo_at?: string | null;
            /** Bravo By */
            bravo_by?: string | null;
            /** Bravo No */
            bravo_no?: string | null;
            confirmation?: components["schemas"]["Confirmation"] | null;
            /** Po Ref */
            po_ref: string;
            /**
             * Receipts
             * @default []
             */
            receipts: components["schemas"]["Receipt"][];
        };
        /**
         * PoDraft
         * @description One supplier's draft order.
         */
        PoDraft: {
            /** Currency */
            currency: string;
            /** Lines */
            lines: components["schemas"]["PoLine"][];
            /** Po Ref */
            po_ref: string;
            /** Supplier Code */
            supplier_code: string;
            /** Supplier Name */
            supplier_name: string;
            /** Total */
            total: string;
        };
        /** PoLine */
        PoLine: {
            /** Amount */
            amount: string;
            /** Description */
            description: string;
            /** Item Code */
            item_code: string | null;
            /** Line No */
            line_no: number;
            /** Need By */
            need_by: string | null;
            /** Quantity */
            quantity: string;
            /** Unit */
            unit: string;
            /** Unit Price */
            unit_price: string;
        };
        /**
         * PoRound
         * @description The orders drafted for a case, and the layout their file is drawn with.
         */
        PoRound: {
            /**
             * Drafted At
             * Format: date-time
             */
            drafted_at: string;
            /**
             * Drafted By
             * Format: uuid
             */
            drafted_by: string;
            layout: components["schemas"]["BravoPoLayout"];
            /**
             * Order Date
             * Format: date
             */
            order_date: string;
            /** Orders */
            orders: components["schemas"]["PoDraft"][];
            /** Rules Ref */
            rules_ref: string;
        };
        /**
         * PrLine
         * @description One thing asked for.
         */
        "PrLine-Input": {
            /** Description */
            description: string;
            /** Estimated Unit Price */
            estimated_unit_price?: number | string | null;
            /** Item Code */
            item_code?: string | null;
            /** Line No */
            line_no: number;
            /** Need By */
            need_by?: string | null;
            /** Quantity */
            quantity: number | string;
            /** Unit */
            unit: string;
        };
        /**
         * PrLine
         * @description One thing asked for.
         */
        "PrLine-Output": {
            /** Description */
            description: string;
            /** Estimated Unit Price */
            estimated_unit_price?: string | null;
            /** Item Code */
            item_code?: string | null;
            /** Line No */
            line_no: number;
            /** Need By */
            need_by?: string | null;
            /** Quantity */
            quantity: string;
            /** Unit */
            unit: string;
        };
        /**
         * PrSource
         * @description Where the request came from (DW02: email, Bravo, form, scanned paper;
         *     a mail's own words, its Excel form or its scanned paper are all `mail`,
         *     `ReadFrom` saying which).
         * @enum {string}
         */
        PrSource: "form" | "mail" | "requester";
        /**
         * PurchaseCase
         * @description One request, from the moment DW2 received it.
         *
         *     ``rules_ref`` is the tenant rules the case was received under
         *     (``purchasing_rules@<version>``), stamped once: a later reader takes the
         *     stamp, never whatever is in force today.
         */
        PurchaseCase: {
            approval?: components["schemas"]["ApprovalAsked"] | null;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            check?: components["schemas"]["CrossCheck"] | null;
            decision?: components["schemas"]["Decided"] | null;
            /**
             * Offers
             * @default []
             */
            offers: components["schemas"]["Offer"][];
            po?: components["schemas"]["PoRound"] | null;
            read_from?: components["schemas"]["ReadFrom"] | null;
            reapproval?: components["schemas"]["Reapproval"] | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /**
             * Received By
             * Format: uuid
             */
            received_by: string;
            request: components["schemas"]["PurchaseRequest-Output"];
            /** Requested By */
            requested_by?: string | null;
            review?: components["schemas"]["Review"] | null;
            rfq?: components["schemas"]["RfqRound"] | null;
            /** Rules Ref */
            rules_ref: string;
            selection?: components["schemas"]["Selection"] | null;
            source: components["schemas"]["PrSource"];
            /** Source Ref */
            source_ref?: string | null;
            status: components["schemas"]["CaseStatus"];
            /**
             * Tracking
             * @default []
             */
            tracking: components["schemas"]["OrderTracking"][];
        };
        /**
         * PurchaseCheckView
         * @description What the check found and who would approve, under the rules in force.
         */
        PurchaseCheckView: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            check: components["schemas"]["CrossCheck"];
            /** Required Scope */
            required_scope: string;
            /** Rules Ref */
            rules_ref: string;
            /** Tier Label */
            tier_label: string;
        };
        /**
         * PurchaseFindingCode
         * @enum {string}
         */
        PurchaseFindingCode: "item_unknown" | "no_reference_price" | "currency_mismatch" | "estimate_above_reference" | "need_by_short" | "budget_missing" | "budget_unknown" | "over_budget";
        /**
         * PurchaseRequest
         * @description What the requester asked for, as they wrote it.
         */
        "PurchaseRequest-Input": {
            /** Budget Code */
            budget_code?: string | null;
            /** Currency */
            currency: string;
            /** Department */
            department: string;
            /** Lines */
            lines: components["schemas"]["PrLine-Input"][];
            /** Need By */
            need_by?: string | null;
            /**
             * Note
             * @default
             */
            note: string;
            /** Pr No */
            pr_no: string;
            /** Requester */
            requester: string;
        };
        /**
         * PurchaseRequest
         * @description What the requester asked for, as they wrote it.
         */
        "PurchaseRequest-Output": {
            /** Budget Code */
            budget_code?: string | null;
            /** Currency */
            currency: string;
            /** Department */
            department: string;
            /** Lines */
            lines: components["schemas"]["PrLine-Output"][];
            /** Need By */
            need_by?: string | null;
            /**
             * Note
             * @default
             */
            note: string;
            /** Pr No */
            pr_no: string;
            /** Requester */
            requester: string;
        };
        /** PurchasingKeyInForce */
        PurchasingKeyInForce: {
            /** Document */
            document: {
                [key: string]: unknown;
            };
            key: components["schemas"]["PurchasingRuleKey"];
            /**
             * Layer
             * @enum {string}
             */
            layer: "platform" | "tenant";
            /** Platform Ref */
            platform_ref: string;
            /** Ref */
            ref: string;
        };
        /**
         * PurchasingModelStep
         * @description The model calls a step's `ai_auto` waits on, each measured on its own
         *     (`dw_purchasing.application.automation.BARS`).
         * @enum {string}
         */
        PurchasingModelStep: "purchasing_pr_mail_reading";
        /**
         * PurchasingRuleKey
         * @description What a tenant may hold its own version of.
         * @enum {string}
         */
        PurchasingRuleKey: "purchasing_rules" | "purchasing_automation" | "purchasing_master_data";
        /**
         * PurchasingRuleVersionView
         * @description A version as the settings page lists it.
         */
        PurchasingRuleVersionView: {
            /** Applied Directly */
            applied_directly: boolean;
            /** Approval Id */
            approval_id: string | null;
            /** Comment */
            comment: string | null;
            /** Decided At */
            decided_at: string | null;
            /** Decided By */
            decided_by: string | null;
            /** Document */
            document: {
                [key: string]: unknown;
            };
            key: components["schemas"]["PurchasingRuleKey"];
            /**
             * Proposed At
             * Format: date-time
             */
            proposed_at: string;
            /**
             * Proposed By
             * Format: uuid
             */
            proposed_by: string;
            /**
             * Status
             * @enum {string}
             */
            status: "proposed" | "approved" | "rejected" | "superseded";
            /** Version */
            version: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * PurchasingRuleWordsBody
         * @description What a person wants changed, in their words, and the part it is about.
         */
        PurchasingRuleWordsBody: {
            /** Focus */
            focus?: string | null;
            /** Request */
            request: string;
        };
        /** PurchasingRulesView */
        PurchasingRulesView: {
            /** Keys */
            keys: components["schemas"]["PurchasingKeyInForce"][];
            /** Versions */
            versions: components["schemas"]["PurchasingRuleVersionView"][];
        };
        /**
         * ReadFrom
         * @description Where in a mail DW2 read the request, when a document was attached:
         *     the file (its id in the stored mailbox, and its name) when the lines
         *     were in it (None: the mail's own words), and whether any value was read
         *     only on a scanned page, which a person compares with the paper before
         *     DW2 sends it on (`review`).
         */
        ReadFrom: {
            /** Attachment */
            attachment?: string | null;
            /** Attachment Id */
            attachment_id?: string | null;
            /**
             * Scanned
             * @default false
             */
            scanned: boolean;
        };
        /**
         * Reapproval
         * @description A choice of suppliers whose total passed what the approver's tier
         *     decides (plus the tenant's tolerance), sent to the tier that total names:
         *     the choice waits here, and becomes the case's selection only once that
         *     approver approves it. ``explanation`` is the model's words for why, kept
         *     only when every figure in them is one of code's facts; None otherwise.
         */
        Reapproval: {
            approval: components["schemas"]["ApprovalAsked"];
            /** Approved Limit */
            approved_limit: string | null;
            decision?: components["schemas"]["Decided"] | null;
            /** Explanation */
            explanation?: string | null;
            selection: components["schemas"]["Selection"];
        };
        /**
         * Receipt
         * @description Goods of one line that arrived, as a buyer recorded them.
         */
        Receipt: {
            /** Line No */
            line_no: number;
            /** Quantity */
            quantity: string;
            /**
             * Received On
             * Format: date
             */
            received_on: string;
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /**
             * Recorded By
             * Format: uuid
             */
            recorded_by: string;
        };
        /** ReceiptBody */
        ReceiptBody: {
            /** Case Version */
            case_version: number;
            /** Line No */
            line_no: number;
            /** Quantity */
            quantity: number | string;
            /**
             * Received On
             * Format: date
             */
            received_on: string;
        };
        /**
         * Rejected
         * @description A row that was not applied, and why (never a value of the row).
         */
        Rejected: {
            /** Reason */
            reason: string;
            /** Row */
            row: number | null;
            /** Sheet */
            sheet: string;
        };
        /**
         * ReplyItem
         * @description A mail that answers one of the case's RFQs, as the offer card lists it.
         */
        ReplyItem: {
            /** Message Id */
            message_id: string;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Sender */
            sender: string;
            /** Subject */
            subject: string;
            /** Supplier Code */
            supplier_code: string;
        };
        /**
         * RequestDraft
         * @description What a requester's own words ask for, as code read it from the model's
         *     spans: the lines, and the request-wide values the words name. No PR
         *     number, department or requester: those are not the words' to say (code
         *     numbers the request, the requester is the signed-in person).
         */
        RequestDraft: {
            /** Budget Code */
            budget_code?: string | null;
            /** Currency */
            currency: string;
            /** Lines */
            lines: components["schemas"]["PrLine-Output"][];
            /** Need By */
            need_by?: string | null;
        };
        /**
         * Review
         * @description A case DW2 opened on its own, or read from a scan, that a person is to
         *     look over first.
         */
        Review: {
            /**
             * Asked At
             * Format: date-time
             */
            asked_at: string;
            /** Reviewed At */
            reviewed_at?: string | null;
            /** Reviewed By */
            reviewed_by?: string | null;
        };
        /**
         * RfqBody
         * @description The version the buyer saw, and the suppliers they name for a line the
         *     master data lists nobody for (or one more for a line).
         */
        RfqBody: {
            /** Case Version */
            case_version: number;
            /** Suppliers */
            suppliers?: components["schemas"]["Choice"][];
        };
        /**
         * RfqDraft
         * @description One supplier's RFQ: who receives it, which lines, and the words.
         */
        RfqDraft: {
            /**
             * Body
             * @default
             */
            body: string;
            /** Line Nos */
            line_nos: number[];
            /**
             * Subject
             * @default
             */
            subject: string;
            /** Supplier Code */
            supplier_code: string;
            /** To */
            to: string[];
            /**
             * Written By
             * @enum {string}
             */
            written_by: "model" | "person" | "pending" | "template";
        };
        /**
         * RfqMailView
         * @description A mail as the case page lists it: never its words, which the case has.
         */
        RfqMailView: {
            /** Error */
            error: ("not_connected" | "flow_failed" | "no_receipt") | null;
            /**
             * Mail Id
             * Format: uuid
             */
            mail_id: string;
            /** Mailbox */
            mailbox: string;
            /**
             * Queued At
             * Format: date-time
             */
            queued_at: string;
            /**
             * Queued By
             * Format: uuid
             */
            queued_by: string;
            /** Settled At */
            settled_at: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "written" | "sent" | "failed" | "stalled";
            /** Supplier Code */
            supplier_code: string;
        };
        /** RfqRound */
        RfqRound: {
            /**
             * Drafted At
             * Format: date-time
             */
            drafted_at: string;
            /**
             * Drafted By
             * Format: uuid
             */
            drafted_by: string;
            /** Drafts */
            drafts: components["schemas"]["RfqDraft"][];
            /**
             * Reply By
             * Format: date
             */
            reply_by: string;
            /**
             * Unsourced
             * @default []
             */
            unsourced: number[];
        };
        /**
         * RfqWordsBody
         * @description A buyer's words for one supplier's RFQ.
         */
        RfqWordsBody: {
            /** Body */
            body: string;
            /** Case Version */
            case_version: number;
            /** Subject */
            subject: string;
        };
        /**
         * RuleChange
         * @description What a proposal answers, and what the idempotency store keeps: ids and
         *     the status, never the document (it holds the company's limits).
         */
        RuleChange: {
            /** Applied Directly */
            applied_directly: boolean;
            /** Approval Id */
            approval_id: string | null;
            /** Status */
            status: string;
            /** Version */
            version: string;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * RulesBody
         * @description A whole version of a key: what the settings page drafted and the person
         *     read as a difference in words before sending.
         */
        RulesBody: {
            /** Document */
            document: {
                [key: string]: unknown;
            };
        };
        /**
         * Selection
         * @description The suppliers a person chose, line by line, and what that comes to.
         */
        Selection: {
            /** Choices */
            choices: components["schemas"]["Choice"][];
            /** Currency */
            currency: string;
            /**
             * Selected At
             * Format: date-time
             */
            selected_at: string;
            /**
             * Selected By
             * Format: uuid
             */
            selected_by: string;
            /** Total */
            total: string;
        };
        /** SelectionBody */
        SelectionBody: {
            /** Case Version */
            case_version: number;
            /** Choices */
            choices: components["schemas"]["Choice"][];
        };
        /**
         * StepLevelView
         * @description One step's switch as the settings page shows it: the level set, the
         *     level it runs at now, why they differ, and how far it may go.
         */
        StepLevelView: {
            ceiling: components["schemas"]["AutomationLevel"];
            chosen: components["schemas"]["AutomationLevel"];
            level: components["schemas"]["AutomationLevel"];
            /** Model Steps */
            model_steps: components["schemas"]["PurchasingModelStep"][];
            step: components["schemas"]["AutomationStep"];
            /** Waiting On */
            waiting_on: components["schemas"]["PurchasingModelStep"][];
            /**
             * Why
             * @enum {string}
             */
            why: "set" | "not_measured" | "unreadable";
        };
        /** SupplierName */
        SupplierName: {
            /** Code */
            code: string;
            /** Name */
            name: string;
        };
        /** SwitchesView */
        SwitchesView: {
            /** Ref */
            ref: string;
            /** Steps */
            steps: components["schemas"]["StepLevelView"][];
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * WordsBody
         * @description What a requester typed in "Tôi cần mua…".
         */
        WordsBody: {
            /** Words */
            words: string;
        };
        /**
         * WordsDraft
         * @description What the settings page shows: the whole document changed, the paths
         *     the machine changed ("Máy đề xuất"), the version it would be, or the
         *     problems that refused it (codes and paths, never a word of the model's).
         */
        WordsDraft: {
            /** Base Ref */
            base_ref: string;
            /** Changed */
            changed: string[];
            /** Document */
            document: {
                [key: string]: unknown;
            } | null;
            /** Key */
            key: string;
            /** Problems */
            problems: string[];
            /** Version */
            version: string | null;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    assistant_ask_api_v1_purchasing_assistant_ask_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssistantAskBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssistantAnswerView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    assistant_sessions_api_v1_purchasing_assistant_sessions_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssistantSessionView"][];
                };
            };
        };
    };
    assistant_session_api_v1_purchasing_assistant_sessions__session_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssistantSessionDetailView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    automation_api_v1_purchasing_automation_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SwitchesView"];
                };
            };
        };
    };
    mailbox_api_v1_purchasing_mail_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InboxItem"][];
                };
            };
        };
    };
    read_mail_api_v1_purchasing_mail__message_id__read_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                message_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InboxItem"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    master_data_api_v1_purchasing_master_data_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MasterDataView"];
                };
            };
        };
    };
    master_upload_api_v1_purchasing_master_data_imports_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MasterUploadBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MasterImportView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    master_import_api_v1_purchasing_master_data_imports__import_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                import_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MasterImportView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    master_submit_api_v1_purchasing_master_data_imports__import_id__submit_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                import_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MasterImportView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    master_template_api_v1_purchasing_master_data_template_xlsx_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
        };
    };
    late_lines_api_v1_purchasing_orders_late_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LateLine"][];
                };
            };
        };
    };
    list_requests_api_v1_purchasing_requests_get: {
        parameters: {
            query?: {
                before_at?: string | null;
                before_id?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CasePage"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_request_api_v1_purchasing_requests_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PurchaseRequest-Input"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_my_request_api_v1_purchasing_requests_mine_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    draft_my_request_api_v1_purchasing_requests_mine_draft_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WordsBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DraftView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_request_api_v1_purchasing_requests__case_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PurchaseCase"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    check_request_api_v1_purchasing_requests__case_id__check_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PurchaseCheckView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    comparison_api_v1_purchasing_requests__case_id__comparison_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ComparisonView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    record_offer_api_v1_purchasing_requests__case_id__offers_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OfferBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_offer_mail_api_v1_purchasing_requests__case_id__offers_from_mail__message_id__post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                message_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseVersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    draft_orders_api_v1_purchasing_requests__case_id__po_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseVersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    bravo_file_api_v1_purchasing_requests__case_id__po_bravo_xlsx_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    confirmation_mails_api_v1_purchasing_requests__case_id__po_confirmations_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmationMail"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    read_confirmation_api_v1_purchasing_requests__case_id__po_confirmations_from_mail__message_id__post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                message_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseVersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    record_bravo_no_api_v1_purchasing_requests__case_id__po__po_ref__bravo_number_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                po_ref: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BravoNoBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    accept_confirmation_api_v1_purchasing_requests__case_id__po__po_ref__confirmation_accept_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                po_ref: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseVersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    record_receipt_api_v1_purchasing_requests__case_id__po__po_ref__receipts_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                po_ref: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReceiptBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    review_request_api_v1_purchasing_requests__case_id__review_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseVersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    draft_rfq_api_v1_purchasing_requests__case_id__rfq_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RfqBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rfq_mails_api_v1_purchasing_requests__case_id__rfq_mails_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RfqMailView"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rfq_replies_api_v1_purchasing_requests__case_id__rfq_replies_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReplyItem"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    write_rfq_api_v1_purchasing_requests__case_id__rfq__supplier_code__post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                supplier_code: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RfqWordsBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    send_rfq_api_v1_purchasing_requests__case_id__rfq__supplier_code__send_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                supplier_code: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RfqMailView"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    select_suppliers_api_v1_purchasing_requests__case_id__selection_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SelectionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    submit_request_for_approval_api_v1_purchasing_requests__case_id__submit_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaseVersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rules_in_force_api_v1_purchasing_rules_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PurchasingRulesView"];
                };
            };
        };
    };
    rule_schema_api_v1_purchasing_rules__key__schema_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: unknown;
                    };
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    propose_rules_api_v1_purchasing_rules__key__versions_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RulesBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RuleChange"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    rule_in_words_api_v1_purchasing_rules__key__words_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PurchasingRuleWordsBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WordsDraft"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    suppliers_api_v1_purchasing_suppliers_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupplierName"][];
                };
            };
        };
    };
}
