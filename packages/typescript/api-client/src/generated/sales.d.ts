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
            /** Needed By */
            needed_by?: string | null;
            /** Note */
            note?: string | null;
            /** Quantity */
            quantity?: number | string | null;
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
        FindingCode: "code_unmapped" | "code_ambiguous" | "price_mismatch" | "currency_mismatch" | "uom_mismatch" | "quotation_missing" | "lme_band_mismatch" | "moq_violation" | "pack_multiple" | "line_total_mismatch" | "value_uncertain" | "customer_unknown" | "duplicate_po" | "requested_date_short_lt" | "missing_noc_esf" | "revised_po" | "revision_without_base" | "customer_temporary" | "sender_unverified";
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
            /** Message Id */
            message_id: string;
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
        /** LineBasisView */
        LineBasisView: {
            /** Candidates */
            candidates: string[];
            /** Checks Run */
            checks_run: string[];
            /** Convert Prv Code */
            convert_prv_code: string | null;
            item: components["schemas"]["ItemBasisView"] | null;
            /** Lead Time Days */
            lead_time_days: number | null;
            /** Lead Time Source */
            lead_time_source: string | null;
            lme: components["schemas"]["LmeView"] | null;
            quotation: components["schemas"]["QuotationBasisView"] | null;
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
        /** LineDate */
        LineDate: {
            /**
             * Confirmed Date
             * Format: date
             */
            confirmed_date: string;
            /** Line No */
            line_no: number;
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
            /** Kind */
            kind: string;
            /** Owner */
            owner?: string | null;
            /** Processed At */
            processed_at?: string | null;
            /** Reason */
            reason?: string | null;
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
            /** Header Flags */
            header_flags: components["schemas"]["FlaggedValue"][];
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
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Release Manifest Ref */
            release_manifest_ref: string | null;
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
            /** Quantity */
            quantity: string;
            /**
             * Requested Date
             * Format: date
             */
            requested_date: string;
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
        /** ProcessAllView */
        ProcessAllView: {
            /** Results */
            results: components["schemas"]["MessageDispositionView"][];
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
            approval: components["schemas"]["QuoteApprovalView"] | null;
            /** Assigned To */
            assigned_to: string | null;
            /** Attachment Id */
            attachment_id: string;
            /** Attachment Sha256 */
            attachment_sha256: string;
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
            /** Overdue */
            overdue: boolean;
            /** Parser Version */
            parser_version: string;
            pricing: components["schemas"]["PricingView"] | null;
            /** Quote Due */
            quote_due: string | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Release Manifest Ref */
            release_manifest_ref: string | null;
            /** Returns */
            returns: components["schemas"]["ReturnView"][];
            /**
             * Rfq Date
             * Format: date
             */
            rfq_date: string;
            /** Rfq No */
            rfq_no: string;
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
            disposition: components["schemas"]["QuoteDispositionView"];
            expected: components["schemas"]["Words"] | null;
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
            /** Customer Item Code */
            customer_item_code: string | null;
            /** Description */
            description: string;
            /** Line No */
            line_no: number;
            /** Needed By */
            needed_by: string | null;
            /** Quantity */
            quantity: string | null;
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
            rfq_no: string;
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
        RegionFlag: "hidden_sheet" | "hidden_row" | "hidden_column" | "font_matches_fill" | "formula_without_cached_value";
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
         * @description The place in one attachment a value was read from.
         *
         *     At least one of: ``cell_ref`` (``Sheet!B10``), ``page`` with its
         *     ``boxes``, or ``quote``, the words as the file prints them. More than one
         *     may be given when the reader knows more than one.
         */
        SourceAnchor: {
            /** Attachment Id */
            attachment_id: string;
            /** Attachment Sha256 */
            attachment_sha256: string;
            /**
             * Boxes
             * @default []
             */
            boxes: components["schemas"]["PageBox"][];
            /** Cell Ref */
            cell_ref?: string | null;
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
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProcessAllView"];
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
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageDispositionView"];
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
                    "application/json": components["schemas"]["WorkItem"][];
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
