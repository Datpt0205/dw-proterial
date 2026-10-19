/**
 * Auto-generated types for context "sales" — do not edit.
 * Regenerate with `make generate-contracts`.
 */
export interface paths {
    "/api/v1/sales/inbox": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Inbox */
        get: operations["inbox_api_v1_sales_inbox_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/inbox/process-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Process All */
        post: operations["process_all_api_v1_sales_inbox_process_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/inbox/{message_id}/process": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Process */
        post: operations["process_api_v1_sales_inbox__message_id__process_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/layouts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Layouts */
        get: operations["layouts_api_v1_sales_layouts_get"];
        put?: never;
        /** Propose Layout */
        post: operations["propose_layout_api_v1_sales_layouts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/layouts/preview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Layout Preview */
        post: operations["layout_preview_api_v1_sales_layouts_preview_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/layouts/source": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Layout Source */
        get: operations["layout_source_api_v1_sales_layouts_source_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/bravo-orders": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Bravo Orders */
        get: operations["bravo_orders_api_v1_sales_master_data_bravo_orders_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/convert-list": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Convert List */
        get: operations["convert_list_api_v1_sales_master_data_convert_list_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/customers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Customers */
        get: operations["customers_api_v1_sales_master_data_customers_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Items */
        get: operations["items_api_v1_sales_master_data_items_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/lme": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Lme */
        get: operations["lme_api_v1_sales_master_data_lme_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/open-ycbg": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Open Ycbg */
        get: operations["open_ycbg_api_v1_sales_master_data_open_ycbg_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/quotations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quotations */
        get: operations["quotations_api_v1_sales_master_data_quotations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/my-work": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** My Work */
        get: operations["my_work_api_v1_sales_my_work_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Orders */
        get: operations["orders_api_v1_sales_orders_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order */
        get: operations["order_api_v1_sales_orders__case_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Artifacts */
        get: operations["order_artifacts_api_v1_sales_orders__case_id__artifacts_get"];
        put?: never;
        /** Render Order Artifact */
        post: operations["render_order_artifact_api_v1_sales_orders__case_id__artifacts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/artifacts/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Artifact */
        get: operations["order_artifact_api_v1_sales_orders__case_id__artifacts__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/assignee": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Reassign Order */
        put: operations["reassign_order_api_v1_sales_orders__case_id__assignee_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/assignees": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Assignees */
        get: operations["order_assignees_api_v1_sales_orders__case_id__assignees_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/bravo-entry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Bravo Entry */
        post: operations["bravo_entry_api_v1_sales_orders__case_id__bravo_entry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/close": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Close */
        post: operations["close_api_v1_sales_orders__case_id__close_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm */
        post: operations["confirm_api_v1_sales_orders__case_id__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/correction-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Correction Request */
        post: operations["correction_request_api_v1_sales_orders__case_id__correction_request_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/findings/{finding_key}/corrections": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Correct Value */
        post: operations["correct_value_api_v1_sales_orders__case_id__findings__finding_key__corrections_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/findings/{finding_key}/disposition": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Dispose */
        post: operations["dispose_api_v1_sales_orders__case_id__findings__finding_key__disposition_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/lines/{line_no}/delivery-date": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Delivery Date
         * @description PC agreed the line's short lead time: recorded as who and when.
         */
        post: operations["delivery_date_api_v1_sales_orders__case_id__lines__line_no__delivery_date_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/lines/{line_no}/mapping": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mapping */
        post: operations["mapping_api_v1_sales_orders__case_id__lines__line_no__mapping_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/prepare": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Prepare */
        post: operations["prepare_api_v1_sales_orders__case_id__prepare_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/resend-cross-check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resend Cross Check
         * @description "Gửi kiểm chéo lại" (ticket 14). Whoever recorded the Bravo entry,
         *     with `sales.order.prepare`; anyone else also needs
         *     `sales.order.resend_cross_check`, which the case checks (403).
         */
        post: operations["resend_cross_check_api_v1_sales_orders__case_id__resend_cross_check_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/resume-review": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resume Review */
        post: operations["resume_review_api_v1_sales_orders__case_id__resume_review_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/source/{attachment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Source */
        get: operations["order_source_api_v1_sales_orders__case_id__source__attachment_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/overview": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Overview */
        get: operations["overview_api_v1_sales_overview_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quotes */
        get: operations["quotes_api_v1_sales_quotes_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/screening": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Screening */
        get: operations["screening_api_v1_sales_quotes_screening_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote */
        get: operations["quote_api_v1_sales_quotes__case_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/artifacts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Artifacts */
        get: operations["quote_artifacts_api_v1_sales_quotes__case_id__artifacts_get"];
        put?: never;
        /** Render Quote Artifact */
        post: operations["render_quote_artifact_api_v1_sales_quotes__case_id__artifacts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/artifacts/{artifact_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Artifact */
        get: operations["quote_artifact_api_v1_sales_quotes__case_id__artifacts__artifact_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/assignee": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Reassign Quote */
        put: operations["reassign_quote_api_v1_sales_quotes__case_id__assignee_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/assignees": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Assignees */
        get: operations["quote_assignees_api_v1_sales_quotes__case_id__assignees_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/decline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decline */
        post: operations["decline_api_v1_sales_quotes__case_id__decline_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/design-sent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Design Sent */
        post: operations["design_sent_api_v1_sales_quotes__case_id__design_sent_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/findings/{finding_key}/answer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Answer */
        post: operations["answer_api_v1_sales_quotes__case_id__findings__finding_key__answer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/master-list": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Master List */
        post: operations["master_list_api_v1_sales_quotes__case_id__master_list_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/message-text": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Message Text */
        get: operations["quote_message_text_api_v1_sales_quotes__case_id__message_text_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/price": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Price */
        post: operations["price_api_v1_sales_quotes__case_id__price_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/sent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Sent */
        post: operations["sent_api_v1_sales_quotes__case_id__sent_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/source/{attachment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Source */
        get: operations["quote_source_api_v1_sales_quotes__case_id__source__attachment_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/spec-discussion": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Spec Discussion */
        post: operations["spec_discussion_api_v1_sales_quotes__case_id__spec_discussion_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/submit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit */
        post: operations["submit_api_v1_sales_quotes__case_id__submit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/ycbg": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Ycbg */
        post: operations["ycbg_api_v1_sales_quotes__case_id__ycbg_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/rules": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rules In Force */
        get: operations["rules_in_force_api_v1_sales_rules_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/rules/{key}/platform": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rule Platform Documents */
        get: operations["rule_platform_documents_api_v1_sales_rules__key__platform_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/rules/{key}/schema": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rule Schema */
        get: operations["rule_schema_api_v1_sales_rules__key__schema_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/rules/{key}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Propose Rules */
        post: operations["propose_rules_api_v1_sales_rules__key__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/worker/pause": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pause */
        post: operations["pause_api_v1_sales_worker_pause_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/worker/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resume */
        post: operations["resume_api_v1_sales_worker_resume_post"];
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
        Amount: string | components["schemas"]["Hidden"];
        /** AnswerBody */
        AnswerBody: {
            /** Case Version */
            case_version: number;
            /** Customer Code */
            customer_code?: string | null;
            /** Field */
            field?: string | null;
            /** Needed By */
            needed_by?: string | null;
            /** Note */
            note?: string | null;
            /** Quantity */
            quantity?: number | string | null;
            /** Value */
            value?: string | null;
        };
        /** ArtifactListView */
        ArtifactListView: {
            /** Artifacts */
            artifacts: components["schemas"]["ArtifactView"][];
            /** Available */
            available: string[];
            /** Case Version */
            case_version: number;
        };
        /**
         * ArtifactView
         * @description One stored file: what the approval view shows beside it (template,
         *     case version, hash), and whether this caller may download it now.
         */
        ArtifactView: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
            /** Case Version */
            case_version: number;
            /** Content Type */
            content_type: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By
             * Format: uuid
             */
            created_by: string;
            /** Downloadable */
            downloadable: boolean;
            /** File Name */
            file_name: string;
            /** Kind */
            kind: string;
            /** Sha256 */
            sha256: string;
            /** Size Bytes */
            size_bytes: number;
            /** Template Ref */
            template_ref: string;
        };
        /**
         * AssigneeBody
         * @description Who the case is given to; null gives it to nobody (every PIC's).
         */
        AssigneeBody: {
            /** Assignee */
            assignee: string | null;
            /** Case Version */
            case_version: number;
        };
        /**
         * AssigneeView
         * @description A member the case may be given to.
         */
        AssigneeView: {
            /** Display Name */
            display_name: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** AttachmentView */
        AttachmentView: {
            /** Attachment Id */
            attachment_id: string;
            /** Media Type */
            media_type: string;
            /** Name */
            name: string;
            /** Size */
            size: number;
        };
        /** BravoEntryBody */
        BravoEntryBody: {
            /** Case Version */
            case_version: number;
            /** Entry Compared */
            entry_compared: boolean;
            /** So No */
            so_no?: string | null;
        };
        /** BravoOrderLineView */
        BravoOrderLineView: {
            /**
             * Delivery Date
             * Format: date
             */
            delivery_date: string;
            /** Line No */
            line_no: number;
            /** Prv Code */
            prv_code: string;
            /** Quantity */
            quantity: string;
            unit_price: components["schemas"]["Amount"];
        };
        /** BravoOrderView */
        BravoOrderView: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "USD" | "VND" | "JPY";
            /** Customer Code */
            customer_code: string;
            /** Lines */
            lines: components["schemas"]["BravoOrderLineView"][];
            /**
             * Order Date
             * Format: date
             */
            order_date: string;
            /** Po No */
            po_no: string;
            /** Po Revision */
            po_revision: number;
            /** So No */
            so_no: string;
        };
        /**
         * CaseChangeView
         * @description What a mutation answers: which case, at which version, in which state.
         */
        CaseChangeView: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            case_kind: components["schemas"]["CaseKind"];
            /** Case Version */
            case_version: number;
            /** Status */
            status: string;
        };
        /**
         * CaseKind
         * @enum {string}
         */
        CaseKind: "order" | "quote";
        /**
         * CaseReply
         * @description A message attached to a case because its thread headers name a message
         *     already on that case, of the sender's own customer (ticket 32).
         */
        CaseReply: {
            /** Linked To */
            linked_to: string;
            reading?: components["schemas"]["ReplyReading"] | null;
        };
        /**
         * CaseReplyView
         * @description A customer's reply attached to the case by its thread (ticket 32), with
         *     what a model read of it and the step code proposes from that, now.
         *
         *     ``proposal`` is computed from the case's status as it is now, and only for
         *     the newest reply: an older reply's reading does not pre-select anything.
         *     It is a suggestion: the step is the existing one, which Sales confirms and
         *     the server checks as for any other caller. The quotes are the customer's
         *     sentences, shown to a case reader as the inbox shows the whole mail.
         */
        CaseReplyView: {
            /** Kind */
            kind: ("accepts_spec" | "rejects_spec" | "counter_proposal" | "sends_corrected_po" | "keeps_po_as_is" | "question" | "unclear") | null;
            /** Linked To */
            linked_to: string;
            /** Message Id */
            message_id: string;
            /** Outcome */
            outcome: ("read" | "unavailable") | null;
            /**
             * Processed At
             * Format: date-time
             */
            processed_at: string;
            /** Prompt */
            prompt: string | null;
            /** Proposal */
            proposal: ("settle_spec" | "decline_customer_rejected_spec" | "resume_review" | "await_revised_po") | null;
            /** Quotes */
            quotes: string[];
        };
        /** CloseBody */
        CloseBody: {
            /** Case Version */
            case_version: number;
            reason: components["schemas"]["CloseReason"];
            /** Superseded By */
            superseded_by?: string | null;
        };
        /**
         * CloseReason
         * @enum {string}
         */
        CloseReason: "duplicate" | "not_an_order" | "superseded" | "cannot_supply";
        /** ConfirmBody */
        ConfirmBody: {
            /** Case Version */
            case_version: number;
            /** Delivery Dates */
            delivery_dates: components["schemas"]["LineDate"][];
        };
        /** ConvertEntryView */
        ConvertEntryView: {
            /** Customer Code */
            customer_code: string;
            /** Customer Item Code */
            customer_item_code: string;
            /** Prv Code */
            prv_code: string;
        };
        /**
         * CopperBasisView
         * @description How a price follows copper. A band's limits are prices of copper.
         */
        CopperBasisView: {
            high_usd_per_tonne?: components["schemas"]["Amount"] | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "fixed" | "lme_band";
            low_usd_per_tonne?: components["schemas"]["Amount"] | null;
        };
        /**
         * CorrectionBody
         * @description One value a `value_uncertain` flagged, as Sales reads it on the source:
         *     the field it is, and the value as text, which the case validates as that
         *     field's type (a number, a date, a unit, text).
         */
        CorrectionBody: {
            /** Case Version */
            case_version: number;
            /** Field */
            field: string;
            /** Value */
            value: string;
        };
        /** CoverageView */
        CoverageView: {
            /** Checks Run */
            checks_run: number;
            /** Findings */
            findings: number;
            /** Lines Printed */
            lines_printed: number;
            /** Lines Read */
            lines_read: number;
            /** Regions */
            regions: string[];
            /** Unchecked Regions */
            unchecked_regions: string[];
        };
        /** CustomerView */
        CustomerView: {
            /** Code */
            code: string;
            /** Confirmation Channel */
            confirmation_channel: string;
            /** Contacts */
            contacts: string[];
            /** Denial List Checked On */
            denial_list_checked_on: string | null;
            /** Esf Fiscal Year */
            esf_fiscal_year: number | null;
            /** Intra Group */
            intra_group: boolean;
            /** Language */
            language: string;
            /** Name */
            name: string;
            /** Noc Confirmed */
            noc_confirmed: boolean;
            /** Sales Pic */
            sales_pic: string | null;
            /** Status */
            status: string;
        };
        /** DeclineBody */
        DeclineBody: {
            /** Case Version */
            case_version: number;
            /** Note */
            note?: string | null;
            reason: components["schemas"]["DeclineReason"];
        };
        /**
         * DeclineReason
         * @enum {string}
         */
        DeclineReason: "not_our_product" | "design_cannot" | "customer_rejected_spec" | "commercial";
        /** DeclineView */
        DeclineView: {
            /**
             * Declined At
             * Format: date-time
             */
            declined_at: string;
            /**
             * Declined By
             * Format: uuid
             */
            declined_by: string;
            /** Note */
            note: string | null;
            /** Reason */
            reason: string;
        };
        /**
         * DeliveryScheduleView
         * @description One delivery of a line's quantity (ticket 21), as the line is entered
         *     (a schedule the PO prints is never typed over): where it is printed,
         *     DW1's suggested date for it, and, on a line the PO splits, the date Sales
         *     confirmed for it (ticket 35).
         */
        DeliveryScheduleView: {
            anchor: components["schemas"]["SourceAnchor"];
            /** Confirmed Delivery Date */
            confirmed_delivery_date: string | null;
            /** Quantity */
            quantity: string;
            /**
             * Requested Date
             * Format: date
             */
            requested_date: string;
            /** Suggested Delivery Date */
            suggested_delivery_date: string | null;
        };
        /**
         * Derivation
         * @description How the bytes a PO was read from were made from the customer's file
         *     (ticket 27): converted from a legacy Office format, or read by OCR from
         *     images of its pages. The tool's own version is kept: another converter or
         *     engine is another reading of the same file.
         */
        Derivation: {
            /** Derived Sha256 */
            derived_sha256?: string | null;
            /**
             * Method
             * @enum {string}
             */
            method: "converted" | "ocr";
            /** Tool */
            tool: string;
        };
        /**
         * DescriptionReading
         * @description What a model reading did for one line, stamped on its check basis.
         *
         *     ``read``: every check passed, and ``spans`` are what the candidates were
         *     computed from. ``not_understood``: a check refused it (``reason``).
         *     ``unavailable``: no usable answer (the model down, timed out, or its
         *     output invalid); the line is unmapped exactly as without the model.
         */
        DescriptionReading: {
            /** Model Profile */
            model_profile: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "read" | "not_understood" | "unavailable";
            /** Prompt */
            prompt: string;
            /** Reason */
            reason?: ("line_missing" | "no_attribute" | "span_not_found" | "span_repeated" | "spans_overlap" | "value_unparsed" | "text_uncovered" | "digit_in_label" | "value_refused") | null;
            /** Route */
            route: string;
            /**
             * Spans
             * @default []
             */
            spans: components["schemas"]["SpanRead"][];
        };
        /**
         * DescriptionReadingView
         * @description What a model reading of the description did (dw_sales ADR 0005).
         *     ``outcome``: ``read``, ``not_understood`` (``reason`` says which check
         *     refused it) or ``unavailable`` (no usable answer: DW1 could not read it).
         */
        DescriptionReadingView: {
            /** Model Profile */
            model_profile: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "read" | "not_understood" | "unavailable";
            /** Prompt */
            prompt: string;
            /** Reason */
            reason: string | null;
            /** Spans */
            spans: components["schemas"]["SpanReadView"][];
        };
        /** DesignLineView */
        DesignLineView: {
            /** Anchors */
            anchors: {
                [key: string]: components["schemas"]["SourceAnchor"];
            };
            /** Bp Code */
            bp_code: string;
            /** Copper Kg Per Km */
            copper_kg_per_km: string | null;
            /** Line No */
            line_no: number;
            /** Prv Code */
            prv_code: string | null;
            /** Spec No */
            spec_no: string;
        };
        /** DesignReplyView */
        DesignReplyView: {
            /** Attachment Id */
            attachment_id: string;
            /** Lines */
            lines: components["schemas"]["DesignLineView"][];
            /** Message Id */
            message_id: string;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /**
             * Reply Date
             * Format: date
             */
            reply_date: string;
            /** Ycbg No */
            ycbg_no: string;
        };
        /** DispositionBody */
        DispositionBody: {
            /** Case Version */
            case_version: number;
            /**
             * Disposition
             * @enum {string}
             */
            disposition: "open" | "accepted" | "corrected_by_sales" | "ask_customer";
            /** Reason */
            reason?: string | null;
            /** Source */
            source?: string | null;
            /** Value */
            value?: string | null;
        };
        /** DispositionView */
        DispositionView: {
            /** At */
            at?: string | null;
            /** By */
            by?: string | null;
            /** Kind */
            kind: string;
            /** Reason */
            reason?: string | null;
            /** Source */
            source?: string | null;
            value?: components["schemas"]["Words"] | null;
        };
        /**
         * EvidenceView
         * @description What Sales weighs for one line (step 7). Only for `sales.price.read`;
         *     other customers' rows and the reference price only for
         *     `sales.price.other_customers.read` too.
         */
        EvidenceView: {
            /**
             * As Of
             * Format: date
             */
            as_of: string;
            copper_usd_per_uom: components["schemas"]["Amount"] | null;
            floor: components["schemas"]["Amount"] | null;
            freight_usd_per_km: components["schemas"]["Amount"] | null;
            /** Line No */
            line_no: number;
            lme: components["schemas"]["LmeView"] | null;
            /** Orders */
            orders: components["schemas"]["OrderedLineView"][];
            /** Other Customers */
            other_customers: components["schemas"]["QuotationRowView"][] | components["schemas"]["Hidden"];
            /** Own History */
            own_history: components["schemas"]["QuotationRowView"][];
            /** Pricing Policy */
            pricing_policy: string;
            /** Prv Code */
            prv_code: string | null;
            /** Reference Price */
            reference_price: components["schemas"]["Amount"] | components["schemas"]["Hidden"] | null;
            target_price: components["schemas"]["Amount"] | null;
        };
        /**
         * ExportRow
         * @description One surveyed step in one month (giờ Việt Nam): how many times DW1
         *     took a case through it, beside the minutes it takes by hand.
         */
        ExportRow: {
            /** Manual Baseline Minutes */
            manual_baseline_minutes: number;
            /** Month */
            month: string;
            /** Step Id */
            step_id: string;
            /** Times */
            times: number;
        };
        /**
         * FindingCode
         * @description The order checks of the spec's findings table, one code each.
         * @enum {string}
         */
        FindingCode: "code_unmapped" | "code_ambiguous" | "price_mismatch" | "currency_mismatch" | "uom_mismatch" | "quotation_missing" | "lme_band_mismatch" | "moq_violation" | "pack_multiple" | "line_total_mismatch" | "value_uncertain" | "customer_unknown" | "duplicate_po" | "requested_date_short_lt" | "missing_noc_esf" | "revised_po" | "revision_without_base" | "customer_temporary" | "sender_unverified" | "legacy_encoding" | "requested_date_missing";
        /**
         * FixedCopper
         * @description The price does not move with copper.
         */
        FixedCopper: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "fixed";
        };
        /**
         * FlaggedValue
         * @description One value read from a flagged region, by the field it fills.
         */
        FlaggedValue: {
            /** Field */
            field: string;
            flag: components["schemas"]["RegionFlag"];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * Handoff
         * @description The pre-filled hand-off stamped on a routed message's disposition.
         *
         *     ``read``: some value was located. ``nothing_located``: the model answered
         *     and code kept nothing of it. ``unavailable``: no usable answer. Either of
         *     the last two is an empty form Sales fills by hand, as before.
         */
        Handoff: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "delivery_change" | "complaint" | "sample_request";
            /**
             * Lines
             * @default []
             */
            lines: components["schemas"]["HandoffLine"][];
            lot?: components["schemas"]["Located"] | null;
            /** Model Profile */
            model_profile: string;
            /** Order Case Id */
            order_case_id?: string | null;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "read" | "unavailable" | "nothing_located";
            po?: components["schemas"]["Located"] | null;
            /** Po No */
            po_no?: string | null;
            /** Prompt */
            prompt: string;
            quantity?: components["schemas"]["Located"] | null;
            /**
             * Quotes
             * @default []
             */
            quotes: components["schemas"]["Located"][];
            /** Refused */
            refused?: {
                [key: string]: number;
            };
            /** Route */
            route: string;
            /** Rules */
            rules: string;
            /** Sample Quantity */
            sample_quantity?: string | null;
            /** So No */
            so_no?: string | null;
        };
        /**
         * HandoffDraftView
         * @description A routed message's hand-off as code wrote it from the template, for
         *     Sales to review, edit and send from their own mailbox (ticket 33). ``to``
         *     names the team, never an address: Sales picks the recipients.
         */
        HandoffDraftView: {
            /** Body */
            body: string;
            /** Subject */
            subject: string;
            /** Template Ref */
            template_ref: string;
            /**
             * To
             * @enum {string}
             */
            to: "pc" | "qa";
        };
        /**
         * HandoffLine
         * @description A line of the order the customer asks to change, resolved by code.
         */
        HandoffLine: {
            date_span?: components["schemas"]["Located"] | null;
            /** Item */
            item?: string | null;
            /** Line No */
            line_no: number;
            /** New Date */
            new_date?: string | null;
            /** New Quantity */
            new_quantity?: string | null;
            quantity?: components["schemas"]["Located"] | null;
            reference: components["schemas"]["Located"];
        };
        /**
         * Hidden
         * @description An amount the caller may not see: there, and not shown.
         */
        Hidden: {
            /**
             * Hidden
             * @default true
             * @constant
             */
            hidden: true;
        };
        /** InboxMessageView */
        InboxMessageView: {
            /** Attachments */
            attachments: components["schemas"]["AttachmentView"][];
            /** Body Text */
            body_text: string;
            disposition: components["schemas"]["MessageDispositionView"];
            handoff_draft?: components["schemas"]["HandoffDraftView"] | null;
            /** Message Id */
            message_id: string;
            processing?: components["schemas"]["ProcessingJobView"] | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Sender */
            sender: string;
            /** Sender Name */
            sender_name: string;
            /** Sender Verified */
            sender_verified: boolean;
            /** Subject */
            subject: string;
        };
        /**
         * IntentReading
         * @description What the model reading of a message's intent did, stamped on its
         *     disposition: the prompt, profile and route of the call, the rules whose
         *     switch asked for it, and the outcome. ``unavailable``: no usable answer
         *     within the retry window, so the message went to Sales as `other`.
         */
        IntentReading: {
            /** Kind */
            kind?: ("po" | "quote_request" | "design_reply" | "reply_to_case" | "delivery_change" | "complaint" | "sample_request" | "other") | null;
            /** Language */
            language?: ("vi" | "en" | "ja" | "other") | null;
            /** Model Profile */
            model_profile: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "read" | "unavailable";
            /** Prompt */
            prompt: string;
            /**
             * References
             * @default []
             */
            references: components["schemas"]["ResolvedReference"][];
            /** Route */
            route: string;
            /** Rules */
            rules: string;
        };
        /** ItemBasisView */
        ItemBasisView: {
            /** Moq */
            moq: string;
            /** Pack Multiple */
            pack_multiple: string;
            /** Prv Code */
            prv_code: string;
            /** Standard Lead Time Days */
            standard_lead_time_days: number;
            /** Uom */
            uom: string | null;
        };
        /** ItemView */
        ItemView: {
            /** Cores */
            cores: number;
            /** Family */
            family: string | null;
            /** Gauge */
            gauge: string;
            /** Moq */
            moq: string;
            /** Pack Multiple */
            pack_multiple: string;
            /** Prv Code */
            prv_code: string;
            /** Spec No */
            spec_no: string;
            /** Standard Lead Time Days */
            standard_lead_time_days: number;
            /** Uom */
            uom: string | null;
        };
        /** LabelCellView */
        LabelCellView: {
            /** Column */
            column: number;
            /** Ref */
            ref: string;
            /** Row */
            row: number;
            /** Sheet */
            sheet: string;
            /** Text */
            text: string;
        };
        /**
         * LabelledAnchor
         * @description Where one value was read, named by the field (and line) it fills.
         */
        LabelledAnchor: {
            anchor: components["schemas"]["SourceAnchor"];
            /** Field */
            field: string;
            /** Line No */
            line_no?: number | null;
        };
        /**
         * LayoutBody
         * @description A mapping of the form one message's attachment prints (ticket 30).
         */
        LayoutBody: {
            /** Attachment Id */
            attachment_id: string;
            mapping: components["schemas"]["LayoutMapping"];
            /** Message Id */
            message_id: string;
        };
        /**
         * LayoutMapping
         * @description Which label on the form names each value, and how its numbers and text
         *     dates are written. A person maps it on the onboarding screen; a model may
         *     pre-fill it.
         */
        LayoutMapping: {
            /** Amount */
            amount: string;
            /** Currency */
            currency: string;
            /** Customer Item Code */
            customer_item_code: string;
            /**
             * Date Format
             * @default %d/%m/%Y
             * @enum {string}
             */
            date_format: "%d/%m/%Y" | "%Y-%m-%d" | "%d-%m-%Y" | "%m/%d/%Y" | "%d.%m.%Y" | "%Y/%m/%d";
            /**
             * Decimal Separator
             * @default .
             * @enum {string}
             */
            decimal_separator: "." | ",";
            /** Description */
            description: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "excel" | "pdf";
            /** Line No */
            line_no: string;
            /** Page Label */
            page_label?: string | null;
            /** Pdf Columns */
            pdf_columns?: string[] | null;
            /** Po Date */
            po_date: string;
            /** Po No */
            po_no: string;
            /** Quantity */
            quantity: string;
            /** Requested Date */
            requested_date: string;
            /** Revision */
            revision?: string | null;
            /**
             * Thousands Separator
             * @default ,
             * @enum {string}
             */
            thousands_separator: "," | "." | " " | "none";
            /** Total Label */
            total_label: string;
            /** Unit Price */
            unit_price: string;
            /** Uom */
            uom: string;
        };
        /**
         * LayoutPrefill
         * @description What the model pre-fill of a form did, stamped on the message it was
         *     asked for and on the layout a person proposed from it: the prompt,
         *     profile and route of the call, the rules whose switch asked, and the
         *     outcome. ``proposed``: every check passed and the screen opens with the
         *     mapping; ``refused``: a check failed (the problems say which), and the
         *     screen opens empty; ``unavailable``: no usable answer.
         */
        LayoutPrefill: {
            /** Attachment Id */
            attachment_id: string;
            mapping?: components["schemas"]["LayoutMapping"] | null;
            /** Model Profile */
            model_profile: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "proposed" | "refused" | "unavailable";
            /**
             * Problems
             * @default []
             */
            problems: string[];
            /** Prompt */
            prompt: string;
            /** Route */
            route: string;
            /** Rules */
            rules: string;
        };
        /**
         * LayoutPreviewView
         * @description A mapping as code judged it: the problems, and what the reader read.
         */
        LayoutPreviewView: {
            /** Currency */
            currency?: string | null;
            /**
             * Lines
             * @default []
             */
            lines: components["schemas"]["PreviewLineView"][];
            /** Ok */
            ok: boolean;
            /** Po Date */
            po_date?: string | null;
            /** Po No */
            po_no?: string | null;
            /** Problems */
            problems: string[];
            /** Revision */
            revision?: number | null;
            /** Total */
            total?: string | null;
        };
        /**
         * LayoutSample
         * @description The PO the form was mapped from: what the approver sees beside it.
         */
        LayoutSample: {
            /** Attachment Id */
            attachment_id: string;
            /** Attachment Sha256 */
            attachment_sha256: string;
            /** Message Id */
            message_id: string;
        };
        /**
         * LayoutSourceView
         * @description What the onboarding screen maps from: the form's cells, the pre-fill
         *     DW1 stamped on the message (a model's, where the step is on), and the
         *     customer's layout of this kind already approved, if any.
         */
        LayoutSourceView: {
            approved: components["schemas"]["LayoutView"] | null;
            /** Attachment Id */
            attachment_id: string;
            /** Cells */
            cells: components["schemas"]["LabelCellView"][];
            /** Customer Code */
            customer_code: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "excel" | "pdf";
            /** Message Id */
            message_id: string;
            prefill: components["schemas"]["LayoutPrefill"] | null;
        };
        /**
         * LayoutView
         * @description One layout: its mapping, the PO it was mapped from, who proposed and
         *     who decided it, and the model pre-fill it started from, if any.
         */
        LayoutView: {
            /**
             * Approval Id
             * Format: uuid
             */
            approval_id: string;
            /** Customer Code */
            customer_code: string;
            /** Decided At */
            decided_at: string | null;
            /** Decided By */
            decided_by: string | null;
            /** Kind */
            kind: string;
            /**
             * Layout Id
             * Format: uuid
             */
            layout_id: string;
            mapping: components["schemas"]["LayoutMapping"];
            prefill: components["schemas"]["LayoutPrefill"] | null;
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
            sample: components["schemas"]["LayoutSample"];
            /** Status */
            status: string;
            /** Version */
            version: number;
        };
        /** LineBasisView */
        LineBasisView: {
            /** Candidates */
            candidates: string[];
            /** Checks Run */
            checks_run: string[];
            /** Convert Prv Code */
            convert_prv_code: string | null;
            description_reading: components["schemas"]["DescriptionReadingView"] | null;
            item: components["schemas"]["ItemBasisView"] | null;
            /** Lead Time Days */
            lead_time_days: number | null;
            /** Lead Time Source */
            lead_time_source: string | null;
            lme: components["schemas"]["LmeView"] | null;
            quotation: components["schemas"]["QuotationBasisView"] | null;
            stated_attributes: components["schemas"]["StatedAttributesView"] | null;
        };
        /** LineChangeView */
        LineChangeView: {
            after: components["schemas"]["Words"] | null;
            before: components["schemas"]["Words"] | null;
            /** Field */
            field: string;
            /** Line No */
            line_no: number;
        };
        /**
         * LineDate
         * @description The date Sales confirms for a line delivered once, or, for a line the
         *     PO splits over several schedules, one per schedule in their order
         *     (ticket 35): exactly one of the two.
         */
        LineDate: {
            /** Confirmed Date */
            confirmed_date?: string | null;
            /** Line No */
            line_no: number;
            /** Schedule Dates */
            schedule_dates?: string[] | null;
        };
        /**
         * LmeBand
         * @description The price holds while LME copper is in ``[low, high)`` USD per tonne.
         */
        LmeBand: {
            /** High Usd Per Tonne */
            high_usd_per_tonne: number | string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "lme_band";
            /** Low Usd Per Tonne */
            low_usd_per_tonne: number | string;
        };
        /** LmeView */
        LmeView: {
            /** Month */
            month: string;
            usd_per_tonne: components["schemas"]["Amount"] | null;
        };
        /**
         * Located
         * @description Text code found exactly once in the newest part, with its offsets
         *     into the NFKC form of `MessagePart.text`.
         */
        Located: {
            /** End */
            end: number;
            /** Start */
            start: number;
            /** Text */
            text: string;
        };
        /** MappingBody */
        MappingBody: {
            /** Case Version */
            case_version: number;
            /** Prv Code */
            prv_code: string;
        };
        /** MappingCounts */
        MappingCounts: {
            /** Confirmed Candidate */
            confirmed_candidate: number;
            /** Convert List */
            convert_list: number;
            /** Unresolved */
            unresolved: number;
        };
        /** MappingView */
        MappingView: {
            /** Candidates */
            candidates: string[];
            /** Confirmed At */
            confirmed_at: string | null;
            /** Confirmed By */
            confirmed_by: string | null;
            /** Hand Entered */
            hand_entered: boolean;
            /** Prv Code */
            prv_code: string | null;
            /** Status */
            status: string;
        };
        /** MasterDataView[BravoOrderView] */
        MasterDataView_BravoOrderView_: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Items */
            items: components["schemas"]["BravoOrderView"][];
        };
        /** MasterDataView[ConvertEntryView] */
        MasterDataView_ConvertEntryView_: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Items */
            items: components["schemas"]["ConvertEntryView"][];
        };
        /** MasterDataView[CustomerView] */
        MasterDataView_CustomerView_: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Items */
            items: components["schemas"]["CustomerView"][];
        };
        /** MasterDataView[ItemView] */
        MasterDataView_ItemView_: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Items */
            items: components["schemas"]["ItemView"][];
        };
        /** MasterDataView[LmeView] */
        MasterDataView_LmeView_: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Items */
            items: components["schemas"]["LmeView"][];
        };
        /** MasterDataView[OpenYcbgView] */
        MasterDataView_OpenYcbgView_: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Items */
            items: components["schemas"]["OpenYcbgView"][];
        };
        /** MasterDataView[QuotationRowView] */
        MasterDataView_QuotationRowView_: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Items */
            items: components["schemas"]["QuotationRowView"][];
        };
        /** MessageDispositionView */
        MessageDispositionView: {
            /** Case Id */
            case_id?: string | null;
            case_kind?: components["schemas"]["CaseKind"] | null;
            /** Customer Code */
            customer_code?: string | null;
            /** Detail */
            detail?: string | null;
            handoff?: components["schemas"]["Handoff"] | null;
            /** Kind */
            kind: string;
            layout_prefill?: components["schemas"]["LayoutPrefill"] | null;
            /** Owner */
            owner?: string | null;
            /** Processed At */
            processed_at?: string | null;
            reading?: components["schemas"]["IntentReading"] | null;
            /** Reason */
            reason?: string | null;
            reply?: components["schemas"]["CaseReply"] | null;
        };
        /**
         * MessageTextView
         * @description The message's newest part a model read a quotation from, as the case
         *     holds it: what its values' ``chars`` index into. It may state a price.
         */
        MessageTextView: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            /**
             * Served At
             * Format: date-time
             */
            served_at: string;
            /** Sha256 */
            sha256: string;
            /** Text */
            text: string;
        };
        /** MessagesView */
        MessagesView: {
            /** Oldest Waiting Seconds */
            oldest_waiting_seconds: number | null;
            /** Routed To Sales */
            routed_to_sales: number;
            /** Routed Without Owner */
            routed_without_owner: number;
            /** Total */
            total: number;
            /** Without Disposition */
            without_disposition: number;
        };
        /** OpenYcbgView */
        OpenYcbgView: {
            /** Customer Code */
            customer_code: string;
            /**
             * Issued On
             * Format: date
             */
            issued_on: string;
            /** Rfq No */
            rfq_no: string;
            /** Ycbg No */
            ycbg_no: string;
        };
        /** OrderCaseView */
        OrderCaseView: {
            /** Assigned To */
            assigned_to: string | null;
            /** Attachment Id */
            attachment_id: string;
            /** Attachment Sha256 */
            attachment_sha256: string;
            /** Base So No */
            base_so_no: string | null;
            /** Bravo Entry Compared */
            bravo_entry_compared: boolean;
            /** Bravo Recorded At */
            bravo_recorded_at: string | null;
            /** Bravo Recorded By */
            bravo_recorded_by: string | null;
            /** Bravo So No */
            bravo_so_no: string | null;
            /** Buyer */
            buyer: string | null;
            buyer_anchor: components["schemas"]["SourceAnchor"] | null;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            /** Catalog As Of */
            catalog_as_of: string | null;
            /** Changes */
            changes: components["schemas"]["LineChangeView"][];
            /** Close Reason */
            close_reason: string | null;
            /** Closed At */
            closed_at: string | null;
            /** Closed By */
            closed_by: string | null;
            /** Confirmed At */
            confirmed_at: string | null;
            /** Confirmed By */
            confirmed_by: string | null;
            coverage: components["schemas"]["CoverageView"];
            /** Cross Check Required */
            cross_check_required: boolean | null;
            /** Cross Check Stalled */
            cross_check_stalled: boolean;
            /** Cross Checked At */
            cross_checked_at: string | null;
            /** Cross Checked By */
            cross_checked_by: string | null;
            /**
             * Currency
             * @enum {string}
             */
            currency: "USD" | "VND" | "JPY";
            /** Customer Code */
            customer_code: string;
            decision?: components["schemas"]["PendingDecisionView"] | null;
            derivation?: components["schemas"]["Derivation"] | null;
            /** Duplicate Of Case */
            duplicate_of_case: string | null;
            /** Duplicate Of So */
            duplicate_of_so: string | null;
            /** Export Control Mode */
            export_control_mode: string | null;
            /** Findings */
            findings: components["schemas"]["OrderFindingView"][];
            /** Header Anchors */
            header_anchors: {
                [key: string]: components["schemas"]["SourceAnchor"];
            };
            /** Header Corrections */
            header_corrections: components["schemas"]["ValueCorrectionView"][];
            /** Header Flags */
            header_flags: components["schemas"]["FlaggedValue"][];
            legacy_text_anchor: components["schemas"]["SourceAnchor"] | null;
            /** Lines */
            lines: components["schemas"]["OrderLineView"][];
            /** Makers */
            makers: string[];
            /** Message Id */
            message_id: string;
            /** Parser Version */
            parser_version: string;
            /**
             * Po Date
             * Format: date
             */
            po_date: string;
            /** Po No */
            po_no: string;
            /** Prepared At */
            prepared_at: string | null;
            /** Prepared By */
            prepared_by: string | null;
            print_copy: components["schemas"]["PrintCopyView"] | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Release Manifest Ref */
            release_manifest_ref: string | null;
            /**
             * Replies
             * @default []
             */
            replies: components["schemas"]["CaseReplyView"][];
            /** Returned At */
            returned_at: string | null;
            /** Returned By */
            returned_by: string | null;
            /** Returned Reason */
            returned_reason: string | null;
            /** Revision */
            revision: number;
            /** Rules Version */
            rules_version: string | null;
            /** Status */
            status: string;
            /** Superseded */
            superseded: components["schemas"]["SupersededView"][];
            /** Superseded By Case */
            superseded_by_case: string | null;
            total: components["schemas"]["Amount"] | null;
            total_anchor: components["schemas"]["SourceAnchor"] | null;
            unapplied_decision: components["schemas"]["UnappliedDecisionView"] | null;
        };
        /** OrderFindingView */
        OrderFindingView: {
            actual: components["schemas"]["Words"] | null;
            /** Allowed */
            allowed: string[];
            /** Blocking */
            blocking: boolean;
            code: components["schemas"]["FindingCode"];
            disposition: components["schemas"]["DispositionView"];
            expected: components["schemas"]["Words"] | null;
            /** Fields */
            fields: string[];
            /** Key */
            key: string;
            /** Line No */
            line_no: number | null;
            /** Rule Version */
            rule_version: string;
            /** Severity */
            severity: string;
        };
        /** OrderLineView */
        OrderLineView: {
            amount: components["schemas"]["Amount"];
            /** Anchors */
            anchors: {
                [key: string]: components["schemas"]["SourceAnchor"];
            };
            basis: components["schemas"]["LineBasisView"];
            /** Confirmed Delivery Date */
            confirmed_delivery_date: string | null;
            /** Corrections */
            corrections: components["schemas"]["ValueCorrectionView"][];
            /** Customer Item Code */
            customer_item_code: string;
            /** Description */
            description: string;
            /** Flags */
            flags: components["schemas"]["FlaggedValue"][];
            /** Line No */
            line_no: number;
            mapping: components["schemas"]["MappingView"];
            /** Pc Confirmed At */
            pc_confirmed_at: string | null;
            /** Pc Confirmed By */
            pc_confirmed_by: string | null;
            /** Printed Schedules */
            printed_schedules: boolean;
            /** Quantity */
            quantity: string;
            /** Requested Date */
            requested_date: string | null;
            /** Schedules */
            schedules: components["schemas"]["DeliveryScheduleView"][];
            /** Suggested Delivery Date */
            suggested_delivery_date: string | null;
            unit_price: components["schemas"]["Amount"];
            /** Uom */
            uom: string;
            /** Value States */
            value_states: {
                [key: string]: components["schemas"]["ValueState"];
            };
        };
        /**
         * OrderSummaryView
         * @description A row of the order list: no amount at all.
         */
        OrderSummaryView: {
            /** Assigned To */
            assigned_to: string | null;
            /** Awaits Cross Check */
            awaits_cross_check: boolean;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            /** Customer Code */
            customer_code: string;
            /** Lines */
            lines: number;
            /** Open Blocking Findings */
            open_blocking_findings: number;
            /** Open Findings */
            open_findings: number;
            /** Po No */
            po_no: string;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Revision */
            revision: number;
            /** Status */
            status: string;
        };
        /** OrderedLineView */
        OrderedLineView: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "USD" | "VND" | "JPY";
            /**
             * Order Date
             * Format: date
             */
            order_date: string;
            /** Quantity */
            quantity: string;
            /** So No */
            so_no: string;
            unit_price: components["schemas"]["Amount"];
        };
        /** OverviewView */
        OverviewView: {
            /** A3 Shadow */
            a3_shadow: number;
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Export */
            export: components["schemas"]["ExportRow"][];
            /** Findings By Code */
            findings_by_code: {
                [key: string]: number;
            };
            /** Kpi Policy */
            kpi_policy: string;
            /** Lines Printed */
            lines_printed: number;
            /** Lines Read */
            lines_read: number;
            mapping: components["schemas"]["MappingCounts"];
            messages: components["schemas"]["MessagesView"];
            order_confirmation: components["schemas"]["TargetView"];
            /** Orders Prepared Without Correction */
            orders_prepared_without_correction: number;
            quotation_time: components["schemas"]["TargetView"];
            /** Quotes Sent As First Drafted */
            quotes_sent_as_first_drafted: number;
            /** Steps */
            steps: components["schemas"]["StepCount"][];
            times: components["schemas"]["TimesView"];
            worker: components["schemas"]["WorkerStateView"];
        };
        /**
         * PageBox
         * @description A rectangle on a rendered page, as fractions of the page.
         *
         *     ``x`` and ``y`` are the top-left corner measured from the page's top-left,
         *     so the box draws the same at any zoom and on any renderer.
         */
        PageBox: {
            /** H */
            h: number;
            /** W */
            w: number;
            /** X */
            x: number;
            /** Y */
            y: number;
        };
        /**
         * Page
         * @description A page of results and the cursor that continues it.
         *
         *     ``next_cursor`` is ``None`` on the last page, and that — not an empty
         *     ``items`` — is the client's stop condition: a filtered listing can return an
         *     empty page in the middle of a run and still have more rows behind it.
         */
        Page_WorkItem_: {
            /** Items */
            items: components["schemas"]["WorkItem"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** PauseBody */
        PauseBody: {
            /** Reason */
            reason?: string | null;
        };
        /**
         * PendingDecisionView
         * @description The platform approval a case waits on: the decision is made there
         *     (`POST /api/v1/approvals/{approval_id}/decisions`), never on a Sales
         *     route. Present only while the case is in the state that waits on it.
         */
        PendingDecisionView: {
            /**
             * Approval Id
             * Format: uuid
             */
            approval_id: string;
            /** Approval Type */
            approval_type: string;
        };
        /**
         * PlatformDocumentView
         * @description One version of a key the platform released, whole: what a proposal may
         *     start from and what a diff compares with while the platform's applies.
         */
        PlatformDocumentView: {
            /** Current */
            current: boolean;
            /** Document */
            document: {
                [key: string]: unknown;
            };
            key: components["schemas"]["RuleKey"];
            /** Ref */
            ref: string;
            /** Version */
            version: string;
        };
        /** PlatformRuleView */
        PlatformRuleView: {
            key: components["schemas"]["RuleKey"];
            /** Ref */
            ref: string;
        };
        /** PreviewLineView */
        PreviewLineView: {
            /** Amount */
            amount: string;
            /** Customer Item Code */
            customer_item_code: string;
            /** Description */
            description: string;
            /** Line No */
            line_no: number;
            /** Quantity */
            quantity: string;
            /** Requested Date */
            requested_date: string | null;
            /** Unit Price */
            unit_price: string;
            /** Uom */
            uom: string;
        };
        /** PriceBody */
        PriceBody: {
            /** Case Version */
            case_version: number;
            /** Lines */
            lines: components["schemas"]["PriceLineBody"][];
            /** Lme Month */
            lme_month?: string | null;
            /** Management Guidance */
            management_guidance?: string | null;
        };
        /** PriceLineBody */
        PriceLineBody: {
            /** Copper Basis */
            copper_basis: components["schemas"]["FixedCopper"] | components["schemas"]["LmeBand"];
            /** Lead Time Days */
            lead_time_days: number;
            /** Line No */
            line_no: number;
            /** Moq */
            moq: number | string;
            /** Unit Price */
            unit_price: number | string;
        };
        /** PricedLineView */
        PricedLineView: {
            copper_basis: components["schemas"]["CopperBasisView"];
            /** Lead Time Days */
            lead_time_days: number;
            /** Line No */
            line_no: number;
            /** Moq */
            moq: string;
            unit_price: components["schemas"]["Amount"];
        };
        /** PricingView */
        PricingView: {
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
            /** Lines */
            lines: components["schemas"]["PricedLineView"][];
            lme: components["schemas"]["LmeView"] | null;
            management_guidance: components["schemas"]["Words"] | null;
        };
        /** PrintCopyView */
        PrintCopyView: {
            /** Attachment Id */
            attachment_id: string;
            /** Differences */
            differences: components["schemas"]["PrintDifferenceView"][];
        };
        /**
         * PrintDifferenceView
         * @description A value the PDF print shows differently, and where it shows it.
         */
        PrintDifferenceView: {
            anchor: components["schemas"]["SourceAnchor"];
            /** Field */
            field: string;
            /** Line No */
            line_no: number | null;
        };
        /**
         * ProcessingJobView
         * @description A message's processing job (ticket 25): ids, a status and a reason
         *     code, never anything read from the message.
         */
        ProcessingJobView: {
            /** Attempts */
            attempts: number;
            /** Error */
            error: ("quota" | "not_permitted" | "paused" | "conflict" | "not_found" | "unavailable" | "model_retry" | "abandoned" | "error") | null;
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /** Message Id */
            message_id: string;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "running" | "done" | "failed";
        };
        /**
         * ProcessingQueuedView
         * @description What "DW xử lý tất cả" queued (ticket 25): one job per message.
         */
        ProcessingQueuedView: {
            /** Jobs */
            jobs: components["schemas"]["ProcessingJobView"][];
        };
        /** QuotationBasisView */
        QuotationBasisView: {
            copper_basis: components["schemas"]["CopperBasisView"];
            /**
             * Currency
             * @enum {string}
             */
            currency: "USD" | "VND" | "JPY";
            /** Lead Time Days */
            lead_time_days: number;
            /** Moq */
            moq: string;
            /** Quote No */
            quote_no: string;
            unit_price: components["schemas"]["Amount"];
            /** Uom */
            uom: string | null;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /**
             * Valid To
             * Format: date
             */
            valid_to: string;
        };
        /**
         * QuotationRowView
         * @description A quotation in the evidence or the master data.
         */
        QuotationRowView: {
            copper_basis: components["schemas"]["CopperBasisView"];
            /**
             * Currency
             * @enum {string}
             */
            currency: "USD" | "VND" | "JPY";
            /** Customer Code */
            customer_code: string;
            /** Lead Time Days */
            lead_time_days: number;
            /** Moq */
            moq: string;
            /** Prv Code */
            prv_code: string;
            /** Quote No */
            quote_no: string;
            unit_price: components["schemas"]["Amount"];
            /** Uom */
            uom: string | null;
            /**
             * Valid From
             * Format: date
             */
            valid_from: string;
            /**
             * Valid To
             * Format: date
             */
            valid_to: string;
        };
        /** QuoteApprovalView */
        QuoteApprovalView: {
            /**
             * Approved At
             * Format: date-time
             */
            approved_at: string;
            /**
             * Approved By
             * Format: uuid
             */
            approved_by: string;
            /** Case Version */
            case_version: number;
            /** Document Sha256 */
            document_sha256: string;
        };
        /** QuoteCaseView */
        QuoteCaseView: {
            /**
             * Anchors
             * @default {}
             */
            anchors: {
                [key: string]: components["schemas"]["SourceAnchor"];
            };
            approval: components["schemas"]["QuoteApprovalView"] | null;
            /** Assigned To */
            assigned_to: string | null;
            /** Attachment Id */
            attachment_id: string | null;
            /** Attachment Sha256 */
            attachment_sha256: string | null;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            /**
             * Catalog As Of
             * Format: date-time
             */
            catalog_as_of: string;
            /**
             * Currency
             * @enum {string}
             */
            currency: "USD" | "VND" | "JPY";
            /** Customer Code */
            customer_code: string;
            /** Customer From */
            customer_from: string;
            decision?: components["schemas"]["PendingDecisionView"] | null;
            decline: components["schemas"]["DeclineView"] | null;
            /** Design Replies */
            design_replies: number;
            design_reply: components["schemas"]["DesignReplyView"] | null;
            /** Earlier Pricing */
            earlier_pricing: number;
            /** Evidence */
            evidence: components["schemas"]["EvidenceView"][] | components["schemas"]["Hidden"] | null;
            /** Findings */
            findings: components["schemas"]["QuoteFindingView"][];
            /** Lines */
            lines: components["schemas"]["QuoteLineView"][];
            master_list: components["schemas"]["StampView"] | null;
            /** Message Id */
            message_id: string;
            /**
             * Model Read
             * @default []
             */
            model_read: string[];
            /** Overdue */
            overdue: boolean;
            /** Parser Version */
            parser_version: string;
            pricing: components["schemas"]["PricingView"] | null;
            /** Quote Due */
            quote_due: string | null;
            reading?: components["schemas"]["RequestReading"] | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Release Manifest Ref */
            release_manifest_ref: string | null;
            /**
             * Replies
             * @default []
             */
            replies: components["schemas"]["CaseReplyView"][];
            /** Returns */
            returns: components["schemas"]["ReturnView"][];
            /** Rfq Date */
            rfq_date: string | null;
            /** Rfq No */
            rfq_no: string | null;
            /** Rules Version */
            rules_version: string;
            /** Sender */
            sender: string;
            sent: components["schemas"]["StampView"] | null;
            /** Status */
            status: string;
            submission: components["schemas"]["SubmissionView"] | null;
            /** Ycbg No */
            ycbg_no: string | null;
            /** Ycbg Recorded At */
            ycbg_recorded_at: string | null;
            /** Ycbg Recorded By */
            ycbg_recorded_by: string | null;
        };
        /** QuoteDispositionView */
        QuoteDispositionView: {
            /** At */
            at?: string | null;
            /** By */
            by?: string | null;
            /** Customer Code */
            customer_code?: string | null;
            /** Kind */
            kind: string;
            /** Needed By */
            needed_by?: string | null;
            /** Note */
            note?: string | null;
            /** Quantity */
            quantity?: string | null;
            /** Reason */
            reason?: string | null;
        };
        /** QuoteFindingView */
        QuoteFindingView: {
            actual: components["schemas"]["Words"] | null;
            /** Blocking */
            blocking: boolean;
            /** Code */
            code: string;
            /**
             * Confirmed
             * @default []
             */
            confirmed: components["schemas"]["ValueConfirmationView"][];
            disposition: components["schemas"]["QuoteDispositionView"];
            expected: components["schemas"]["Words"] | null;
            /**
             * Flagged
             * @default []
             */
            flagged: string[];
            /** Key */
            key: string;
            /** Line No */
            line_no: number | null;
            /** Missing */
            missing: string[];
            /** Rule Versions */
            rule_versions: string[];
        };
        /** QuoteLineView */
        QuoteLineView: {
            /** Anchors */
            anchors: {
                [key: string]: components["schemas"]["SourceAnchor"];
            };
            /**
             * Candidates
             * @default []
             */
            candidates: string[];
            /** Customer Item Code */
            customer_item_code: string | null;
            /** Description */
            description: string;
            description_reading?: components["schemas"]["DescriptionReading"] | null;
            /** Line No */
            line_no: number;
            /**
             * Model Read
             * @default []
             */
            model_read: string[];
            /** Needed By */
            needed_by: string | null;
            /** Quantity */
            quantity: string | null;
            stated_target_price?: components["schemas"]["Amount"] | null;
            target_price: components["schemas"]["Amount"] | null;
            /** Uom */
            uom: string;
        };
        /** QuoteSummaryView */
        QuoteSummaryView: {
            /** Assigned To */
            assigned_to: string | null;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            /** Customer Code */
            customer_code: string;
            /** Open Findings */
            open_findings: number;
            /** Overdue */
            overdue: boolean;
            /** Quote Due */
            quote_due: string | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Rfq No */
            rfq_no: string | null;
            /** Status */
            status: string;
            /** Ycbg No */
            ycbg_no: string | null;
        };
        /**
         * RegionFlag
         * @description Why a value read from a file is not taken on trust (`value_uncertain`).
         *
         *     Each is a place a person looking at the file would not see the value, or
         *     would see something else than the reader read.
         * @enum {string}
         */
        RegionFlag: "hidden_sheet" | "hidden_row" | "hidden_column" | "font_matches_fill" | "formula_without_cached_value" | "model_read" | "new_layout" | "print_differs" | "ocr";
        /**
         * RenderBody
         * @description An artifact kind to render from the case at the version the caller saw;
         *     which kinds are open now is `GET .../artifacts`'s ``available``.
         */
        RenderBody: {
            /** Case Version */
            case_version: number;
            /** Kind */
            kind: string;
        };
        /**
         * RenderedView
         * @description The files one render stored: ids, template, version and hash only.
         */
        RenderedView: {
            /** Artifacts */
            artifacts: components["schemas"]["ArtifactView"][];
        };
        /**
         * ReplyQuote
         * @description A sentence of the reply that code found, once, in its newest part:
         *     the text as the customer wrote it and where it is (offsets into the NFKC
         *     form of `MessagePart.text`).
         */
        ReplyQuote: {
            /** End */
            end: number;
            /** Start */
            start: number;
            /** Text */
            text: string;
        };
        /**
         * ReplyReading
         * @description What the model reading of a reply did, stamped on its disposition: the
         *     prompt, profile and route of the call, the rules whose switch asked for
         *     it, and the outcome. ``unavailable``: no usable answer, so the reply is on
         *     its case with no proposal and Sales reads it.
         */
        ReplyReading: {
            /** Kind */
            kind?: ("accepts_spec" | "rejects_spec" | "counter_proposal" | "sends_corrected_po" | "keeps_po_as_is" | "question" | "unclear") | null;
            /** Model Profile */
            model_profile: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "read" | "unavailable";
            /** Prompt */
            prompt: string;
            /**
             * Quotes
             * @default []
             */
            quotes: components["schemas"]["ReplyQuote"][];
            /** Route */
            route: string;
            /** Rules */
            rules: string;
        };
        /**
         * RequestReading
         * @description How a model read the request (ticket 29): the prompt, profile and route
         *     of the calls, the rules whose switch asked, and how many calls it took.
         */
        RequestReading: {
            /** Calls */
            calls: number;
            /** Model Profile */
            model_profile: string;
            /** Prompt */
            prompt: string;
            /** Refused */
            refused?: {
                [key: string]: number;
            };
            /** Route */
            route: string;
            /** Rules */
            rules: string;
        };
        /**
         * ResolvedReference
         * @description A number the message names that code found in it and resolved to
         *     exactly one record of the sender's customer.
         */
        ResolvedReference: {
            /** Number */
            number: string;
            /** Order Case Id */
            order_case_id?: string | null;
            /**
             * Record
             * @enum {string}
             */
            record: "purchase_order" | "quote_request";
        };
        /** ResumeBody */
        ResumeBody: {
            /** Reason */
            reason: string;
        };
        /** ReturnView */
        ReturnView: {
            /** Case Version */
            case_version: number;
            /** Reason */
            reason: string;
            /**
             * Returned At
             * Format: date-time
             */
            returned_at: string;
            /**
             * Returned By
             * Format: uuid
             */
            returned_by: string;
        };
        /**
         * RuleKey
         * @description The Sales policies and copy a tenant may hold its own version of.
         * @enum {string}
         */
        RuleKey: "sales_order_rules" | "sales_kpi" | "sales_quote_rules" | "sales_pricing" | "sales_emails" | "sales_documents" | "sales_bravo_upload" | "sales_handoffs";
        /**
         * RuleProposalBody
         * @description A whole policy document for one key, validated by that key's schema.
         */
        RuleProposalBody: {
            /** Document */
            document: {
                [key: string]: unknown;
            };
        };
        /**
         * RuleSchemaView
         * @description What the rules editor draws one key's form from: the JSON Schema a
         *     proposal of it is validated by (ticket 40). The schema is the key's own
         *     model's, never a copy, so a field added to the model reaches the form.
         */
        RuleSchemaView: {
            /** Json Schema */
            json_schema: {
                [key: string]: unknown;
            };
            key: components["schemas"]["RuleKey"];
        };
        /**
         * RuleVersionView
         * @description A version as the rules list shows it: who proposed and decided it, and
         *     the document only to whoever may propose (it can hold price rules).
         */
        RuleVersionView: {
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
            key: components["schemas"]["RuleKey"];
            /**
             * Layer
             * @enum {string}
             */
            layer: "platform" | "tenant";
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
            /** Ref */
            ref: string;
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
         * RulesInForceView
         * @description What applies to the tenant now, per key, and every version it holds.
         */
        RulesInForceView: {
            /** In Force */
            in_force: {
                [key: string]: string;
            };
            /** Layers */
            layers: {
                [key: string]: "platform" | "tenant";
            };
            /** Platform */
            platform: components["schemas"]["PlatformRuleView"][];
            /** Versions */
            versions: components["schemas"]["RuleVersionView"][];
        };
        /**
         * ScreeningRow
         * @description One customer's item quoted to them with no order of it in the window
         *     (WIV-03-023 step 12): for Sales to decide whether the quotation stays.
         */
        ScreeningRow: {
            /** Customer Code */
            customer_code: string;
            /** Prv Code */
            prv_code: string;
            /** Quote Nos */
            quote_nos: string[];
        };
        /**
         * SheetCell
         * @description One cell as the workbook holds it, with why a person might not see it.
         */
        SheetCell: {
            /** Column */
            column: number;
            /** Fill Rgb */
            fill_rgb?: string | null;
            /**
             * Font Matches Fill
             * @default false
             */
            font_matches_fill: boolean;
            /** Font Rgb */
            font_rgb?: string | null;
            /**
             * Formula Without Cached Value
             * @default false
             */
            formula_without_cached_value: boolean;
            /**
             * Hidden Column
             * @default false
             */
            hidden_column: boolean;
            /**
             * Hidden Row
             * @default false
             */
            hidden_row: boolean;
            /** Ref */
            ref: string;
            /** Row */
            row: number;
            /** Text */
            text: string;
        };
        /** SheetGrid */
        SheetGrid: {
            /** Cells */
            cells: components["schemas"]["SheetCell"][];
            /** Columns */
            columns: number;
            /** Hidden Sheet */
            hidden_sheet: boolean;
            /** Rows */
            rows: number;
            /** Sheet */
            sheet: string;
            /** Truncated */
            truncated: boolean;
        };
        /**
         * SourceAnchor
         * @description The place in one attachment, or in the message's own text, a value was
         *     read from.
         *
         *     At least one of: ``cell_ref`` (``Sheet!B10``), ``page`` (with its
         *     ``boxes`` where the reader knows them), ``quote``, the words as the file
         *     prints them, or ``chars``, where they are in the text DW1 read. More than
         *     one may be given when the reader knows more than one. ``attachment_id``
         *     None points into the message's newest part, by ``chars`` alone.
         */
        SourceAnchor: {
            /** Attachment Id */
            attachment_id: string | null;
            /** Attachment Sha256 */
            attachment_sha256: string;
            /**
             * Boxes
             * @default []
             */
            boxes: components["schemas"]["PageBox"][];
            /** Cell Ref */
            cell_ref?: string | null;
            chars?: components["schemas"]["TextRange"] | null;
            /** Derived Sha256 */
            derived_sha256?: string | null;
            /** Page */
            page?: number | null;
            /** Quote */
            quote?: string | null;
        };
        /** SourceView */
        SourceView: {
            /** Anchors */
            anchors: components["schemas"]["LabelledAnchor"][];
            /** Attachment Id */
            attachment_id: string;
            /** Attachment Sha256 */
            attachment_sha256: string;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            case_kind: components["schemas"]["CaseKind"];
            /** Case Version */
            case_version: number;
            grid?: components["schemas"]["SheetGrid"] | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "pdf" | "sheet";
            /** Page */
            page?: number | null;
            /** Page Count */
            page_count?: number | null;
            /** Pdf Base64 */
            pdf_base64?: string | null;
            /**
             * Served At
             * Format: date-time
             */
            served_at: string;
            /** Sheet */
            sheet?: string | null;
            /** Sheets */
            sheets?: string[];
        };
        /**
         * SpanRead
         * @description One attribute as code accepted it: the text, where it sits in the
         *     NFKC-normalised description, the value, and who read the value.
         */
        SpanRead: {
            /**
             * Attribute
             * @enum {string}
             */
            attribute: "family" | "stranding" | "conductor" | "shield" | "colour" | "packaging" | "cores" | "gauge" | "pack_length_m" | "spec_no";
            /** End */
            end: number;
            /**
             * Read By
             * @enum {string}
             */
            read_by: "code" | "model";
            /** Span */
            span: string;
            /** Start */
            start: number;
            /** Value */
            value: string;
        };
        /**
         * SpanReadView
         * @description One attribute a model reading located: the text, where it sits in the
         *     normalised description, the value, and whether code parsed the value
         *     (``code``) or it is the model's label (``model``), which Sales checks.
         */
        SpanReadView: {
            /** Attribute */
            attribute: string;
            /** End */
            end: number;
            /**
             * Read By
             * @enum {string}
             */
            read_by: "code" | "model";
            /** Span */
            span: string;
            /** Start */
            start: number;
            /** Value */
            value: string;
        };
        /** SpecBody */
        SpecBody: {
            /** Case Version */
            case_version: number;
            /**
             * Step
             * @enum {string}
             */
            step: "start" | "settle" | "ask_design_again";
        };
        /** StampView */
        StampView: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /**
             * By
             * Format: uuid
             */
            by: string;
        };
        /**
         * StatedAttributesView
         * @description What the description stated of the attributes the candidate picker
         *     compares with each item (`ItemView`), as stamped when the line was
         *     mapped (`LineBasis.stated_attributes`). None: not stated.
         */
        StatedAttributesView: {
            /** Cores */
            cores: number | null;
            /** Family */
            family: string | null;
            /** Gauge */
            gauge: string | null;
            /** Spec No */
            spec_no: string | null;
        };
        /** StepCount */
        StepCount: {
            /** Cases */
            cases: number;
            /** Coverage */
            coverage: string;
            /** Procedure */
            procedure: string;
            /** States */
            states: string[];
            /** Step Id */
            step_id: string;
        };
        /** SubmissionView */
        SubmissionView: {
            /** Document Sha256 */
            document_sha256: string;
            /**
             * Issued On
             * Format: date
             */
            issued_on: string;
            /**
             * Priced By
             * Format: uuid
             */
            priced_by: string;
            /** Quote No */
            quote_no: string;
            /** Recipients */
            recipients: string[];
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
            /**
             * Valid To
             * Format: date
             */
            valid_to: string;
        };
        /** SubmitBody */
        SubmitBody: {
            /** Case Version */
            case_version: number;
            /** Quote No */
            quote_no: string;
        };
        /** SupersededView */
        SupersededView: {
            /** Attachment Id */
            attachment_id: string;
            /** Message Id */
            message_id: string;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Revision */
            revision: number;
            /** @default superseded */
            value_state: components["schemas"]["ValueState"];
        };
        /**
         * TargetView
         * @description A target beside what was measured end to end (waits included).
         */
        TargetView: {
            measured: components["schemas"]["TimeStat"];
            /** Target Seconds */
            target_seconds: number;
        };
        /**
         * TextRange
         * @description Characters ``start`` (inclusive) to ``end`` (exclusive) of a text.
         */
        TextRange: {
            /** End */
            end: number;
            /** Start */
            start: number;
        };
        /** TimeStat */
        TimeStat: {
            /** Cases */
            cases: number;
            /** Max Seconds */
            max_seconds: number | null;
            /** Median Seconds */
            median_seconds: number | null;
        };
        /** TimesView */
        TimesView: {
            approver: components["schemas"]["TimeStat"];
            customer: components["schemas"]["TimeStat"];
            design: components["schemas"]["TimeStat"];
            dw: components["schemas"]["TimeStat"];
            /** Pc */
            pc?: null;
            sales: components["schemas"]["TimeStat"];
        };
        /**
         * UnappliedDecisionView
         * @description A cross-check decision the platform recorded and DW1's run could not
         *     apply to the order (ticket 14): who decided which way, on which version,
         *     and the reason code. Ids and codes only.
         */
        UnappliedDecisionView: {
            /** Approval Id */
            approval_id: string | null;
            /** Approved */
            approved: boolean;
            /**
             * At
             * Format: date-time
             */
            at: string;
            /**
             * Decided By
             * Format: uuid
             */
            decided_by: string;
            /** Decided On */
            decided_on: number | null;
            /** Reason Code */
            reason_code: string;
            /**
             * Run Id
             * Format: uuid
             */
            run_id: string;
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
         * ValueConfirmationView
         * @description One value a model read, as Sales confirmed it (ticket 29).
         */
        ValueConfirmationView: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /**
             * By
             * Format: uuid
             */
            by: string;
            /** Field */
            field: string;
            /** Read */
            read: string;
            /** Value */
            value: string;
        };
        /**
         * ValueCorrectionView
         * @description A value Sales typed for a flagged field, beside the value as read. An
         *     amount is shown only with `sales.price.read`.
         */
        ValueCorrectionView: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /**
             * By
             * Format: uuid
             */
            by: string;
            /** Field */
            field: string;
            value: components["schemas"]["Words"];
        };
        /**
         * ValueState
         * @description How sure a value on a case is (CONTEXT.md "Value states").
         * @enum {string}
         */
        ValueState: "dw" | "uncertain" | "confirmed" | "hand_entered" | "superseded";
        /**
         * VersionBody
         * @description The case version the decision was made on.
         */
        VersionBody: {
            /** Case Version */
            case_version: number;
        };
        Words: string | components["schemas"]["Hidden"];
        /** WorkItem */
        WorkItem: {
            /** Action */
            action: string;
            /** Assigned To */
            assigned_to: string | null;
            /** Customer Code */
            customer_code: string | null;
            /** Due */
            due: string | null;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "order" | "quote" | "message";
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Status */
            status: string;
        };
        /** WorkerStateView */
        WorkerStateView: {
            /** Changed At */
            changed_at: string | null;
            /** Changed By */
            changed_by: string | null;
            /** Paused */
            paused: boolean;
            /** Reason */
            reason: string | null;
        };
        /** YcbgBody */
        YcbgBody: {
            /** Case Version */
            case_version: number;
            /** Ycbg No */
            ycbg_no?: string | null;
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
    inbox_api_v1_sales_inbox_get: {
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
                    "application/json": components["schemas"]["InboxMessageView"][];
                };
            };
        };
    };
    process_all_api_v1_sales_inbox_process_all_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path?: never;
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
                    "application/json": components["schemas"]["ProcessingQueuedView"];
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
    process_api_v1_sales_inbox__message_id__process_post: {
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
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProcessingJobView"];
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
    layouts_api_v1_sales_layouts_get: {
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
                    "application/json": components["schemas"]["LayoutView"][];
                };
            };
        };
    };
    propose_layout_api_v1_sales_layouts_post: {
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
                "application/json": components["schemas"]["LayoutBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LayoutView"];
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
    layout_preview_api_v1_sales_layouts_preview_post: {
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
                "application/json": components["schemas"]["LayoutBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LayoutPreviewView"];
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
    layout_source_api_v1_sales_layouts_source_get: {
        parameters: {
            query: {
                message_id: string;
                attachment_id: string;
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
                    "application/json": components["schemas"]["LayoutSourceView"];
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
    bravo_orders_api_v1_sales_master_data_bravo_orders_get: {
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
                    "application/json": components["schemas"]["MasterDataView_BravoOrderView_"];
                };
            };
        };
    };
    convert_list_api_v1_sales_master_data_convert_list_get: {
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
                    "application/json": components["schemas"]["MasterDataView_ConvertEntryView_"];
                };
            };
        };
    };
    customers_api_v1_sales_master_data_customers_get: {
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
                    "application/json": components["schemas"]["MasterDataView_CustomerView_"];
                };
            };
        };
    };
    items_api_v1_sales_master_data_items_get: {
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
                    "application/json": components["schemas"]["MasterDataView_ItemView_"];
                };
            };
        };
    };
    lme_api_v1_sales_master_data_lme_get: {
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
                    "application/json": components["schemas"]["MasterDataView_LmeView_"];
                };
            };
        };
    };
    open_ycbg_api_v1_sales_master_data_open_ycbg_get: {
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
                    "application/json": components["schemas"]["MasterDataView_OpenYcbgView_"];
                };
            };
        };
    };
    quotations_api_v1_sales_master_data_quotations_get: {
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
                    "application/json": components["schemas"]["MasterDataView_QuotationRowView_"];
                };
            };
        };
    };
    my_work_api_v1_sales_my_work_get: {
        parameters: {
            query?: {
                limit?: number;
                /** @description Opaque cursor from a previous page. */
                cursor?: string | null;
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
                    "application/json": components["schemas"]["Page_WorkItem_"];
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
    orders_api_v1_sales_orders_get: {
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
                    "application/json": components["schemas"]["OrderSummaryView"][];
                };
            };
        };
    };
    order_api_v1_sales_orders__case_id__get: {
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
                    "application/json": components["schemas"]["OrderCaseView"];
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
    order_artifacts_api_v1_sales_orders__case_id__artifacts_get: {
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
                    "application/json": components["schemas"]["ArtifactListView"];
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
    render_order_artifact_api_v1_sales_orders__case_id__artifacts_post: {
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
                "application/json": components["schemas"]["RenderBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RenderedView"];
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
    order_artifact_api_v1_sales_orders__case_id__artifacts__artifact_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
                artifact_id: string;
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
                content?: never;
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
    reassign_order_api_v1_sales_orders__case_id__assignee_put: {
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
                "application/json": components["schemas"]["AssigneeBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    order_assignees_api_v1_sales_orders__case_id__assignees_get: {
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
                    "application/json": components["schemas"]["AssigneeView"][];
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
    bravo_entry_api_v1_sales_orders__case_id__bravo_entry_post: {
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
                "application/json": components["schemas"]["BravoEntryBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    close_api_v1_sales_orders__case_id__close_post: {
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
                "application/json": components["schemas"]["CloseBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    confirm_api_v1_sales_orders__case_id__confirm_post: {
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
                "application/json": components["schemas"]["ConfirmBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    correction_request_api_v1_sales_orders__case_id__correction_request_post: {
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
                "application/json": components["schemas"]["VersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    correct_value_api_v1_sales_orders__case_id__findings__finding_key__corrections_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                finding_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CorrectionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    dispose_api_v1_sales_orders__case_id__findings__finding_key__disposition_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                finding_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DispositionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    delivery_date_api_v1_sales_orders__case_id__lines__line_no__delivery_date_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                line_no: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["VersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    mapping_api_v1_sales_orders__case_id__lines__line_no__mapping_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                line_no: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MappingBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    prepare_api_v1_sales_orders__case_id__prepare_post: {
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
                "application/json": components["schemas"]["VersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    resend_cross_check_api_v1_sales_orders__case_id__resend_cross_check_post: {
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
                "application/json": components["schemas"]["VersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    resume_review_api_v1_sales_orders__case_id__resume_review_post: {
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
                "application/json": components["schemas"]["VersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    order_source_api_v1_sales_orders__case_id__source__attachment_id__get: {
        parameters: {
            query?: {
                page?: number | null;
                sheet?: string | null;
            };
            header?: never;
            path: {
                case_id: string;
                attachment_id: string;
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
                    "application/json": components["schemas"]["SourceView"];
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
    overview_api_v1_sales_overview_get: {
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
                    "application/json": components["schemas"]["OverviewView"];
                };
            };
        };
    };
    quotes_api_v1_sales_quotes_get: {
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
                    "application/json": components["schemas"]["QuoteSummaryView"][];
                };
            };
        };
    };
    screening_api_v1_sales_quotes_screening_get: {
        parameters: {
            query?: {
                as_of?: string | null;
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
                    "application/json": components["schemas"]["ScreeningRow"][];
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
    quote_api_v1_sales_quotes__case_id__get: {
        parameters: {
            query?: {
                incoterm?: ("EXW" | "FCA" | "FOB" | "CIF" | "DAP" | "DDP") | null;
                destination?: string | null;
            };
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
                    "application/json": components["schemas"]["QuoteCaseView"];
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
    quote_artifacts_api_v1_sales_quotes__case_id__artifacts_get: {
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
                    "application/json": components["schemas"]["ArtifactListView"];
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
    render_quote_artifact_api_v1_sales_quotes__case_id__artifacts_post: {
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
                "application/json": components["schemas"]["RenderBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RenderedView"];
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
    quote_artifact_api_v1_sales_quotes__case_id__artifacts__artifact_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
                artifact_id: string;
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
                content?: never;
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
    reassign_quote_api_v1_sales_quotes__case_id__assignee_put: {
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
                "application/json": components["schemas"]["AssigneeBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    quote_assignees_api_v1_sales_quotes__case_id__assignees_get: {
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
                    "application/json": components["schemas"]["AssigneeView"][];
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
    decline_api_v1_sales_quotes__case_id__decline_post: {
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
                "application/json": components["schemas"]["DeclineBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    design_sent_api_v1_sales_quotes__case_id__design_sent_post: {
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
                "application/json": components["schemas"]["VersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    answer_api_v1_sales_quotes__case_id__findings__finding_key__answer_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                finding_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AnswerBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    master_list_api_v1_sales_quotes__case_id__master_list_post: {
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
                "application/json": components["schemas"]["VersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    quote_message_text_api_v1_sales_quotes__case_id__message_text_get: {
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
                    "application/json": components["schemas"]["MessageTextView"];
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
    price_api_v1_sales_quotes__case_id__price_post: {
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
                "application/json": components["schemas"]["PriceBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    sent_api_v1_sales_quotes__case_id__sent_post: {
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
                "application/json": components["schemas"]["VersionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    quote_source_api_v1_sales_quotes__case_id__source__attachment_id__get: {
        parameters: {
            query?: {
                page?: number | null;
                sheet?: string | null;
            };
            header?: never;
            path: {
                case_id: string;
                attachment_id: string;
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
                    "application/json": components["schemas"]["SourceView"];
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
    spec_discussion_api_v1_sales_quotes__case_id__spec_discussion_post: {
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
                "application/json": components["schemas"]["SpecBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    submit_api_v1_sales_quotes__case_id__submit_post: {
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
                "application/json": components["schemas"]["SubmitBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    ycbg_api_v1_sales_quotes__case_id__ycbg_post: {
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
                "application/json": components["schemas"]["YcbgBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CaseChangeView"];
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
    rules_in_force_api_v1_sales_rules_get: {
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
                    "application/json": components["schemas"]["RulesInForceView"];
                };
            };
        };
    };
    rule_platform_documents_api_v1_sales_rules__key__platform_get: {
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
                    "application/json": components["schemas"]["PlatformDocumentView"][];
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
    rule_schema_api_v1_sales_rules__key__schema_get: {
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
                    "application/json": components["schemas"]["RuleSchemaView"];
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
    propose_rules_api_v1_sales_rules__key__versions_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                key: components["schemas"]["RuleKey"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RuleProposalBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RuleVersionView"];
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
    pause_api_v1_sales_worker_pause_post: {
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
                "application/json": components["schemas"]["PauseBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkerStateView"];
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
    resume_api_v1_sales_worker_resume_post: {
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
                "application/json": components["schemas"]["ResumeBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkerStateView"];
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
}
