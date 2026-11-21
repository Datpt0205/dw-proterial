/**
 * Auto-generated types for context "sales" — do not edit.
 * Regenerate with `make generate-contracts`.
 */
export interface paths {
    "/api/v1/sales/activity": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Activity Summary */
        get: operations["activity_summary_api_v1_sales_activity_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/activity/autonomy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Activity Autonomy */
        get: operations["activity_autonomy_api_v1_sales_activity_autonomy_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/activity/labels": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Activity Labels */
        get: operations["activity_labels_api_v1_sales_activity_labels_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/ask": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Assistant Ask */
        post: operations["assistant_ask_api_v1_sales_assistant_ask_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/ask/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Assistant Stream */
        post: operations["assistant_stream_api_v1_sales_assistant_ask_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/cases": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Assistant Cases */
        get: operations["assistant_cases_api_v1_sales_assistant_cases_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/cases/{kind}/{case_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Assistant Case */
        get: operations["assistant_case_api_v1_sales_assistant_cases__kind___case_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/cases/{kind}/{case_id}/ask": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Assistant Case Ask */
        post: operations["assistant_case_ask_api_v1_sales_assistant_cases__kind___case_id__ask_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/cases/{kind}/{case_id}/ask/stream": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Assistant Case Stream */
        post: operations["assistant_case_stream_api_v1_sales_assistant_cases__kind___case_id__ask_stream_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/cases/{kind}/{case_id}/turns/{seq}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Assistant Confirm */
        post: operations["assistant_confirm_api_v1_sales_assistant_cases__kind___case_id__turns__seq__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/conversation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Assistant Conversation */
        get: operations["assistant_conversation_api_v1_sales_assistant_conversation_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/assistant/unread": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Assistant Unread */
        get: operations["assistant_unread_api_v1_sales_assistant_unread_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/bravo-exports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Bravo Exports */
        get: operations["bravo_exports_api_v1_sales_bravo_exports_get"];
        put?: never;
        /** Upload Bravo Export */
        post: operations["upload_bravo_export_api_v1_sales_bravo_exports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/customers/{customer_code}/notation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Customer Notation */
        get: operations["customer_notation_api_v1_sales_customers__customer_code__notation_get"];
        /** Set Customer Notation */
        put: operations["set_customer_notation_api_v1_sales_customers__customer_code__notation_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/customers/{customer_code}/notation/{kind}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Forget Customer Notation */
        delete: operations["forget_customer_notation_api_v1_sales_customers__customer_code__notation__kind__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/customers/{customer_code}/salesorder-examples": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Salesorder Examples */
        get: operations["salesorder_examples_api_v1_sales_customers__customer_code__salesorder_examples_get"];
        put?: never;
        /** Request Salesorder Example */
        post: operations["request_salesorder_example_api_v1_sales_customers__customer_code__salesorder_examples_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/customers/{customer_code}/salesorder-pairs": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Salesorder Pairs */
        get: operations["salesorder_pairs_api_v1_sales_customers__customer_code__salesorder_pairs_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
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
    "/api/v1/sales/inbox/upload": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Upload Po */
        post: operations["upload_po_api_v1_sales_inbox_upload_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/inbox/{message_id}/case": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pick Thread Case */
        post: operations["pick_thread_case_api_v1_sales_inbox__message_id__case_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/inbox/{message_id}/customer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Sender Customer */
        get: operations["sender_customer_api_v1_sales_inbox__message_id__customer_get"];
        put?: never;
        /** Confirm Sender Customer */
        post: operations["confirm_sender_customer_api_v1_sales_inbox__message_id__customer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/inbox/{message_id}/design-reply": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Design Text Reply */
        get: operations["design_text_reply_api_v1_sales_inbox__message_id__design_reply_get"];
        put?: never;
        /** Confirm Design Text Reply */
        post: operations["confirm_design_text_reply_api_v1_sales_inbox__message_id__design_reply_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/inbox/{message_id}/handled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Handled */
        post: operations["handled_api_v1_sales_inbox__message_id__handled_post"];
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
    "/api/v1/sales/inbox/{message_id}/reopen": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reopen */
        post: operations["reopen_api_v1_sales_inbox__message_id__reopen_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/inbox/{message_id}/triage": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decide Triage Card */
        post: operations["decide_triage_card_api_v1_sales_inbox__message_id__triage_post"];
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
    "/api/v1/sales/master-data/convert-gaps": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Convert Gaps */
        get: operations["convert_gaps_api_v1_sales_master_data_convert_gaps_get"];
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
    "/api/v1/sales/master-data/imports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Catalog State */
        get: operations["catalog_state_api_v1_sales_master_data_imports_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/imports/snapshots/{snapshot_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Catalog Preview */
        get: operations["catalog_preview_api_v1_sales_master_data_imports_snapshots__snapshot_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/imports/snapshots/{snapshot_id}/submit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Catalog Submit */
        post: operations["catalog_submit_api_v1_sales_master_data_imports_snapshots__snapshot_id__submit_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/imports/{catalog_list}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Catalog Upload */
        post: operations["catalog_upload_api_v1_sales_master_data_imports__catalog_list__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/master-data/imports/{catalog_list}/template": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Catalog Template */
        get: operations["catalog_template_api_v1_sales_master_data_imports__catalog_list__template_get"];
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
    "/api/v1/sales/orders/{case_id}/activity": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Activity */
        get: operations["order_activity_api_v1_sales_orders__case_id__activity_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/agreement": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record Agreement */
        post: operations["record_agreement_api_v1_sales_orders__case_id__agreement_post"];
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
    "/api/v1/sales/orders/{case_id}/artifacts/{artifact_id}/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Send Order Mail */
        post: operations["send_order_mail_api_v1_sales_orders__case_id__artifacts__artifact_id__send_post"];
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
    "/api/v1/sales/orders/{case_id}/bravo-read-back": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Bravo Read Back */
        get: operations["bravo_read_back_api_v1_sales_orders__case_id__bravo_read_back_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/change-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Open Change Request */
        post: operations["open_change_request_api_v1_sales_orders__case_id__change_requests_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/change-requests/{request_id}/lines": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Add Change Line */
        post: operations["add_change_line_api_v1_sales_orders__case_id__change_requests__request_id__lines_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/change-requests/{request_id}/lines/{seq}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Change Line */
        post: operations["confirm_change_line_api_v1_sales_orders__case_id__change_requests__request_id__lines__seq__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/change-requests/{request_id}/lines/{seq}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject Change Line */
        post: operations["reject_change_line_api_v1_sales_orders__case_id__change_requests__request_id__lines__seq__reject_post"];
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
    "/api/v1/sales/orders/{case_id}/customer-reminder": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Reminder */
        get: operations["order_reminder_api_v1_sales_orders__case_id__customer_reminder_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/decline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Record Decline */
        post: operations["record_decline_api_v1_sales_orders__case_id__decline_post"];
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
    "/api/v1/sales/orders/{case_id}/findings/{finding_key}/explanation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Explain Finding */
        get: operations["explain_finding_api_v1_sales_orders__case_id__findings__finding_key__explanation_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order History */
        get: operations["order_history_api_v1_sales_orders__case_id__history_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/internal-change": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Apply Internal Change */
        post: operations["apply_internal_change_api_v1_sales_orders__case_id__internal_change_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/internal-change/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Read Internal Change */
        post: operations["read_internal_change_api_v1_sales_orders__case_id__internal_change_read_post"];
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
    "/api/v1/sales/orders/{case_id}/lines/{line_no}/design-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Design Request */
        get: operations["design_request_api_v1_sales_orders__case_id__lines__line_no__design_request_get"];
        put?: never;
        /** Design Asked */
        post: operations["design_asked_api_v1_sales_orders__case_id__lines__line_no__design_request_post"];
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
    "/api/v1/sales/orders/{case_id}/lines/{line_no}/mapping/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject Mapping */
        post: operations["reject_mapping_api_v1_sales_orders__case_id__lines__line_no__mapping_reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/lines/{line_no}/mapping/undo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Undo Mapping */
        post: operations["undo_mapping_api_v1_sales_orders__case_id__lines__line_no__mapping_undo_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/lines/{line_no}/pc-answer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pc Answer */
        post: operations["pc_answer_api_v1_sales_orders__case_id__lines__line_no__pc_answer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/lines/{line_no}/trail": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Line Trail */
        get: operations["order_line_trail_api_v1_sales_orders__case_id__lines__line_no__trail_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/message-text": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Message Text */
        get: operations["order_message_text_api_v1_sales_orders__case_id__message_text_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/outbound": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Outbound */
        get: operations["order_outbound_api_v1_sales_orders__case_id__outbound_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/pc-dates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pc Dates */
        post: operations["pc_dates_api_v1_sales_orders__case_id__pc_dates_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/pc-dates/from-mail/{message_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pc Dates From Mail */
        post: operations["pc_dates_from_mail_api_v1_sales_orders__case_id__pc_dates_from_mail__message_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/pc-mails": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Pc Mails */
        get: operations["pc_mails_api_v1_sales_orders__case_id__pc_mails_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/pc-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Pc Request */
        get: operations["pc_request_api_v1_sales_orders__case_id__pc_request_get"];
        put?: never;
        /** Pc Asked */
        post: operations["pc_asked_api_v1_sales_orders__case_id__pc_request_post"];
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
    "/api/v1/sales/orders/{case_id}/quote": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Open Quote */
        post: operations["open_quote_api_v1_sales_orders__case_id__quote_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/quote-check": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Quote Check */
        post: operations["quote_check_api_v1_sales_orders__case_id__quote_check_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/reply-draft": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Reply Draft */
        get: operations["order_reply_draft_api_v1_sales_orders__case_id__reply_draft_get"];
        put?: never;
        post?: never;
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
    "/api/v1/sales/orders/{case_id}/thread-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Order Thread */
        get: operations["order_thread_api_v1_sales_orders__case_id__thread_summary_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/update/answer-sent": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Update Answer Sent */
        post: operations["update_answer_sent_api_v1_sales_orders__case_id__update_answer_sent_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/update/bravo-file": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Update Bravo File */
        post: operations["update_bravo_file_api_v1_sales_orders__case_id__update_bravo_file_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/update/customer-answer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Update Customer Answer */
        post: operations["update_customer_answer_api_v1_sales_orders__case_id__update_customer_answer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/update/lines/{line_no}/pc-answer": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Update Pc Answer */
        post: operations["update_pc_answer_api_v1_sales_orders__case_id__update_lines__line_no__pc_answer_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/orders/{case_id}/update/pc-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Update Pc Request */
        get: operations["update_pc_request_api_v1_sales_orders__case_id__update_pc_request_get"];
        put?: never;
        /** Update Pc Asked */
        post: operations["update_pc_asked_api_v1_sales_orders__case_id__update_pc_request_post"];
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
    "/api/v1/sales/pipeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Pipeline */
        get: operations["pipeline_api_v1_sales_pipeline_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/prompts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Prompt Versions */
        get: operations["prompt_versions_api_v1_sales_prompts_get"];
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
    "/api/v1/sales/quotes/screening/{customer_code}/{prv_code}/followup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Screening Followup */
        get: operations["screening_followup_api_v1_sales_quotes_screening__customer_code___prv_code__followup_get"];
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
    "/api/v1/sales/quotes/{case_id}/activity": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Activity */
        get: operations["quote_activity_api_v1_sales_quotes__case_id__activity_get"];
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
    "/api/v1/sales/quotes/{case_id}/artifacts/{artifact_id}/send": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Send Quote Mail */
        post: operations["send_quote_mail_api_v1_sales_quotes__case_id__artifacts__artifact_id__send_post"];
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
    "/api/v1/sales/quotes/{case_id}/customer-reminder": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Reminder */
        get: operations["quote_reminder_api_v1_sales_quotes__case_id__customer_reminder_get"];
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
    "/api/v1/sales/quotes/{case_id}/design-from-bravo": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Design From Bravo
         * @description Ticket 11: Design's QUOTE read from Bravo recorded as its reply.
         */
        post: operations["design_from_bravo_api_v1_sales_quotes__case_id__design_from_bravo_post"];
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
    "/api/v1/sales/quotes/{case_id}/history": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote History */
        get: operations["quote_history_api_v1_sales_quotes__case_id__history_get"];
        put?: never;
        post?: never;
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
    "/api/v1/sales/quotes/{case_id}/outbound": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Outbound */
        get: operations["quote_outbound_api_v1_sales_quotes__case_id__outbound_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/pcs-price": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Pcs Price */
        post: operations["pcs_price_api_v1_sales_quotes__case_id__pcs_price_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/quotes/{case_id}/pcs-price-request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Pcs Price Request */
        get: operations["pcs_price_request_api_v1_sales_quotes__case_id__pcs_price_request_get"];
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
    "/api/v1/sales/quotes/{case_id}/production-type": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Production Type */
        post: operations["production_type_api_v1_sales_quotes__case_id__production_type_post"];
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
    "/api/v1/sales/quotes/{case_id}/signed-copy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload Signed Quote
         * @description The quotation printed, signed on paper and scanned: kept with the
         *     case (no electronic signature, 2026-10-28).
         */
        post: operations["upload_signed_quote_api_v1_sales_quotes__case_id__signed_copy_post"];
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
    "/api/v1/sales/quotes/{case_id}/thread-summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Quote Thread */
        get: operations["quote_thread_api_v1_sales_quotes__case_id__thread_summary_get"];
        put?: never;
        post?: never;
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
    "/api/v1/sales/rules/drafts/{draft_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rule Draft */
        get: operations["rule_draft_api_v1_sales_rules_drafts__draft_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/rules/process": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Rules Process */
        get: operations["rules_process_api_v1_sales_rules_process_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/rules/{key}/drafts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Rule Draft */
        post: operations["request_rule_draft_api_v1_sales_rules__key__drafts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/rules/{key}/drafts/words": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Request Rule Words */
        post: operations["request_rule_words_api_v1_sales_rules__key__drafts_words_post"];
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
    "/api/v1/sales/salesorder-examples/by-version/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Salesorder Example Of Version */
        get: operations["salesorder_example_of_version_api_v1_sales_salesorder_examples_by_version__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/salesorder-examples/{example_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Salesorder Example */
        get: operations["salesorder_example_api_v1_sales_salesorder_examples__example_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/salesorder-examples/{example_id}/submissions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Submit Salesorder Example */
        post: operations["submit_salesorder_example_api_v1_sales_salesorder_examples__example_id__submissions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/salesorder-pairs/{pair_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Withdraw Salesorder Pair */
        delete: operations["withdraw_salesorder_pair_api_v1_sales_salesorder_pairs__pair_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/skills": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Skills In Force */
        get: operations["skills_in_force_api_v1_sales_skills_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/skills/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Skill Version */
        get: operations["skill_version_api_v1_sales_skills_versions__version_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/skills/{name}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Propose Skill */
        post: operations["propose_skill_api_v1_sales_skills__name__versions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/today": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Today */
        get: operations["today_api_v1_sales_today_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/today/reminders/{notification_id}/mark": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark Reminder */
        post: operations["mark_reminder_api_v1_sales_today_reminders__notification_id__mark_post"];
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
        /** ActivityEntry */
        ActivityEntry: {
            /** Calls */
            calls: number;
            check: components["schemas"]["CheckView"];
            /** Duration Ms */
            duration_ms: number | null;
            /**
             * Handled By
             * @enum {string}
             */
            handled_by: "dw1" | "person";
            /**
             * Kind
             * @enum {string}
             */
            kind: "read" | "route" | "check" | "to_person" | "model_unavailable";
            /** Line No */
            line_no: number | null;
            /** Message Id */
            message_id: string;
            /** Model */
            model: string | null;
            /** Model Profile */
            model_profile: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Process Steps */
            process_steps: components["schemas"]["StepId"][];
            /** Produced */
            produced: components["schemas"]["ProducedValue"][];
            /** Prompt */
            prompt: string;
            /** Refusals */
            refusals: {
                [key: string]: number;
            };
            step: components["schemas"]["ModelStep"];
            /** Taken Over By */
            taken_over_by: string | null;
        };
        /**
         * ActivityFilter
         * @description The case list filter a count stands for: the parameters, not a URL.
         */
        ActivityFilter: {
            /**
             * From
             * Format: date
             */
            from: string;
            /** Handled By */
            handled_by?: ("dw1" | "person") | null;
            lane?: components["schemas"]["CaseKind"] | null;
            /** Reason Code */
            reason_code?: string | null;
            /** Result */
            result?: ("accepted" | "refused" | "unavailable") | null;
            step: components["schemas"]["ModelStep"];
            /**
             * To
             * Format: date
             */
            to: string;
        };
        /** ActivitySummaryView */
        ActivitySummaryView: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Days */
            days: components["schemas"]["DayView"][];
            /**
             * From
             * Format: date
             */
            from: string;
            lane: components["schemas"]["CaseKind"] | null;
            /** Steps */
            steps: components["schemas"]["StepSummaryView"][];
            /**
             * To
             * Format: date
             */
            to: string;
        };
        /**
         * ActorView
         * @description A role or a permission set holding scopes the step's actions need.
         */
        ActorView: {
            /** Key */
            key: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "role" | "permission_set";
            /** Name */
            name: string;
            /** Scopes */
            scopes: string[];
        };
        /**
         * AgreementBody
         * @description How the customer agreed to the confirmation (ticket 28), and their
         *     reply on the case when the person records it from one.
         */
        AgreementBody: {
            /** Case Version */
            case_version: number;
            /**
             * How
             * @enum {string}
             */
            how: "accepted" | "implied";
            /** Message Id */
            message_id?: string | null;
        };
        /**
         * AgreementView
         * @description How the customer agreed, as a person recorded it (ticket 28): in
         *     words, from their reply and its located sentences when recorded from
         *     one, or by silence.
         */
        AgreementView: {
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
            /**
             * How
             * @enum {string}
             */
            how: "accepted" | "implied";
            /** Message Id */
            message_id: string | null;
            /** Quotes */
            quotes: string[];
        };
        Amount: string | components["schemas"]["Hidden"];
        /**
         * AnchorRef
         * @description Where the case view anchors the value: the line (None for the
         *     request's or the PO's own fields) and the field its ``anchors`` key it by.
         */
        AnchorRef: {
            /** Field */
            field: string;
            /** Line No */
            line_no: number | null;
        };
        /** AnswerBody */
        AnswerBody: {
            /**
             * As Read
             * @default false
             */
            as_read: boolean;
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
        /** AnswerView */
        AnswerView: {
            turn: components["schemas"]["TurnView"];
        };
        /**
         * AppliedChangeView
         * @description A value of the line the customer asked to change by mail, which a
         *     person confirmed (ticket 27): it replaces the value above where the line
         *     is entered. Never an amount.
         */
        AppliedChangeView: {
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
            /**
             * Field
             * @enum {string}
             */
            field: "quantity" | "requested_date";
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            /** Value */
            value: string;
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
         * AskBody
         * @description A question to the status assistant (ADR 0007). Which conversation it
         *     continues is the route's (ticket 46): the caller's general one, or their
         *     one on the case the path names; never an id the body sends.
         */
        AskBody: {
            /** Question */
            question: string;
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
        /** AutonomySummaryView */
        AutonomySummaryView: {
            /** Days */
            days: number;
            /** Steps */
            steps: components["schemas"]["StepAutonomyView"][];
        };
        /** BaStepView */
        BaStepView: {
            /** Code */
            code: string;
            /** Label */
            label: string;
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
        /**
         * BravoExport
         * @description One uploaded export and what became of it (module docstring).
         */
        BravoExport: {
            /** Error */
            error?: string | null;
            /**
             * Export Id
             * Format: uuid
             */
            export_id: string;
            /** File Name */
            file_name: string;
            /** File Sha256 */
            file_sha256: string;
            /** File Size */
            file_size: number;
            /**
             * Outcomes
             * @default []
             */
            outcomes: components["schemas"]["ExportOutcome"][];
            /**
             * Rejected
             * @default []
             */
            rejected: components["schemas"]["RejectedRow"][];
            /**
             * Screen
             * @enum {string}
             */
            screen: "ycbg" | "sales_orders";
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "read" | "failed";
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
        };
        /**
         * BravoExportBody
         * @description A Bravo screen exported by Sales (tickets 16, 03): which screen, the
         *     file's name and its bytes, base64, decoded here and never opened: the
         *     worker reads it in the reader sandbox.
         */
        BravoExportBody: {
            /** Content B64 */
            content_b64: string;
            /** File Name */
            file_name: string;
            /**
             * Screen
             * @enum {string}
             */
            screen: "ycbg" | "sales_orders";
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
         * BravoReadBack
         * @description A case's sales order as Bravo held it when last read, against the case
         *     version it was compared with (module docstring).
         */
        BravoReadBack: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Case Version */
            case_version: number;
            /** Differences */
            differences: components["schemas"]["SoDifference"][];
            /** File Sha256 */
            file_sha256: string;
            /** Po No */
            po_no: string;
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
            /** Rows Read */
            rows_read: number;
            /** So No */
            so_no: string;
        };
        /** BriefView */
        BriefView: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Counts */
            counts: string[];
            /**
             * Notification Id
             * Format: uuid
             */
            notification_id: string;
            /** Opening */
            opening: string | null;
            /** Title */
            title: string;
        };
        /**
         * CardDecisionRequest
         * @description A person's decision on a triage card: the step they take (the card's
         *     own or another of the closed set), None to dismiss it; ``attach`` to
         *     attach a reply to the case the card names. Never a case id: the only
         *     case a card may lead to is its own.
         */
        CardDecisionRequest: {
            /**
             * Attach
             * @default false
             */
            attach: boolean;
            /** Step */
            step: ("reply_to_case" | "delivery_change" | "complaint" | "sample_request" | "portal_notice") | null;
        };
        /**
         * CardVerdict
         * @description What a person did with a card, and when.
         */
        CardVerdict: {
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
            /** Case Id */
            case_id?: string | null;
            /**
             * Decision
             * @enum {string}
             */
            decision: "taken" | "changed" | "dismissed";
            /** Step */
            step: ("reply_to_case" | "delivery_change" | "complaint" | "sample_request" | "portal_notice") | null;
        };
        /** CaseActivityView */
        CaseActivityView: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            case_kind: components["schemas"]["CaseKind"];
            /** Entries */
            entries: components["schemas"]["ActivityEntry"][];
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
         * CaseConversationView
         * @description A case talked about, on the assistant page's short list.
         */
        CaseConversationView: {
            case: components["schemas"]["CaseRefView"];
            /** Last Turn At */
            last_turn_at: string;
            /** Unread */
            unread: boolean;
        };
        /** CaseHistoryEntry */
        CaseHistoryEntry: {
            /** Action */
            action: string;
            /**
             * Actor Kind
             * @enum {string}
             */
            actor_kind: "worker" | "user";
            /** Actor User Id */
            actor_user_id: string | null;
            /** Case Version */
            case_version: number;
            /** From Status */
            from_status: string | null;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Reason Code */
            reason_code: string | null;
            /** To Status */
            to_status: string;
            /** Worker Id */
            worker_id: string | null;
        };
        /**
         * CaseKind
         * @enum {string}
         */
        CaseKind: "order" | "quote";
        /** CaseRefView */
        CaseRefView: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "order" | "quote";
            /** Label */
            label: string;
        };
        /**
         * CaseReply
         * @description A message attached to a case because its thread headers name a message
         *     already on that case, of the sender's own customer (ticket 32).
         */
        CaseReply: {
            /** Linked To */
            linked_to: string;
            /** Picked By */
            picked_by?: string | null;
            reading?: components["schemas"]["ReplyReading"] | null;
        };
        /**
         * CaseReplyView
         * @description A customer's reply attached to the case by its thread (ticket 32), with
         *     the thread intents a model read in it (ticket 26) and the step code
         *     proposes from that, now.
         *
         *     ``proposal`` is computed from the case's status as it is now, and only for
         *     the newest message of the case's thread, a reply or one Sales sent: an
         *     older one's reading does not pre-select anything. It is a suggestion: the
         *     step is the existing one, which Sales confirms and the server checks as
         *     for any other caller. The quotes are the customer's sentences, shown to a
         *     case reader as the inbox shows the whole mail.
         */
        CaseReplyView: {
            /** Fallback */
            fallback?: ("calls" | "spend" | "time" | "unavailable") | null;
            /** Intents */
            intents: components["schemas"]["IntentView"][];
            /** Linked To */
            linked_to: string;
            /** Message Id */
            message_id: string;
            /** Outcome */
            outcome: ("read" | "unavailable") | null;
            /** Picked By */
            picked_by?: string | null;
            /**
             * Processed At
             * Format: date-time
             */
            processed_at: string;
            /** Prompt */
            prompt: string | null;
            /** Proposal */
            proposal: ("settle_spec" | "decline_customer_rejected_spec" | "resume_review" | "await_revised_po" | "request_correction" | "discuss_spec" | "record_accepted" | "record_declined") | null;
            /** Skills */
            skills?: string[];
        };
        /**
         * CatalogImportView
         * @description An import as the page shows it: who, when, which file, how far.
         */
        CatalogImportView: {
            /** Approval Id */
            approval_id: string | null;
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            catalog_list: components["schemas"]["CatalogList"];
            /**
             * Column Map
             * @default []
             */
            column_map: [
                string,
                string
            ][];
            /** Comment */
            comment: string | null;
            /** Decided At */
            decided_at: string | null;
            /** Decided By */
            decided_by: string | null;
            /** Error */
            error: string | null;
            /** File Name */
            file_name: string | null;
            /** File Sha256 */
            file_sha256: string | null;
            /**
             * Imported At
             * Format: date-time
             */
            imported_at: string;
            /**
             * Imported By
             * Format: uuid
             */
            imported_by: string;
            /** Rejected Count */
            rejected_count: number;
            /** Row Count */
            row_count: number;
            /**
             * Snapshot Id
             * Format: uuid
             */
            snapshot_id: string;
            /**
             * Source
             * @enum {string}
             */
            source: "file" | "erp";
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "parsed" | "failed" | "submitted" | "approved" | "rejected" | "superseded" | "discarded";
            /** Submitted At */
            submitted_at: string | null;
            /** Submitted By */
            submitted_by: string | null;
        };
        /**
         * CatalogInForceView
         * @description Where a list's rows come from now: an approved snapshot, the mock, or
         *     ``none``: no approved snapshot where nothing stands in for one (deployed,
         *     audit finding 1), and then no ``as_of`` either.
         */
        CatalogInForceView: {
            /** As Of */
            as_of: string | null;
            snapshot: components["schemas"]["CatalogImportView"] | null;
            /**
             * Source
             * @enum {string}
             */
            source: "mock" | "file" | "erp" | "none";
        };
        /**
         * CatalogList
         * @description The lists Sales maintains by hand. The ERP's own records (its sales
         *     orders and open YCBG) are not among them: they come from Bravo.
         * @enum {string}
         */
        CatalogList: "customers" | "items" | "convert_list" | "quotations" | "lme" | "base_prices" | "bravo_quotations";
        /** CatalogListStateView */
        CatalogListStateView: {
            /** Can Import */
            can_import: boolean;
            catalog_list: components["schemas"]["CatalogList"];
            /** History */
            history: components["schemas"]["CatalogImportView"][];
            in_force: components["schemas"]["CatalogInForceView"];
            /** Label */
            label: string;
            open: components["schemas"]["CatalogImportView"] | null;
        };
        /**
         * CatalogPreviewView
         * @description A proposed snapshot against the list in force now: rows added,
         *     changed (old to new) and removed, and the rows the file had that will
         *     not be applied.
         */
        CatalogPreviewView: {
            /** Added */
            added: components["schemas"]["DiffRow"][];
            /** Changed */
            changed: components["schemas"]["ChangedRow"][];
            /** Columns */
            columns: string[];
            compared_with: components["schemas"]["CatalogInForceView"];
            /** Rejected */
            rejected: components["schemas"]["RejectedRow"][];
            /** Rejected Count */
            rejected_count: number;
            /** Removed */
            removed: components["schemas"]["DiffRow"][];
            snapshot: components["schemas"]["CatalogImportView"];
            /** Unchanged */
            unchanged: number;
            /** Unknown Headers */
            unknown_headers: string[];
        };
        /** CatalogStateView */
        CatalogStateView: {
            /** Lists */
            lists: components["schemas"]["CatalogListStateView"][];
        };
        /**
         * CatalogUploadBody
         * @description A master-data file (ticket 41): its name and its bytes, base64. The
         *     bytes are decoded here and never opened: the worker reads them in the
         *     reader sandbox.
         */
        CatalogUploadBody: {
            /** Content B64 */
            content_b64: string;
            /** File Name */
            file_name: string;
        };
        /** CellChange */
        CellChange: {
            /** Column */
            column: string;
            /** New */
            new: string;
            /** Old */
            old: string;
        };
        /**
         * CellDifference
         * @description One cell the replay did not reproduce: where (the PIC's file's cell),
         *     what was expected and what came out, and what produced it (the
         *     customer's rule for the column, its step that could not apply, or the
         *     layout). Carries the cells' values: price-bearing, as the key is.
         */
        CellDifference: {
            /** Cell */
            cell: string;
            /** Column */
            column?: string | null;
            /** Expected */
            expected?: string | null;
            /** Got */
            got?: string | null;
            /** Header */
            header?: string | null;
            /** Problem */
            problem: ("value_differs" | "row_missing" | "row_extra" | "row_refused") | ("value_missing" | "not_text" | "not_a_number" | "not_a_date" | "lookup_missing");
            /**
             * Source
             * @enum {string}
             */
            source: "layout" | "rule" | "row";
            /** Step */
            step?: number | null;
        };
        /**
         * ChangeLineBody
         * @description One change line a person types, on the case version they saw.
         */
        ChangeLineBody: {
            /** Case Version */
            case_version: number;
            /**
             * Field
             * @enum {string}
             */
            field: "quantity" | "requested_date";
            /** Line No */
            line_no: number;
            /** Value */
            value: string;
        };
        /**
         * ChangeLineView
         * @description One value a customer's mail asks to change (`ChangeLine`).
         */
        ChangeLineView: {
            anchor: components["schemas"]["TextRange"] | null;
            /** Asked */
            asked: string;
            /** Blocked */
            blocked: ("no_such_line" | "unit_differs" | "printed_schedules") | null;
            /** Decided At */
            decided_at: string | null;
            /** Decided By */
            decided_by: string | null;
            /**
             * Field
             * @enum {string}
             */
            field: "quantity" | "requested_date";
            /** Held */
            held: string | null;
            /** Line No */
            line_no: number;
            /**
             * Read By
             * @enum {string}
             */
            read_by: "table" | "model" | "person";
            /** Reason */
            reason: string | null;
            /** Seq */
            seq: number;
            /**
             * State
             * @enum {string}
             */
            state: "open" | "confirmed" | "rejected";
            /** Unit */
            unit: string | null;
            /** Written */
            written: string;
        };
        /**
         * ChangeRejectBody
         * @description Why one change line is rejected, in the person's words.
         */
        ChangeRejectBody: {
            /** Case Version */
            case_version: number;
            /** Reason */
            reason: string;
        };
        /**
         * ChangeRequestBody
         * @description A change request from one of the order's replies (ticket 27): the
         *     mail, and any line the person types besides what DW1 reads, on the
         *     case version the person saw.
         */
        ChangeRequestBody: {
            /** Case Version */
            case_version: number;
            /**
             * Lines
             * @default []
             */
            lines: components["schemas"]["TypedChange"][];
            /** Message Id */
            message_id: string;
        };
        /**
         * ChangeRequestResult
         * @description What a change-request decision returns: the request as it now stands
         *     and the case's version after it (the next decision names it).
         */
        ChangeRequestResult: {
            /** Case Version */
            case_version: number;
            request: components["schemas"]["ChangeRequestView"];
        };
        /**
         * ChangeRequestView
         * @description A change request on the order (ticket 27, dw_sales ADR 0010), with
         *     the mail's newest part its anchors index into: the customer's own words.
         *     The mail may state a price, so its text is served only to a holder of
         *     `sales.price.read`, as the mail text of a PO read from the body is; for
         *     anyone else it is absent, and the lines' own words stand.
         */
        ChangeRequestView: {
            /** Lines */
            lines: components["schemas"]["ChangeLineView"][];
            /** Message Id */
            message_id: string;
            /**
             * Opened At
             * Format: date-time
             */
            opened_at: string;
            /**
             * Opened By
             * Format: uuid
             */
            opened_by: string;
            /** Prompt */
            prompt: string | null;
            /** Reading */
            reading: ("read" | "unavailable") | null;
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            /**
             * State
             * @enum {string}
             */
            state: "open" | "queued" | "closed";
            /** Text */
            text: string | null;
            /** Unread */
            unread: number;
        };
        /** ChangedRow */
        ChangedRow: {
            /** Changes */
            changes: components["schemas"]["CellChange"][];
            /** Key */
            key: string;
        };
        /**
         * CheckView
         * @description Code's check of the model's answer: passed, refused with the reason
         *     code, or not run because no answer came.
         */
        CheckView: {
            /** Reason Code */
            reason_code: string | null;
            /**
             * Result
             * @enum {string}
             */
            result: "passed" | "refused" | "not_run";
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
        /**
         * ColumnRule
         * @description One column of the upload file, by its letter in the tenant's layout:
         *     where its value starts (a field of the normal reading, or the customer's
         *     record; none only where the first step is a constant) and the steps it
         *     then goes through, in order.
         */
        ColumnRule: {
            /** Column */
            column: string;
            /** Customer */
            customer?: ("order_type" | "delivery_term" | "delivery_mode" | "destination" | "shipment_type") | null;
            /** Field */
            field?: ("row_no" | "customer_code" | "po_no" | "revision" | "po_date" | "received_date" | "currency" | "usd_rate" | "line_no" | "customer_item_code" | "prv_code" | "description" | "quantity" | "uom" | "unit_price" | "amount" | "requested_date" | "suggested_delivery_date" | "first_confirmed_date" | "confirmed_date") | null;
            /**
             * Steps
             * @default []
             */
            steps: (components["schemas"]["Copy"] | components["schemas"]["Constant"] | components["schemas"]["Lookup"] | components["schemas"]["UnitFactor"] | components["schemas"]["ShiftDays"] | components["schemas"]["Round"] | components["schemas"]["Cut"] | components["schemas"]["Concat"] | components["schemas"]["Multiply"])[];
        };
        /**
         * Concat
         * @description Appends the values of other fields, each after the separator.
         */
        Concat: {
            /**
             * Separator
             * @default
             * @enum {string}
             */
            separator: "" | " " | "-" | "/" | "_" | "." | ", ";
            /** Sources */
            sources: ("row_no" | "customer_code" | "po_no" | "revision" | "po_date" | "received_date" | "currency" | "usd_rate" | "line_no" | "customer_item_code" | "prv_code" | "description" | "quantity" | "uom" | "unit_price" | "amount" | "requested_date" | "suggested_delivery_date" | "first_confirmed_date" | "confirmed_date")[];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "concat";
        };
        /** ConfirmBody */
        ConfirmBody: {
            /** Case Version */
            case_version: number;
            /** Delivery Dates */
            delivery_dates: components["schemas"]["LineDate"][];
            /** Sent Message Id */
            sent_message_id?: string | null;
        };
        /**
         * ConfirmationCopyView
         * @description A message Sales sent on the case's thread carrying the processed
         *     Excel DW1 made at this case version (by sha256), while the confirmation
         *     is ahead of the order: it proposes "Ghi đã gửi xác nhận", from that
         *     mail's time (ticket 28). A suggestion: the PIC records it.
         */
        ConfirmationCopyView: {
            /** Message Id */
            message_id: string;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Subject */
            subject: string;
        };
        /**
         * ConfirmationView
         * @description The confirmation that left (ticket 28): when (the clock of silence),
         *     the sent copy it was recorded from, and, for a customer with days of
         *     silence, the term and the instant it counts as agreement. None of the
         *     two: never by silence.
         */
        ConfirmationView: {
            /** Implied From */
            implied_from: string | null;
            /** Message Id */
            message_id: string | null;
            /**
             * Sent At
             * Format: date-time
             */
            sent_at: string;
            term: components["schemas"]["ImpliedTermView"] | null;
        };
        /**
         * ConfirmedView
         * @description A confirmed decision: DW1's sentence, and the case's new version.
         */
        ConfirmedView: {
            /** Answer */
            answer: string;
            /** Case Version */
            case_version: number;
        };
        /**
         * Constant
         * @description The value is this fixed text.
         */
        Constant: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "constant";
            /** Value */
            value: string;
        };
        /**
         * ConversationView
         * @description A conversation as its person sees it; before its first turn, empty.
         */
        ConversationView: {
            case: components["schemas"]["CaseRefView"] | null;
            /** Turns */
            turns: components["schemas"]["TurnView"][];
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
         * ConvertGap
         * @description One customer code Bravo does not answer with an approved row.
         */
        ConvertGap: {
            /** Bravo Prv Code */
            bravo_prv_code?: string | null;
            /** Customer Code */
            customer_code: string;
            /** Customer Item Code */
            customer_item_code: string;
            /** Prv Code */
            prv_code?: string | null;
            /** Recorded At */
            recorded_at?: string | null;
            /**
             * State
             * @enum {string}
             */
            state: "not_in_bravo" | "waiting_in_bravo";
        };
        /**
         * ConvertGapsView
         * @description The gaps, and whether an approved Bravo convert list was read at all:
         *     without one, nothing can be said to be missing from it.
         */
        ConvertGapsView: {
            /** As Of */
            as_of: string | null;
            /** Bravo Read */
            bravo_read: boolean;
            /** Gaps */
            gaps: components["schemas"]["ConvertGap"][];
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
         * Copy
         * @description Keeps the value as it is.
         */
        Copy: {
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "copy";
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
        /**
         * Coverage
         * @description How far this slice takes the step.
         * @enum {string}
         */
        Coverage: "yes" | "suggestion" | "mock" | "out";
        /** CoverageView */
        CoverageView: {
            /** Checks Run */
            checks_run: number;
            /** Findings */
            findings: number;
            /**
             * Forecast Rows
             * @default 0
             */
            forecast_rows: number;
            /** Lines Printed */
            lines_printed: number;
            /** Lines Read */
            lines_read: number;
            /** Regions */
            regions: string[];
            /** Unchecked Regions */
            unchecked_regions: string[];
        };
        /**
         * CustomerNotationBody
         * @description How the customer writes one kind, as a person states it (ticket 37):
         *     the kind and its value, checked against the values the kind holds.
         */
        CustomerNotationBody: {
            /**
             * Kind
             * @enum {string}
             */
            kind: "decimal_mark" | "date_order" | "dollar_sign" | "yen_sign";
            /** Value */
            value: string;
        };
        /**
         * CustomerNotationView
         * @description A customer's notation: each kind known, what it rests on, and the
         *     values each kind may hold (the platform's one list, so a screen offers
         *     exactly what the server takes).
         */
        CustomerNotationView: {
            /** Choices */
            choices: {
                [key: string]: string[];
            };
            /** Customer Code */
            customer_code: string;
            /** Entries */
            entries: components["schemas"]["NotationEntryView"][];
        };
        /**
         * CustomerReminderView
         * @description A draft, or why there is none; always marked as the model's.
         */
        CustomerReminderView: {
            /**
             * Asked On
             * Format: date
             */
            asked_on: string;
            /** Body */
            body?: string | null;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Language */
            language?: string | null;
            /** Model Profile */
            model_profile?: string | null;
            /** Prompt Ref */
            prompt_ref?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "drafted" | "unavailable" | "refused";
            /** Subject */
            subject?: string | null;
            /**
             * To
             * @default []
             */
            to: string[];
        };
        /**
         * CustomerSalesOrderRules
         * @description One customer's columns: each named once.
         */
        CustomerSalesOrderRules: {
            /** Columns */
            columns: components["schemas"]["ColumnRule"][];
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
        /**
         * Cut
         * @description Keeps the characters from ``start`` to before ``end`` (from 0; a
         *     negative number counts from the end; none: the start or the end).
         */
        Cut: {
            /** End */
            end?: number | null;
            /** Start */
            start?: number | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "cut";
        };
        /** DayStepView */
        DayStepView: {
            /** Automatic */
            automatic: number;
            /** Handled */
            handled: number;
            step: components["schemas"]["ModelStep"];
            /** To Person */
            to_person: number;
        };
        /** DayView */
        DayView: {
            /**
             * Day
             * Format: date
             */
            day: string;
            /** Steps */
            steps: components["schemas"]["DayStepView"][];
        };
        /**
         * DecisionConfirmBody
         * @description The PIC confirms the decision a turn stated (ticket 56): its hash,
         *     which binds the confirmation to exactly the words said. What is decided
         *     is the stored turn's, never anything this body sends.
         */
        DecisionConfirmBody: {
            /** Content Hash */
            content_hash: string;
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
         * Demonstration
         * @description One decided line a version shows: the customer's description and the
         *     PRV code a person kept. The reading shows the code's attributes from the
         *     item master, never the code (`model_reading.shown_lines`).
         */
        Demonstration: {
            /** Case Id */
            case_id?: string | null;
            /** Customer Code */
            customer_code?: string | null;
            /** Description */
            description: string;
            /** Label Id */
            label_id?: string | null;
            /** Prv Code */
            prv_code: string;
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
            /** Confidence */
            confidence?: number | null;
            /** Gate */
            gate?: ("person" | "shadow" | "audit" | "applied") | null;
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
        /**
         * DesignBasePriceView
         * @description A QUOTE line's BP as Bravo's "Danh mục Base price" holds it (ticket
         *     11), for a price reader only: ``found`` False is a BP code the list read
         *     does not hold (B21 exports the latest BPs only), never a blank price.
         */
        DesignBasePriceView: {
            /** As Of */
            as_of?: string | null;
            /** Base Price */
            base_price?: string | null;
            /** Bp Code */
            bp_code: string;
            /** Bp Date */
            bp_date?: string | null;
            /** Bp Unit */
            bp_unit?: string | null;
            /** Copper Kg */
            copper_kg?: string | null;
            /** Found */
            found: boolean;
            /** Line No */
            line_no: number;
            /** Lme Of Bp */
            lme_of_bp?: string | null;
            /** Specification */
            specification?: string | null;
        };
        /**
         * DesignCheck
         * @description Design's result on a whole YCBG, read from Bravo (ticket 16), never
         *     written there: Bravo's status is Design's to close. Read from the YCBG
         *     export a person uploaded (``file_sha256``, ``read_by``) until the
         *     vendor's API reads a request back by its number (R13).
         */
        DesignCheck: {
            /** File Sha256 */
            file_sha256: string;
            /** Lines */
            lines: components["schemas"]["DesignCheckLine"][];
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
            snapshot?: components["schemas"]["ExportSnapshot"] | null;
            /** Ycbg No */
            ycbg_no: string;
        };
        /**
         * DesignCheckLine
         * @description Design's result on one line of the YCBG, as Bravo holds it once the
         *     line is closed: QUOTE with the BP code it is quoted under, or DECLINE
         *     with Design's reason.
         */
        DesignCheckLine: {
            /** Bp Code */
            bp_code?: string | null;
            /** Bp Unit */
            bp_unit?: string | null;
            /** Complete Date */
            complete_date?: string | null;
            /** Copper Kg Per Bp Unit */
            copper_kg_per_bp_unit?: string | null;
            /** Line No */
            line_no: number;
            /** Places */
            places?: {
                [key: string]: string;
            };
            /** Reason */
            reason?: string | null;
            /** Row */
            row?: number | null;
            /** Spec No */
            spec_no?: string | null;
            /**
             * Verdict
             * @enum {string}
             */
            verdict: "quote" | "decline";
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
            attachment_id: string | null;
            /** Confirmed By */
            confirmed_by?: string | null;
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
        /**
         * DesignRequestStateView
         * @description Sales asked Design to create a PRV code for this line, and waits (ticket 06).
         */
        DesignRequestStateView: {
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
            /** Line No */
            line_no: number;
        };
        /**
         * DesignRequestView
         * @description The request to Design for one line, drafted from the case for a person
         *     to send, and the codes Design named since it was recorded sent (who
         *     recorded it, and when, is the order's own `design_requests`).
         */
        DesignRequestView: {
            /** Body */
            body: string;
            /** Case Version */
            case_version: number;
            /** Line No */
            line_no: number;
            /**
             * Named
             * @default []
             */
            named: components["schemas"]["NamedCodeView"][];
            /** Nearest */
            nearest: components["schemas"]["NearestCodeView"][];
            /** Subject */
            subject: string;
            /** Template Ref */
            template_ref: string;
            /** To */
            to: string[];
        };
        /** DesignTextLineView */
        DesignTextLineView: {
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
        /**
         * DesignTextReadingView
         * @description What DW1 read of a Design reply written in the mail, for Sales to
         *     confirm; always marked as the model's.
         */
        DesignTextReadingView: {
            /** Case Id */
            case_id?: string | null;
            /**
             * Lines
             * @default []
             */
            lines: components["schemas"]["DesignTextLineView"][];
            /** Message Id */
            message_id: string;
            /** Model Profile */
            model_profile?: string | null;
            /** Prompt Ref */
            prompt_ref?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "read" | "no_case" | "unavailable";
            /** Ycbg No */
            ycbg_no?: string | null;
        };
        /**
         * DiffRow
         * @description A record as its template row prints it.
         */
        DiffRow: {
            /** Cells */
            cells: {
                [key: string]: string;
            };
            /** Key */
            key: string;
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
         * DraftProblem
         * @description Why a draft is not, or not wholly, what the template says. Names a
         *     field, a cell and that cell's own text: never a word of the model's.
         */
        DraftProblem: {
            /**
             * Code
             * @enum {string}
             */
            code: "column_unmapped" | "header_not_in_template" | "header_too_long" | "header_ambiguous" | "header_twice" | "field_twice" | "source_invalid" | "constant_not_in_template" | "required_missing" | "layout_invalid" | "sheet_name_invalid" | "model_unavailable" | "model_not_configured" | "model_quota" | "nothing_understood" | "path_unknown" | "type_changed" | "placeholder_changed" | "digit_invented" | "document_invalid";
            /** Field */
            field?: ("row_no" | "customer_code" | "po_no" | "revision" | "po_date" | "received_date" | "currency" | "usd_rate" | "line_no" | "customer_item_code" | "prv_code" | "description" | "quantity" | "uom" | "unit_price" | "amount" | "requested_date" | "suggested_delivery_date" | "first_confirmed_date" | "confirmed_date") | null;
            /** Header */
            header?: string | null;
            /** Ref */
            ref?: string | null;
            /** Where */
            where?: string | null;
        };
        /**
         * EdgeAction
         * @description What makes a case move: the domain method that moves it.
         * @enum {string}
         */
        EdgeAction: "check" | "close" | "start_review" | "prepare" | "request_correction" | "revise" | "resume_review" | "record_bravo_entry" | "edit" | "cross_check" | "return" | "confirm" | "record_agreement" | "record_decline" | "apply_change" | "draft_ycbg" | "record_ycbg" | "send_to_design" | "record_design_reply" | "discuss_spec" | "settle_spec" | "price" | "submit" | "approve" | "send" | "record_master_list" | "decline";
        /**
         * EdgeGuard
         * @description What the domain refuses a move without.
         * @enum {string}
         */
        EdgeGuard: "blocking_findings" | "ask_customer" | "entry_compared" | "approval" | "maker_checker" | "cross_check_not_required" | "export_control_hold" | "pc_confirmed_date" | "request_findings" | "implied_days";
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
            orders: components["schemas"]["OrderedLineView"][] | null;
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
            suggestion?: components["schemas"]["SuggestionView"] | null;
            target_price: components["schemas"]["Amount"] | null;
        };
        /**
         * ExampleFileBody
         * @description One file of a worked example (ticket 38): its name and its bytes,
         *     base64, decoded here and never opened: the worker reads it in the reader
         *     sandbox.
         */
        ExampleFileBody: {
            /** Content B64 */
            content_b64: string;
            /** File Name */
            file_name: string;
        };
        /**
         * ExampleSubmissionBody
         * @description "Gửi duyệt": the number the new version of the customers' rules takes.
         */
        ExampleSubmissionBody: {
            /** Version */
            version: string;
        };
        /**
         * ExportMapping
         * @description A customer portal's export (ticket 18): the title of each column read,
         *     the column saying whether a row is a firm order, and the values of it
         *     that mean firm. Every other row is a forecast, counted and never ordered.
         *     The export prints no currency, so the person mapping it states the one
         *     the customer orders in; each PO read with it has that value flagged
         *     `not_printed`, for Sales to confirm.
         */
        ExportMapping: {
            /**
             * Currency
             * @enum {string}
             */
            currency: "USD" | "VND" | "JPY";
            /** Customer Item Code */
            customer_item_code: string;
            /**
             * Date Format
             * @default %y-%m-%d
             * @enum {string}
             */
            date_format: "%d/%m/%Y" | "%Y-%m-%d" | "%d-%m-%Y" | "%m/%d/%Y" | "%d.%m.%Y" | "%Y/%m/%d" | "%y-%m-%d";
            /**
             * Decimal Separator
             * @default .
             * @enum {string}
             */
            decimal_separator: "." | ",";
            /** Description */
            description?: string | null;
            /** Firm Values */
            firm_values: string[];
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "csv";
            /** Order Type */
            order_type: string;
            /** Po Date */
            po_date: string;
            /** Po No */
            po_no: string;
            /** Quantity */
            quantity: string;
            /** Requested Date */
            requested_date: string;
            /**
             * Thousands Separator
             * @default ,
             * @enum {string}
             */
            thousands_separator: "," | "." | " " | "none";
            /** Unit Price */
            unit_price?: string | null;
            /** Uom */
            uom: string;
        };
        /**
         * ExportOutcome
         * @description What became of one document of an export: its number (a YCBG's, a
         *     customer PO's) and the case, never a value of the file.
         */
        ExportOutcome: {
            /** Case Id */
            case_id?: string | null;
            /**
             * Declined
             * @default false
             */
            declined: boolean;
            /**
             * Differences
             * @default 0
             */
            differences: number;
            /** Key */
            key: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "recorded" | "unchanged" | "pending" | "no_case" | "lines_differ" | "changed" | "unreadable" | "equal" | "differs" | "several_cases" | "several_sos";
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
         * ExportSnapshot
         * @description The rows of one YCBG as Bravo's "RFQ List" export held them (ticket
         *     11): the title row and the request's own rows, never another request's,
         *     since one export lists every open YCBG and other customers' among them.
         *     Kept on the case instead of the file, it is the place Design's values
         *     are anchored in and what the source pane draws; ``file_sha256`` binds it
         *     to the export it was read from.
         */
        ExportSnapshot: {
            /** File Sha256 */
            file_sha256: string;
            /** Rows */
            rows: components["schemas"]["ExportSnapshotRow"][];
            /** Sheet */
            sheet: string;
        };
        /**
         * ExportSnapshotRow
         * @description One row of a Bravo export as the reader sandbox read it, as text.
         */
        ExportSnapshotRow: {
            /** Cells */
            cells: (string | null)[];
            /** Row */
            row: number;
        };
        /**
         * FindingCode
         * @description The order checks of the spec's findings table, one code each.
         * @enum {string}
         */
        FindingCode: "code_unmapped" | "code_ambiguous" | "price_mismatch" | "currency_mismatch" | "uom_mismatch" | "quotation_missing" | "lme_band_mismatch" | "moq_violation" | "pack_multiple" | "line_total_mismatch" | "value_uncertain" | "customer_unknown" | "duplicate_po" | "requested_date_short_lt" | "missing_noc_esf" | "revised_po" | "revision_without_base" | "customer_temporary" | "sender_unverified" | "legacy_encoding" | "requested_date_missing" | "reel_length_mismatch" | "spec_mismatch" | "files_disagree" | "delivery_term_mismatch";
        /**
         * FindingExplanationView
         * @description An explanation, or why there is none; always marked as the model's.
         */
        FindingExplanationView: {
            /** Check */
            check?: string | null;
            /** Explanation */
            explanation?: string | null;
            /** Finding Key */
            finding_key: string;
            /** Model Profile */
            model_profile?: string | null;
            /** Prompt Ref */
            prompt_ref?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "explained" | "unavailable" | "refused";
        };
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
         * FlaggedValueView
         * @description A flagged value as the case page is served it: the field, why it is
         *     flagged, and a model's confidence. Never the gate (ticket 44): a value
         *     sampled for the audit must reach its person as any other does, or the
         *     audit would not be blind.
         */
        FlaggedValueView: {
            /** Confidence */
            confidence?: number | null;
            /** Field */
            field: string;
            flag: components["schemas"]["RegionFlag"];
        };
        /**
         * FollowupDraftView
         * @description A draft, or why there is none; always marked as the model's.
         */
        FollowupDraftView: {
            /** Body */
            body?: string | null;
            /** Customer Code */
            customer_code: string;
            /** Language */
            language?: string | null;
            /** Model Profile */
            model_profile?: string | null;
            /** Prompt Ref */
            prompt_ref?: string | null;
            /** Prv Code */
            prv_code: string;
            /**
             * Status
             * @enum {string}
             */
            status: "drafted" | "unavailable" | "refused";
            /** Subject */
            subject?: string | null;
            /**
             * To
             * @default []
             */
            to: string[];
        };
        /**
         * FromOrder
         * @description The order case a quote case was opened from (ticket 09): its id and
         *     PO number, stamped when the quote opened, so both cases name each other.
         */
        FromOrder: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Po No */
            po_no: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * HandledRequest
         * @description The note a person may leave when they mark a message handled.
         */
        HandledRequest: {
            /** Note */
            note?: string | null;
        };
        /**
         * HandledView
         * @description Where a routed message stands after a mark or a reopen.
         */
        HandledView: {
            /** Handled At */
            handled_at: string | null;
            /** Handled By */
            handled_by: string | null;
            /** Handled Note */
            handled_note: string | null;
            /** Message Id */
            message_id: string;
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
            /** Kind Label */
            kind_label?: string | null;
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
             * Quantity From Record
             * @default false
             */
            quantity_from_record: boolean;
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
            /** Skill */
            skill?: string | null;
            /** Skill Kind */
            skill_kind?: string | null;
            /** So No */
            so_no?: string | null;
            /** To */
            to?: ("pc" | "qa") | null;
        };
        /**
         * HandoffDraftView
         * @description A routed message's hand-off as code wrote it from the template, for
         *     Sales to review, edit and send from their own mailbox (ticket 33). ``to``
         *     names the team, never an address: Sales picks the recipients.
         *     ``kind_label``: the tenant's hand-off skill's words for its kind, where
         *     the skill read it and gives some (ticket 42 family 5).
         */
        HandoffDraftView: {
            /** Body */
            body: string;
            /** Kind Label */
            kind_label?: string | null;
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
            /**
             * From Record
             * @default []
             */
            from_record: ("quantity" | "date")[];
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
         * HeadSettingView
         * @description A setting of the head's short list: where it is, and its sentence.
         */
        HeadSettingView: {
            key: components["schemas"]["RuleKey"];
            /** Path */
            path: string;
            /** Sentence */
            sentence: string;
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
        /**
         * ImpliedTermView
         * @description A customer's days of silence that count as agreement, as the rules
         *     stamped on the case gave them when the confirmation left (ticket 28).
         */
        ImpliedTermView: {
            /**
             * Counted From
             * @enum {string}
             */
            counted_from: "confirmation_sent" | "po_date";
            /**
             * Day Count
             * @enum {string}
             */
            day_count: "calendar" | "business";
            /** Days */
            days: number;
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
         *
         *     Read with the tenant's mail-classifying skill (ticket 42), ``kind`` is a
         *     kind that skill names, ``skill`` the version it was read with,
         *     ``routed_as`` the legal route the skill gave that kind and ``kind_label``
         *     the skill's words for it, where it gives some. Read with the one call,
         *     ``kind`` is one of the platform's kinds and is its own route.
         */
        IntentReading: {
            /** Kind */
            kind?: string | null;
            /** Kind Label */
            kind_label?: string | null;
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
            /** Routed As */
            routed_as?: ("po" | "quote_request" | "design_reply" | "reply_to_case" | "delivery_change" | "complaint" | "sample_request" | "portal_notice" | "other") | null;
            /** Rules */
            rules: string;
            /** Skill */
            skill?: string | null;
        };
        /**
         * IntentView
         * @description One thread intent a model read and code kept (ticket 26), with the
         *     sentences it stands on.
         */
        IntentView: {
            /**
             * Intent
             * @enum {string}
             */
            intent: "sends_po" | "requests_change" | "cancels" | "accepts" | "rejects" | "asks" | "adds_info" | "sends_rfq" | "unclear";
            /** Quotes */
            quotes: string[];
        };
        /**
         * InternalApplyBody
         * @description Proterial's own change as a person applies it (ticket 10): why, and
         *     each line with the deliveries PC now gives it.
         */
        InternalApplyBody: {
            /** Case Version */
            case_version: number;
            /** Lines */
            lines: components["schemas"]["InternalLine"][];
            /**
             * Reason
             * @enum {string}
             */
            reason: "overcapacity" | "ng" | "short_stock" | "other";
        };
        /**
         * InternalDelivery
         * @description One delivery a person applies: how much, on PC's date.
         */
        InternalDelivery: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Quantity */
            quantity: number | string;
        };
        /**
         * InternalDeliveryView
         * @description A delivery as read: a value None where the paste leaves it to a person.
         */
        InternalDeliveryView: {
            /** Date */
            date: string | null;
            /** Date Words */
            date_words: string;
            /** Quantity */
            quantity: string | null;
            /** Quantity Words */
            quantity_words: string | null;
        };
        /**
         * InternalLine
         * @description One line a person applies, with its deliveries in PC's order; or
         *     ``cancelled``, PC cancelling the whole line, with none. A line without
         *     a delivery is a cancel only where it says so: an empty list alone is
         *     refused, never read as one.
         */
        InternalLine: {
            /**
             * Cancelled
             * @default false
             */
            cancelled: boolean;
            /**
             * Deliveries
             * @default []
             */
            deliveries: components["schemas"]["InternalDelivery"][];
            /** Line No */
            line_no: number;
        };
        /**
         * InternalLineView
         * @description A line as read. ``line_no`` None: the words name no line of the order,
         *     refused. ``held_*``: the line as the order holds it, beside what PC gives.
         */
        InternalLineView: {
            /** Deliveries */
            deliveries: components["schemas"]["InternalDeliveryView"][];
            /**
             * Held Deliveries
             * @default []
             */
            held_deliveries: components["schemas"]["UpdateDeliveryView"][];
            /** Held Quantity */
            held_quantity?: string | null;
            /** Line No */
            line_no: number | null;
            /** Problem */
            problem: ("no_such_line" | "unread" | "quantity_raised" | "printed_schedules") | null;
            /** Uom */
            uom?: string | null;
            /** Words */
            words: string;
        };
        /**
         * InternalReadBody
         * @description PC's mail as Sales pasted it into "Thay đổi nội bộ" (ticket 10): read,
         *     never stored, to DW1's reading limit (`pc_dates.MAX_TEXT`).
         */
        InternalReadBody: {
            /** Case Version */
            case_version: number;
            /** Text */
            text: string;
        };
        /**
         * InternalReadView
         * @description What DW1 read of the paste, or why nothing: always marked as the
         *     model's on the page, and nothing of it is kept.
         */
        InternalReadView: {
            /**
             * Dropped
             * @default 0
             */
            dropped: number;
            /**
             * Lines
             * @default []
             */
            lines: components["schemas"]["InternalLineView"][];
            /** Model Profile */
            model_profile?: string | null;
            /** Prompt Ref */
            prompt_ref?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "read" | "nothing" | "unavailable" | "off";
            /**
             * Text Max
             * @default 8000
             */
            text_max: number;
        };
        /** ItemBasisView */
        ItemBasisView: {
            /** Moq */
            moq: string | null;
            /** Pack Multiple */
            pack_multiple: string | null;
            /** Prv Code */
            prv_code: string;
            /** Standard Lead Time Days */
            standard_lead_time_days: number | null;
            /** Uom */
            uom: string | null;
        };
        /**
         * ItemView
         * @description An item as the master-data page and the candidate picker show it.
         *     None: the item master does not hold the value (Bravo's holds no MOQ,
         *     lead time or attribute but those its name states, ticket 36).
         */
        ItemView: {
            /** Cores */
            cores: number | null;
            /** Family */
            family: string | null;
            /** Gauge */
            gauge: string | null;
            /** Moq */
            moq: string | null;
            /** Name */
            name: string | null;
            /** Pack Multiple */
            pack_multiple: string | null;
            /** Prv Code */
            prv_code: string;
            /** Spec No */
            spec_no: string | null;
            /** Standard Lead Time Days */
            standard_lead_time_days: number | null;
            /** Unit */
            unit: string | null;
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
         * LabelSummaryView
         * @description Per step, the cases people decided on its proposals (ticket 43).
         */
        LabelSummaryView: {
            /** Steps */
            steps: components["schemas"]["StepLabelView"][];
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
         * LatencyView
         * @description The step's time per message, nearest-rank percentiles.
         */
        LatencyView: {
            /** P50 Ms */
            p50_ms: number | null;
            /** P95 Ms */
            p95_ms: number | null;
            /** Samples */
            samples: number;
        };
        /**
         * LayoutBody
         * @description A mapping of the form one message's attachment prints (ticket 30), or
         *     of a portal's export's columns (ticket 18).
         */
        LayoutBody: {
            /** Attachment Id */
            attachment_id: string;
            /** Mapping */
            mapping: components["schemas"]["LayoutMapping"] | components["schemas"]["ExportMapping"];
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
            date_format: "%d/%m/%Y" | "%Y-%m-%d" | "%d-%m-%Y" | "%m/%d/%Y" | "%d.%m.%Y" | "%Y/%m/%d" | "%y-%m-%d";
            /**
             * Decimal Separator
             * @default .
             * @enum {string}
             */
            decimal_separator: "." | ",";
            /** Delivery Term */
            delivery_term?: string | null;
            /** Description */
            description: string;
            /**
             * @description discriminator enum property added by openapi-typescript
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
             * Forecast Rows
             * @default 0
             */
            forecast_rows: number;
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
            kind: "excel" | "pdf" | "csv";
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
            /** Approval Id */
            approval_id: string | null;
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
            /** Mapping */
            mapping: components["schemas"]["LayoutMapping"] | components["schemas"]["ExportMapping"];
            /** Origin */
            origin: string;
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
        /**
         * LearnProblem
         * @description Why a proposal was refused: a code, the column, a path. Never a word
         *     of the model's, never a cell's value.
         */
        LearnProblem: {
            /**
             * Code
             * @enum {string}
             */
            code: "header_differs" | "column_outside_layout" | "rule_invalid" | "constant_not_alone" | "constant_not_in_file" | "constant_from_po" | "model_unavailable" | "model_not_configured" | "model_quota";
            /** Column */
            column?: string | null;
            /** Where */
            where?: string | null;
        };
        /**
         * LeftBlank
         * @description A column neither the layout nor the rules fill: left for the person
         *     who pastes, as in the file a case draws. Not compared; how many rows of
         *     the PIC's file fill it is shown.
         */
        LeftBlank: {
            /** Column */
            column: string;
            /** Filled Rows */
            filled_rows: number;
            /** Header */
            header: string;
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
        /** LineTrailView */
        LineTrailView: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Line No */
            line_no: number;
            /** Steps */
            steps: components["schemas"]["TrailStepView"][];
        };
        /** LinkedCount */
        LinkedCount: {
            /** Count */
            count: number;
            filter: components["schemas"]["ActivityFilter"];
        };
        /**
         * LiveShareView
         * @description What the step handled in the workspace over the last ``window_days``
         *     days, and how much of it DW1 carried (`StepTally`).
         */
        LiveShareView: {
            /** Automatic */
            automatic: number;
            /** Handled */
            handled: number;
            /** Share */
            share: number | null;
            /** Window Days */
            window_days: number;
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
        /**
         * LockReason
         * @description Why the page shows a field without editing it: served with the field,
         *     worded by the web (`rule-labels.ts`, keyed by these values, so a reason
         *     added here fails its typecheck until it has words).
         * @enum {string}
         */
        LockReason: "model_bar" | "bound_at_build" | "trust" | "two_owners";
        /**
         * Lookup
         * @description The value is what the master data's table holds for it, or for the
         *     field ``key`` where one is named.
         */
        Lookup: {
            /** Key */
            key?: ("row_no" | "customer_code" | "po_no" | "revision" | "po_date" | "received_date" | "currency" | "usd_rate" | "line_no" | "customer_item_code" | "prv_code" | "description" | "quantity" | "uom" | "unit_price" | "amount" | "requested_date" | "suggested_delivery_date" | "first_confirmed_date" | "confirmed_date") | null;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "lookup";
            /**
             * Table
             * @enum {string}
             */
            table: "convert_list" | "item_name" | "item_specification" | "item_standard_length" | "item_unit" | "item_category" | "item_colour";
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
            /**
             * Applied By Dw
             * @default false
             */
            applied_by_dw: boolean;
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
        /**
         * MarkIn
         * @description What a person did with a reminder.
         */
        MarkIn: {
            /** Hours */
            hours?: number | null;
            /**
             * Mark
             * @enum {string}
             */
            mark: "done" | "dismissed" | "snoozed";
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
        /** MeasurementView */
        MeasurementView: {
            /**
             * Measured At
             * Format: date-time
             */
            measured_at: string;
            /** Model */
            model: string;
            /** Passed */
            passed: boolean;
            /** Prompt */
            prompt: string;
            /** Value */
            value: number;
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
            /** Handled At */
            handled_at?: string | null;
            /** Handled By */
            handled_by?: string | null;
            /** Handled Note */
            handled_note?: string | null;
            handoff?: components["schemas"]["Handoff"] | null;
            /** Kind */
            kind: string;
            layout_prefill?: components["schemas"]["LayoutPrefill"] | null;
            /**
             * Order Cases
             * @default []
             */
            order_cases: components["schemas"]["ThreadCaseView"][];
            /**
             * Outgoing
             * @default false
             */
            outgoing: boolean;
            /** Owner */
            owner?: string | null;
            /** Processed At */
            processed_at?: string | null;
            reading?: components["schemas"]["IntentReading"] | null;
            /** Reason */
            reason?: string | null;
            reply?: components["schemas"]["CaseReply"] | null;
            /**
             * Thread Cases
             * @default []
             */
            thread_cases: components["schemas"]["ThreadCaseView"][];
            triage?: components["schemas"]["TriageCardView"] | null;
        };
        /**
         * MessageTextView
         * @description The message's newest part a model read a quotation's request or an
         *     order's PO from, as the case holds it: what its values' ``chars`` index
         *     into. It may state a price.
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
        /**
         * ModelDesignReply
         * @description What the model reads, and what Sales confirms: the YCBG answered and
         *     each line, every value as the mail writes it.
         */
        ModelDesignReply: {
            /** Lines */
            lines: components["schemas"]["ModelReplyLine"][];
            /** Ycbg No */
            ycbg_no: string;
        };
        /** ModelReplyLine */
        ModelReplyLine: {
            /** Bp Code */
            bp_code: string;
            /** Copper Kg Per Km */
            copper_kg_per_km?: string | null;
            /** Line No */
            line_no: number;
            /** Prv Code */
            prv_code?: string | null;
            /** Spec No */
            spec_no: string;
        };
        /**
         * ModelStep
         * @description The DW1 steps a model may take part in: each a switch of `ModelAssist`
         *     by the same name (a test holds the two together), and each with the bar
         *     its live eval must meet before the switch does anything
         *     (`application.model_readiness.BARS`).
         * @enum {string}
         */
        ModelStep: "description_attributes" | "salesorder_skill" | "message_intent" | "rfq_extraction" | "reply_intent" | "request_handoff" | "layout_proposal" | "po_body_extraction" | "change_request" | "thread_agent" | "reply_draft" | "skill_intents" | "skill_mail_kinds" | "skill_document_forms" | "skill_handoffs" | "skill_reply_drafts" | "triage_card" | "internal_change";
        /**
         * Multiply
         * @description Multiplies the value by another field's.
         */
        Multiply: {
            /**
             * Source
             * @enum {string}
             */
            source: "row_no" | "customer_code" | "po_no" | "revision" | "po_date" | "received_date" | "currency" | "usd_rate" | "line_no" | "customer_item_code" | "prv_code" | "description" | "quantity" | "uom" | "unit_price" | "amount" | "requested_date" | "suggested_delivery_date" | "first_confirmed_date" | "confirmed_date";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "multiply";
        };
        /**
         * NamedCodeView
         * @description A code a Design mail names that the item master holds, and the mail.
         */
        NamedCodeView: {
            /** Code */
            code: string;
            /** Description */
            description: string;
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
        };
        /** NearestCodeView */
        NearestCodeView: {
            /** Code */
            code: string;
            /** Description */
            description: string;
        };
        /**
         * NotationEntryView
         * @description One kind of a customer's notation on the master data screen.
         */
        NotationEntryView: {
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
            /** Case Id */
            case_id: string | null;
            /** Case Kind */
            case_kind: ("order" | "quote") | null;
            /** Confirmed */
            confirmed: string | null;
            /** Field */
            field: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "decimal_mark" | "date_order" | "dollar_sign" | "yen_sign";
            /**
             * Source
             * @enum {string}
             */
            source: "confirmed" | "set";
            /** Value */
            value: string;
            /** Written */
            written: string | null;
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
            agreement?: components["schemas"]["AgreementView"] | null;
            /** Assigned To */
            assigned_to: string | null;
            /** Attachment Id */
            attachment_id: string | null;
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
            /**
             * Change Requests
             * @default []
             */
            change_requests: components["schemas"]["ChangeRequestView"][];
            /** Changes */
            changes: components["schemas"]["LineChangeView"][];
            /** Close Reason */
            close_reason: string | null;
            /** Closed At */
            closed_at: string | null;
            /** Closed By */
            closed_by: string | null;
            confirmation?: components["schemas"]["ConfirmationView"] | null;
            confirmation_copy?: components["schemas"]["ConfirmationCopyView"] | null;
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
            /** Delivery Term */
            delivery_term?: string | null;
            derivation?: components["schemas"]["Derivation"] | null;
            /**
             * Design Requests
             * @default []
             */
            design_requests: components["schemas"]["DesignRequestStateView"][];
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
            header_flags: components["schemas"]["FlaggedValueView"][];
            /**
             * Internal Change Open
             * @default false
             */
            internal_change_open: boolean;
            legacy_text_anchor: components["schemas"]["SourceAnchor"] | null;
            /** Lines */
            lines: components["schemas"]["OrderLineView"][];
            /** Makers */
            makers: string[];
            /** Message Id */
            message_id: string;
            /** Name Revision */
            name_revision?: string | null;
            /** Parser Version */
            parser_version: string;
            pc_request?: components["schemas"]["PcRequestStateView"] | null;
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
             * Quote Links
             * @default []
             */
            quote_links: components["schemas"]["QuoteLinkView"][];
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
            /**
             * Thread Before
             * @default []
             */
            thread_before: components["schemas"]["ThreadMessageView"][];
            /**
             * Thread Sent
             * @default []
             */
            thread_sent: components["schemas"]["SentMessageView"][];
            total: components["schemas"]["Amount"] | null;
            total_anchor: components["schemas"]["SourceAnchor"] | null;
            unapplied_decision: components["schemas"]["UnappliedDecisionView"] | null;
            /** Unopened Values */
            unopened_values?: components["schemas"]["UnopenedValue"][] | null;
            update_loop?: components["schemas"]["UpdateLoopView"] | null;
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
            /**
             * Cancelled
             * @default false
             */
            cancelled: boolean;
            /**
             * Changes
             * @default []
             */
            changes: components["schemas"]["AppliedChangeView"][];
            /** Confirmed Delivery Date */
            confirmed_delivery_date: string | null;
            /**
             * Confirmed Delivery Dates
             * @default []
             */
            confirmed_delivery_dates: string[];
            /** Corrections */
            corrections: components["schemas"]["ValueCorrectionView"][];
            /** Customer Item Code */
            customer_item_code: string;
            /** Description */
            description: string;
            /** Flags */
            flags: components["schemas"]["FlaggedValueView"][];
            /** Line No */
            line_no: number;
            mapping: components["schemas"]["MappingView"];
            pc_answer?: components["schemas"]["PcAnswerView"] | null;
            /** Pc Confirmed At */
            pc_confirmed_at: string | null;
            /** Pc Confirmed By */
            pc_confirmed_by: string | null;
            /** Po No */
            po_no?: string | null;
            po_no_anchor?: components["schemas"]["SourceAnchor"] | null;
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
         * OrderQuoteView
         * @description The quote case opened from the order, and the order's next version.
         */
        OrderQuoteView: {
            /** Case Version */
            case_version: number;
            /** Lines */
            lines: number[];
            /**
             * Quote Case Id
             * Format: uuid
             */
            quote_case_id: string;
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
        /**
         * OutboundMailView
         * @description Where one mail stands, for the case page.
         */
        OutboundMailView: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
            /** Error */
            error: ("not_connected" | "write_failed" | "flow_failed" | "no_receipt" | "gone") | null;
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
            /** Settled At */
            settled_at: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "written" | "sent" | "failed" | "stalled";
        };
        /**
         * OutboundMailsView
         * @description Whether DW1 sends mail here at all, and the case's mails.
         */
        OutboundMailsView: {
            /** Enabled */
            enabled: boolean;
            /** Mails */
            mails: components["schemas"]["OutboundMailView"][];
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
         * PcAnswerBody
         * @description PC's answer for one line (ticket 07): its deliveries in PC's order, one
         *     for a line PC delivers at once, several for a line PC splits.
         */
        PcAnswerBody: {
            /** Case Version */
            case_version: number;
            /** Deliveries */
            deliveries: components["schemas"]["PcDeliveryBody"][];
        };
        /**
         * PcAnswerView
         * @description PC's answer for a line and who recorded it (ticket 07).
         */
        PcAnswerView: {
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
            /** Deliveries */
            deliveries: components["schemas"]["PcDeliveryView"][];
        };
        /** PcDateView */
        PcDateView: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Delivery */
            delivery: number;
            /** Line No */
            line_no: number;
            /** Quote */
            quote: string;
        };
        /**
         * PcDatesBody
         * @description PC's mail as Sales pasted it (AI item 7): read, never stored. Its
         *     limit is DW1's reading limit (`pc_dates.MAX_TEXT`, its one owner).
         */
        PcDatesBody: {
            /** Case Version */
            case_version: number;
            /** Text */
            text: string;
        };
        /**
         * PcDatesView
         * @description The dates read, or why there are none; always marked as the model's.
         */
        PcDatesView: {
            /**
             * Dates
             * @default []
             */
            dates: components["schemas"]["PcDateView"][];
            /**
             * Dropped
             * @default 0
             */
            dropped: number;
            /** Model Profile */
            model_profile?: string | null;
            /** Prompt Ref */
            prompt_ref?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "read" | "nothing" | "unavailable";
            /**
             * Unsettled
             * @default 0
             */
            unsettled: number;
        };
        /**
         * PcDeliveryBody
         * @description One delivery of PC's answer: how much, on which date PC gives.
         */
        PcDeliveryBody: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Quantity */
            quantity: number | string;
        };
        /**
         * PcDeliveryView
         * @description One delivery of a line as PC confirmed it (ticket 07).
         */
        PcDeliveryView: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /**
             * First Date
             * Format: date
             */
            first_date: string;
            /** Quantity */
            quantity: string;
        };
        /**
         * PcMailView
         * @description A verified mail that names the order: what Sales may have DW1 read.
         */
        PcMailView: {
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
        };
        /**
         * PcMailsView
         * @description The mails Sales may have DW1 read, and the longest text DW1 reads, a
         *     paste's or a mail's: `MAX_TEXT`, served so the paste box holds no copy of
         *     its own (hardcode audit, finding 22).
         */
        PcMailsView: {
            /** Mails */
            mails: components["schemas"]["PcMailView"][];
            /**
             * Text Max
             * @default 8000
             */
            text_max: number;
        };
        /**
         * PcRequestStateView
         * @description Sales asked PC for these lines' dates, and waits (ticket 07).
         */
        PcRequestStateView: {
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
            /** Lines */
            lines: number[];
        };
        /**
         * PcRequestView
         * @description The request to PC, drafted from the case for a person to copy, and
         *     when DW1 reminds while the case waits on PC (who asked, and when, is the
         *     order's own `pc_request`).
         */
        PcRequestView: {
            /** Body */
            body: string;
            /** Case Version */
            case_version: number;
            /** Lines */
            lines: number[];
            /** Reminder At */
            reminder_at?: string | null;
            /** Subject */
            subject: string;
            /** Template Ref */
            template_ref: string;
        };
        /**
         * PcsCostRow
         * @description One row of the cost sheet sent to GM/BC Manager: what the request
         *     states, and the price cells left blank for the GM (and Purchasing) to
         *     fill. Never a figure the case does not hold.
         */
        PcsCostRow: {
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
            /** Total */
            total?: null;
            /** Unit Price */
            unit_price?: null;
            /** Uom */
            uom: string;
        };
        /**
         * PcsCostSheet
         * @description The request to GM/BC Manager for a pcs price (ticket 05): the request's
         *     lines, and the cost lines of B49's sheet in its order, every amount
         *     blank.
         */
        PcsCostSheet: {
            /** Cost Lines */
            cost_lines: string[];
            /** Customer Code */
            customer_code: string;
            /** Rfq No */
            rfq_no: string | null;
            /** Rows */
            rows: components["schemas"]["PcsCostRow"][];
        };
        /**
         * PcsPriceBody
         * @description The price GM/BC Manager decided, per line (ticket 05); who recorded it
         *     is the caller, never a field of the request.
         */
        PcsPriceBody: {
            /** Case Version */
            case_version: number;
            /** Lines */
            lines: components["schemas"]["PcsPriceLineBody"][];
        };
        /** PcsPriceLineBody */
        PcsPriceLineBody: {
            /** Line No */
            line_no: number;
            /** Unit Price */
            unit_price: number | string;
        };
        /** PcsPriceLineView */
        PcsPriceLineView: {
            /** Line No */
            line_no: number;
            unit_price: components["schemas"]["Amount"];
        };
        /**
         * PcsPriceView
         * @description The GM/BC Manager's price for a pcs case (ticket 05), as recorded;
         *     its amounts hidden from a caller who may not read prices.
         */
        PcsPriceView: {
            /** Lines */
            lines: components["schemas"]["PcsPriceLineView"][];
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
        /** PipelineCard */
        PipelineCard: {
            /** Assigned To */
            assigned_to: string | null;
            /** Awaits Cross Check */
            awaits_cross_check: boolean;
            /** Blocking Findings */
            blocking_findings: number;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /** Customer Code */
            customer_code: string;
            /** Due */
            due: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "order" | "quote";
            /** My Action */
            my_action: string | null;
            /** Open Findings */
            open_findings: number;
            /** Overdue */
            overdue: boolean;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Reference */
            reference: string;
            /** Status */
            status: string;
            /**
             * Status Since
             * Format: date-time
             */
            status_since: string;
        };
        /** PipelineColumn */
        PipelineColumn: {
            /** Cases */
            cases: number;
            /** Hidden */
            hidden: number;
            /** Holder */
            holder: ("dw" | "sales" | "design" | "approver" | "customer") | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "order" | "quote";
            /** Status */
            status: string;
            /** Steps */
            steps: string[];
        };
        /** PipelineView */
        PipelineView: {
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Cards */
            cards: components["schemas"]["PipelineCard"][];
            /** Columns */
            columns: components["schemas"]["PipelineColumn"][];
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
        /**
         * PoUploadBody
         * @description "Tải PO lên": the customer a person chose and the files they dropped.
         *     Who uploads is the caller, never a field here.
         */
        PoUploadBody: {
            /** Customer Code */
            customer_code: string;
            /** Files */
            files: components["schemas"]["UploadFileBody"][];
        };
        /**
         * PoUploadView
         * @description What one upload did: the message it is, whether it was stored now or
         *     already, and its processing job when one was queued.
         */
        PoUploadView: {
            /** Already Stored */
            already_stored: boolean;
            /** Customer Code */
            customer_code: string;
            job: components["schemas"]["ProcessingJobView"] | null;
            /** Message Id */
            message_id: string;
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
         * @description A value the PO's second file shows differently, where it shows it, and
         *     both values as each file prints them (ticket 22; None for a difference
         *     stored before they were kept).
         */
        PrintDifferenceView: {
            anchor: components["schemas"]["SourceAnchor"];
            /** Field */
            field: string;
            /** Line No */
            line_no: number | null;
            /** Ours */
            ours?: string | null;
            /** Theirs */
            theirs?: string | null;
        };
        /** ProcessEdgeView */
        ProcessEdgeView: {
            action: components["schemas"]["EdgeAction"];
            /**
             * Actor
             * @enum {string}
             */
            actor: "dw" | "sales" | "design" | "approver" | "customer";
            /** From */
            from: string;
            /** Guards */
            guards: components["schemas"]["EdgeGuard"][];
            /** To */
            to: string;
        };
        /** ProcessLaneView */
        ProcessLaneView: {
            /** Edges */
            edges: components["schemas"]["ProcessEdgeView"][];
            kind: components["schemas"]["CaseKind"];
            /** Nodes */
            nodes: components["schemas"]["ProcessNodeView"][];
            /** Stateless Steps */
            stateless_steps: string[];
            /** Subflows */
            subflows: components["schemas"]["ProcessSubflowView"][];
        };
        /** ProcessNodeView */
        ProcessNodeView: {
            /** Ba Steps */
            ba_steps: components["schemas"]["BaStepView"][];
            /** Holder */
            holder: ("dw" | "sales" | "design" | "approver" | "customer") | null;
            /** Status */
            status: string;
            /** Steps */
            steps: string[];
        };
        /** ProcessSettingsView */
        ProcessSettingsView: {
            /** Head Settings */
            head_settings: components["schemas"]["HeadSettingView"][];
            /** Lane Settings */
            lane_settings: {
                [key: string]: components["schemas"]["SettingView"][];
            };
            /** Lanes */
            lanes: components["schemas"]["ProcessLaneView"][];
            /** Process Settings */
            process_settings: components["schemas"]["SettingView"][];
            /** Steps */
            steps: components["schemas"]["ProcessStepView"][];
        };
        /** ProcessStepView */
        ProcessStepView: {
            /** Actors */
            actors: components["schemas"]["ActorView"][];
            coverage: components["schemas"]["Coverage"];
            /** Models */
            models: components["schemas"]["StepModelView"][];
            /** Settings */
            settings: components["schemas"]["SettingView"][];
            /** Step Id */
            step_id: string;
            uses: components["schemas"]["UsesView"];
        };
        /** ProcessSubflowView */
        ProcessSubflowView: {
            key: components["schemas"]["SubflowKey"];
            /** Steps */
            steps: components["schemas"]["SubflowStepView"][];
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
        /** ProducedValue */
        ProducedValue: {
            anchor: components["schemas"]["AnchorRef"] | null;
            /** Field */
            field: string;
            /** Line No */
            line_no: number | null;
            /** Value */
            value: string;
        };
        /** ProductionTypeBody */
        ProductionTypeBody: {
            /** Case Version */
            case_version: number;
            /**
             * Kind
             * @enum {string}
             */
            kind: "mass" | "pcs";
        };
        /**
         * PromptReplay
         * @description What the version was proposed on: the labelled cases replayed, how
         *     many the platform's (or the version in force) read right and how many
         *     this one does, and the security cases it passed. Counts only.
         */
        PromptReplay: {
            /** Cases */
            cases: number;
            /** Right After */
            right_after: number;
            /** Right Before */
            right_before: number;
            /** Security Cases */
            security_cases: number;
        };
        /**
         * PromptVersionView
         * @description A tenant's version of the prompt, as the head's page shows it.
         */
        PromptVersionView: {
            /** Approval Id */
            approval_id: string | null;
            /** Comment */
            comment: string | null;
            /** Decided At */
            decided_at: string | null;
            /** Decided By */
            decided_by: string | null;
            /** Demonstrations */
            demonstrations: components["schemas"]["Demonstration"][];
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
            replay: components["schemas"]["PromptReplay"] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "proposed" | "approved" | "rejected" | "superseded";
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * PromptsView
         * @description The description reading's prompt for the tenant: the platform's
         *     prompt the versions add to, the version in force and what it shows, and
         *     every version of the tenant's, newest first.
         */
        PromptsView: {
            /** Demonstrations */
            demonstrations: components["schemas"]["Demonstration"][];
            /** In Force */
            in_force: string;
            /**
             * Layer
             * @enum {string}
             */
            layer: "platform" | "tenant";
            /** Prompt */
            prompt: string;
            /** Step */
            step: string;
            /** Versions */
            versions: components["schemas"]["PromptVersionView"][];
        };
        /** ProposalView */
        ProposalView: {
            /** Case Version */
            case_version: number;
            /** Content Hash */
            content_hash: string;
            /**
             * Decision
             * @enum {string}
             */
            decision: "accepted" | "ask_customer";
            /** Finding Key */
            finding_key: string;
            /** Reason */
            reason: string | null;
        };
        /**
         * QuestionKind
         * @description What DW1 answers (the agreed list), and everything else.
         * @enum {string}
         */
        QuestionKind: "order_status" | "quote_status" | "my_work" | "overdue" | "draft_reply" | "remind_customer" | "explain_thread" | "decide_finding" | "out_of_scope";
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
            coverage: components["schemas"]["QuoteCoverageView"];
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
            design_check?: components["schemas"]["DesignCheck"] | null;
            /** Design Check Source */
            design_check_source?: string | null;
            /** Design Prices */
            design_prices?: components["schemas"]["DesignBasePriceView"][] | null;
            /** Design Replies */
            design_replies: number;
            design_reply: components["schemas"]["DesignReplyView"] | null;
            /** Due Soon */
            due_soon: boolean;
            /** Earlier Pricing */
            earlier_pricing: number;
            /** Evidence */
            evidence: components["schemas"]["EvidenceView"][] | components["schemas"]["Hidden"] | null;
            /** Findings */
            findings: components["schemas"]["QuoteFindingView"][];
            from_order?: components["schemas"]["FromOrder"] | null;
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
            pcs_price?: components["schemas"]["PcsPriceView"] | null;
            pricing: components["schemas"]["PricingView"] | null;
            /** Production Type */
            production_type?: ("mass" | "pcs") | null;
            production_type_set?: components["schemas"]["StampView"] | null;
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
            signed_copy?: components["schemas"]["SignedCopyView"] | null;
            /** Status */
            status: string;
            submission: components["schemas"]["SubmissionView"] | null;
            /**
             * Thread Before
             * @default []
             */
            thread_before: components["schemas"]["ThreadMessageView"][];
            /**
             * Thread Sent
             * @default []
             */
            thread_sent: components["schemas"]["SentMessageView"][];
            /**
             * Waits On Pcs Price
             * @default false
             */
            waits_on_pcs_price: boolean;
            /** Ycbg No */
            ycbg_no: string | null;
            /** Ycbg Recorded At */
            ycbg_recorded_at: string | null;
            /** Ycbg Recorded By */
            ycbg_recorded_by: string | null;
        };
        /**
         * QuoteCoverageView
         * @description The request's coverage statement (`QuoteCase.coverage`).
         */
        QuoteCoverageView: {
            /** Findings */
            findings: number;
            /** Lines Read */
            lines_read: number;
            /** Model Read */
            model_read: number;
            /** Model Read Confirmed */
            model_read_confirmed: number;
            /** Regions */
            regions: string[];
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
            /**
             * Source Not Served
             * @default []
             */
            source_not_served: string[];
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
        /**
         * QuoteLinkView
         * @description A quote case opened from the order (ticket 09): for which lines, who
         *     opened it and when, and its status now. ``status`` None: the caller does
         *     not see that quote case, and is shown only that it exists.
         */
        QuoteLinkView: {
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
            /** Lines */
            lines: number[];
            /**
             * Quote Case Id
             * Format: uuid
             */
            quote_case_id: string;
            /** Status */
            status: string | null;
            /** Waiting */
            waiting: boolean;
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
            /** Due Soon */
            due_soon: boolean;
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
         * ReadBackView
         * @description A case's read-back as its page shows it. ``stale``: the case changed
         *     since it was compared. A unit price's values are left out for a viewer
         *     who may not read prices.
         */
        ReadBackView: {
            /** Prices Hidden */
            prices_hidden: boolean;
            read_back: components["schemas"]["BravoReadBack"] | null;
            /** Stale */
            stale: boolean;
        };
        /**
         * ReadIntent
         * @description One intent code kept, standing on the quotes it located.
         */
        ReadIntent: {
            /**
             * Intent
             * @enum {string}
             */
            intent: "sends_po" | "requests_change" | "cancels" | "accepts" | "rejects" | "asks" | "adds_info" | "sends_rfq" | "unclear";
            /**
             * Quotes
             * @default []
             */
            quotes: components["schemas"]["ReplyQuote"][];
        };
        /** ReasonCount */
        ReasonCount: {
            /** Count */
            count: number;
            filter: components["schemas"]["ActivityFilter"];
            /** Reason Code */
            reason_code: string;
        };
        /**
         * RegionFlag
         * @description Why a value read from a file is not taken on trust (`value_uncertain`).
         *
         *     Each is a place a person looking at the file would not see the value, or
         *     would see something else than the reader read.
         * @enum {string}
         */
        RegionFlag: "hidden_sheet" | "hidden_row" | "hidden_column" | "font_matches_fill" | "formula_without_cached_value" | "model_read" | "new_layout" | "print_differs" | "ocr" | "opened_with_password" | "not_printed" | "notation_from_record";
        /**
         * RejectedRow
         * @description A row that is not applied, and why. ``row`` 0 is the file itself.
         */
        RejectedRow: {
            /** Column */
            column?: string | null;
            /** Reason */
            reason: string;
            /** Row */
            row: number;
        };
        /** ReminderView */
        ReminderView: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            /** Body */
            body: string;
            /** Case Id */
            case_id: string | null;
            /** Customer Term */
            customer_term: boolean;
            /** Followup */
            followup: string;
            /** Link */
            link: string | null;
            /**
             * Notification Id
             * Format: uuid
             */
            notification_id: string;
            /** Stage */
            stage: string;
            /** Title */
            title: string;
        };
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
         * Replay
         * @description The rules applied to the example's PO and compared with the PIC's file.
         */
        Replay: {
            /** Cells Compared */
            cells_compared: number;
            /**
             * Differences
             * @default []
             */
            differences: components["schemas"]["CellDifference"][];
            /** Differences Total */
            differences_total: number;
            /** Layout Ref */
            layout_ref: string;
            /**
             * Left Blank
             * @default []
             */
            left_blank: components["schemas"]["LeftBlank"][];
            /** Rows Expected */
            rows_expected: number;
            /** Rows Got */
            rows_got: number;
        };
        /**
         * ReplyDraftView
         * @description The model's wording, or why there is none; always marked as the model's
         *     on the page, beside the template's draft of ``drafted_as`` where it has
         *     one. ``kind`` is the kind asked for: a platform draft, or a kind of the
         *     tenant's reply-drafts skill worded as ``drafted_as`` (ticket 42 family 5),
         *     with the skill's label and version.
         */
        ReplyDraftView: {
            /** Body */
            body?: string | null;
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /**
             * Drafted As
             * @enum {string}
             */
            drafted_as: "question_answer" | "change_can_do_draft" | "change_options_draft" | "confirmation_draft";
            /**
             * Figures Checked
             * @default 0
             */
            figures_checked: number;
            /** Kind */
            kind: string;
            /** Kind Label */
            kind_label?: string | null;
            /** Language */
            language: string;
            /** Model Profile */
            model_profile?: string | null;
            /**
             * Others
             * @default []
             */
            others: components["schemas"]["ReplyKindOffer"][];
            /** Prompt Ref */
            prompt_ref?: string | null;
            /** Refusal */
            refusal?: ("figure" | "amount" | "address") | null;
            /** Skill */
            skill?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "drafted" | "refused" | "unavailable" | "off";
            /** Subject */
            subject?: string | null;
            /**
             * To
             * @default []
             */
            to: string[];
            /**
             * Unsupported
             * @default []
             */
            unsupported: string[];
        };
        /**
         * ReplyKindOffer
         * @description Another kind of the tenant's reply-drafts skill worded as the same
         *     draft (ticket 42 family 5): what the page offers beside it.
         */
        ReplyKindOffer: {
            /** Kind */
            kind: string;
            /** Label */
            label: string | null;
        };
        /**
         * ReplyQuote
         * @description A sentence of the message that code found, once, in its newest part:
         *     the text as written and where it is (offsets into the NFKC form of
         *     `MessagePart.text`).
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
         * @description What the model reading of a thread message did, stamped where the
         *     message is kept (a reply's disposition, a sent message's record): the
         *     prompt, profile and route of the call, the rules whose switch asked for
         *     it, the outcome and the intents code kept. ``unavailable``: no usable
         *     answer, so the message proposes nothing and Sales reads it.
         */
        ReplyReading: {
            /** Fallback */
            fallback?: ("calls" | "spend" | "time" | "unavailable") | null;
            /**
             * Intents
             * @default []
             */
            intents: components["schemas"]["ReadIntent"][];
            /** Model Profile */
            model_profile: string;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "read" | "unavailable";
            /** Prompt */
            prompt: string;
            /** Route */
            route: string;
            /** Rules */
            rules: string;
            /**
             * Skills
             * @default []
             */
            skills: string[];
        };
        /**
         * RequestReading
         * @description How a model read the request (ticket 29): the prompt, profile and route
         *     of the calls, the rules whose switch asked, and how many calls it took.
         */
        RequestReading: {
            /** Calls */
            calls: number;
            /** Form */
            form?: string | null;
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
            /** Skill */
            skill?: string | null;
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
         * Round
         * @description Rounds a number to ``places`` decimals.
         */
        Round: {
            /**
             * Mode
             * @default half_up
             * @enum {string}
             */
            mode: "half_up" | "down" | "up";
            /** Places */
            places: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "round";
        };
        /**
         * RuleDraftBody
         * @description A company's template to draft a rule version from ("Tạo từ tệp
         *     mẫu"): its name and its bytes, base64, decoded here and never opened.
         */
        RuleDraftBody: {
            /** Content B64 */
            content_b64: string;
            /** File Name */
            file_name: string;
        };
        /**
         * RuleDraftView
         * @description A draft as the rules editor reads it.
         */
        RuleDraftView: {
            /** Document */
            document: {
                [key: string]: unknown;
            } | null;
            /**
             * Draft Id
             * Format: uuid
             */
            draft_id: string;
            /** Error */
            error: string | null;
            /** Evidence */
            evidence: {
                [key: string]: string;
            };
            /** File Name */
            file_name: string;
            /** File Sha256 */
            file_sha256: string;
            /** Focus */
            focus: string | null;
            /** Machine Read */
            machine_read: string[];
            /** Model Profile */
            model_profile: string | null;
            /** Problems */
            problems: components["schemas"]["DraftProblem"][];
            /** Prompt Ref */
            prompt_ref: string | null;
            /** Request */
            request: string | null;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /**
             * Requested By
             * Format: uuid
             */
            requested_by: string;
            rule_key: components["schemas"]["RuleKey"];
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "ready" | "refused" | "unavailable" | "failed";
            template: components["schemas"]["TemplateRow"] | null;
        };
        /**
         * RuleKey
         * @description The Sales policies and copy a tenant may hold its own version of.
         * @enum {string}
         */
        RuleKey: "sales_order_rules" | "sales_kpi" | "sales_quote_rules" | "sales_pricing" | "sales_emails" | "sales_documents" | "sales_bravo_upload" | "sales_handoffs" | "sales_followups" | "sales_salesorder_rules" | "sales_reminders" | "sales_assistant";
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
         *     the document only to whoever may propose, and a price-bearing key's only
         *     to whoever may also read prices.
         */
        RuleVersionView: {
            /**
             * Applied Directly
             * @default false
             */
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
         * RuleWordsBody
         * @description What a person wants changed in a rule, in their words (dw_sales ADR
         *     0006), and the part of the document it is about, if not the whole.
         */
        RuleWordsBody: {
            /** Focus */
            focus?: string | null;
            /** Request */
            request: string;
        };
        /**
         * RulesInForceView
         * @description What applies to the tenant now, per key, and every version it holds.
         */
        RulesInForceView: {
            /** Draftable */
            draftable: components["schemas"]["RuleKey"][];
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
         * SalesOrderExampleBody
         * @description A customer's worked example: its PO, the SalesOrder file the PIC made
         *     from it, and the day the PO came in. The customer is the path's, looked
         *     up in the caller's own tenant; who uploads is the caller.
         */
        SalesOrderExampleBody: {
            po: components["schemas"]["ExampleFileBody"];
            /**
             * Received On
             * Format: date
             */
            received_on: string;
            salesorder: components["schemas"]["ExampleFileBody"];
        };
        /**
         * SalesOrderExampleView
         * @description An example as the customer's screen and the approval read it.
         */
        SalesOrderExampleView: {
            /** Customer Code */
            customer_code: string;
            /** Error */
            error: string | null;
            /**
             * Example Id
             * Format: uuid
             */
            example_id: string;
            /** Model Profile */
            model_profile: string | null;
            /** Po File Name */
            po_file_name: string;
            /** Problems */
            problems: components["schemas"]["LearnProblem"][];
            /** Prompt Ref */
            prompt_ref: string | null;
            /**
             * Received On
             * Format: date
             */
            received_on: string;
            replay: components["schemas"]["Replay"] | null;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /**
             * Requested By
             * Format: uuid
             */
            requested_by: string;
            rules: components["schemas"]["CustomerSalesOrderRules"] | null;
            /** Salesorder File Name */
            salesorder_file_name: string;
            /**
             * Status
             * @enum {string}
             */
            status: "queued" | "replayed" | "refused" | "unavailable" | "failed" | "submitted";
            /** Submittable */
            submittable: boolean;
            /** Version Id */
            version_id: string | null;
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
         * SenderCustomerBody
         * @description The customer Sales confirms an unknown sender as (AI item 5).
         */
        SenderCustomerBody: {
            /** Customer Code */
            customer_code: string;
        };
        /**
         * SenderCustomerView
         * @description A suggestion, or why there is none; always marked as the model's.
         */
        SenderCustomerView: {
            /** Customer Code */
            customer_code?: string | null;
            /** Customer Name */
            customer_name?: string | null;
            /** Evidence */
            evidence?: string | null;
            /** Message Id */
            message_id: string;
            /** Model Profile */
            model_profile?: string | null;
            /** Prompt Ref */
            prompt_ref?: string | null;
            /** Sender */
            sender: string;
            /**
             * Status
             * @enum {string}
             */
            status: "suggested" | "no_match" | "unavailable";
        };
        /**
         * SentMessageView
         * @description A message Sales sent on the case's thread (ticket 25: "Sales gửi"),
         *     with the thread intents a model read in it where the tenant's rules turn
         *     the step on (ticket 26), and the step that proposes when it is the
         *     thread's newest: Sales asking the customer proposes that the case waits
         *     on them. Its subject is Sales' own words.
         */
        SentMessageView: {
            /** Fallback */
            fallback?: ("calls" | "spend" | "time" | "unavailable") | null;
            /** Intents */
            intents: components["schemas"]["IntentView"][];
            /** Message Id */
            message_id: string;
            /** Outcome */
            outcome: ("read" | "unavailable") | null;
            /** Prompt */
            prompt: string | null;
            /** Proposal */
            proposal: ("settle_spec" | "decline_customer_rejected_spec" | "resume_review" | "await_revised_po" | "request_correction" | "discuss_spec" | "record_accepted" | "record_declined") | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Skills */
            skills?: string[];
            /** Subject */
            subject: string;
        };
        /** SettingView */
        SettingView: {
            key: components["schemas"]["RuleKey"];
            lock: components["schemas"]["LockReason"] | null;
            /** Path */
            path: string;
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
            /** Text Unseen */
            text_unseen: boolean;
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
            /** Sheets */
            sheets: string[];
            /** Truncated */
            truncated: boolean;
        };
        /**
         * ShiftDays
         * @description Moves a date by whole calendar days.
         */
        ShiftDays: {
            /** Days */
            days: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "shift_days";
        };
        /**
         * SignedCopyBody
         * @description The printed quotation as signed and scanned (PDF, JPG or PNG), base64.
         *     10 MiB of bytes (`SIGNED_MAX_BYTES`; the service refuses more).
         */
        SignedCopyBody: {
            /** Case Version */
            case_version: number;
            /** Content B64 */
            content_b64: string;
        };
        /**
         * SignedCopyView
         * @description The signed paper copy uploaded to the quotation: its file, who, when.
         */
        SignedCopyView: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
            /** Content Type */
            content_type: string;
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
        };
        /**
         * SkillComparison
         * @description One version beside the skill in force under its key, as a
         *     `sales.skills` approval is decided on /approvals: any skill's version,
         *     a customer's SalesOrder skill's too (ticket 41), which `SkillsView`
         *     does not list.
         */
        SkillComparison: {
            skill: components["schemas"]["SkillView"];
            version: components["schemas"]["SkillVersionView"];
        };
        /**
         * SkillProposal
         * @description What a person proposes: the skill's new words and a version number of
         *     the tenant's own.
         */
        SkillProposal: {
            /** Description */
            description: string;
            /** From Message */
            from_message?: string | null;
            /** Instructions */
            instructions: string;
            /** Version */
            version: string;
        };
        /**
         * SkillReplay
         * @description What one replay of a proposed version found, stored beside it
         *     (`skill_replay`).
         */
        SkillReplay: {
            /** Messages */
            messages: number;
            /**
             * Outcome
             * @enum {string}
             */
            outcome: "replayed" | "incomplete";
            /**
             * Replayed At
             * Format: date-time
             */
            replayed_at: string;
            /** Right With */
            right_with: number;
            /** Right Without */
            right_without: number;
            /**
             * Security Failed
             * @default []
             */
            security_failed: string[];
            /**
             * Source
             * @enum {string}
             */
            source: "platform_examples" | "customer_pairs";
            trigger?: components["schemas"]["TriggerReplay"] | null;
            /** Unanswered */
            unanswered: number;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * SkillVersionView
         * @description A tenant's version of a skill, as the skills list shows it.
         */
        SkillVersionView: {
            /** Approval Id */
            approval_id: string | null;
            /** Decided By */
            decided_by: string | null;
            /** Description */
            description: string;
            /** Instructions */
            instructions: string;
            /** Name */
            name: string;
            /**
             * Proposed By
             * Format: uuid
             */
            proposed_by: string;
            /** Ref */
            ref: string;
            replay?: components["schemas"]["SkillReplay"] | null;
            /**
             * Status
             * @enum {string}
             */
            status: "proposed" | "approved" | "rejected" | "superseded";
            /** Trigger */
            trigger?: string | null;
            /**
             * Version Id
             * Format: uuid
             */
            version_id: string;
        };
        /**
         * SkillView
         * @description A skill as it applies to the tenant now.
         */
        SkillView: {
            /** Customer Code */
            customer_code?: string | null;
            /** Customer Name */
            customer_name?: string | null;
            /** Description */
            description: string;
            /** Instructions */
            instructions: string;
            /**
             * Layer
             * @enum {string}
             */
            layer: "platform" | "tenant";
            /** Name */
            name: string;
            /** Platform Ref */
            platform_ref: string;
            /** Ref */
            ref: string;
        };
        /** SkillsView */
        SkillsView: {
            /**
             * Customer Skills
             * @default []
             */
            customer_skills: components["schemas"]["SkillView"][];
            /** Skills */
            skills: components["schemas"]["SkillView"][];
            /** Versions */
            versions: components["schemas"]["SkillVersionView"][];
        };
        /**
         * SoDifference
         * @description Where Bravo's order is not what was prepared. ``expected`` and
         *     ``actual`` are the values as printed; a unit price's are shown only to
         *     those who may read prices (the view's concern).
         */
        SoDifference: {
            /** Actual */
            actual?: string | null;
            /** Expected */
            expected?: string | null;
            /**
             * Field
             * @enum {string}
             */
            field: "missing_row" | "extra_row" | "item_code" | "quantity" | "unit_price" | "requested_date";
            /** Line No */
            line_no: number;
            /** Po No */
            po_no: string;
            /** Row */
            row?: number | null;
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
        /**
         * StepAutonomyView
         * @description One step's line on the head's view (ticket 44).
         */
        StepAutonomyView: {
            /** Applied */
            applied: number;
            /** Audited */
            audited: number;
            /** Audited Error */
            audited_error: number | null;
            /** Audits */
            audits: number;
            /** Cases */
            cases: number;
            /** Computed At */
            computed_at: string | null;
            /**
             * Mode
             * @enum {string}
             */
            mode: "never" | "measuring" | "applying" | "stopped";
            /** Needed */
            needed: number | null;
            /** Shadow */
            shadow: number;
            step: components["schemas"]["ModelStep"];
            /** Target */
            target: number | null;
            /** Threshold */
            threshold: number | null;
            tier: components["schemas"]["Tier"];
            /** To Person */
            to_person: number;
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
        /**
         * StepId
         * @description The surveyed steps' ids as a closed set: what a value kept per step (the
         *     KPI's manual baseline) is keyed by, so a version written before a step was
         *     surveyed reads that step as the platform has it (`rules.read_over`). Held
         *     to `WIV_STEPS`, which owns the steps themselves, by a test.
         * @enum {string}
         */
        StepId: "O1" | "O2" | "O3" | "O4" | "O5" | "O6" | "O7" | "O8" | "O9" | "O10" | "O11" | "Q1" | "Q2" | "Q3" | "Q4" | "Q5" | "Q6" | "Q7" | "Q8" | "Q9" | "Q10" | "Q11" | "Q12";
        /**
         * StepLabelView
         * @description One step's line on the head's view.
         */
        StepLabelView: {
            /** Confirmed */
            confirmed: number;
            /** Confirmed Share */
            confirmed_share: number | null;
            /** Corrected */
            corrected: number;
            /** Rejected */
            rejected: number;
            step: components["schemas"]["ModelStep"];
            /** Total */
            total: number;
        };
        /**
         * StepModelView
         * @description One model step of a process step, read-only.
         */
        StepModelView: {
            /** Bar */
            bar: number;
            /** Effective */
            effective: boolean;
            /** Enabled */
            enabled: boolean;
            latest: components["schemas"]["MeasurementView"] | null;
            live_share: components["schemas"]["LiveShareView"];
            /** Metric */
            metric: string;
            /** Model */
            model: string | null;
            /** Prompt */
            prompt: string;
            step: components["schemas"]["ModelStep"];
        };
        /** StepSummaryView */
        StepSummaryView: {
            automatic: components["schemas"]["LinkedCount"];
            /** Automatic Share */
            automatic_share: number | null;
            handled: components["schemas"]["LinkedCount"];
            latency: components["schemas"]["LatencyView"];
            model_unavailable: components["schemas"]["LinkedCount"];
            /** Process Steps */
            process_steps: components["schemas"]["StepId"][];
            step: components["schemas"]["ModelStep"];
            to_person: components["schemas"]["LinkedCount"];
            /** Top Reasons */
            top_reasons: components["schemas"]["ReasonCount"][];
        };
        /**
         * SubflowKey
         * @description A flow beside a lane's statuses: a case waits or loops in it while its
         *     status stays where it is (ticket 35).
         * @enum {string}
         */
        SubflowKey: "thread" | "pc_request" | "change_request" | "update" | "design_code" | "quote";
        /** SubflowStepView */
        SubflowStepView: {
            /** Ba Steps */
            ba_steps: components["schemas"]["BaStepView"][];
            /** Next */
            next: string[];
            /** Statuses */
            statuses: string[];
            /** Step */
            step: string;
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
        /** SuggestionView */
        SuggestionView: {
            /** Basis */
            basis: string;
            copper_basis: components["schemas"]["CopperBasisView"] | null;
            /** Lead Time Days */
            lead_time_days: number | null;
            /** Moq */
            moq: string | null;
            /** Raised To Floor */
            raised_to_floor: boolean;
            /** Source No */
            source_no: string | null;
            /** Unit Price */
            unit_price: string;
        };
        /** SummaryPoint */
        SummaryPoint: {
            /** Cites */
            cites: string[];
            /** Text */
            text: string;
        };
        /** SupersededView */
        SupersededView: {
            /** Attachment Id */
            attachment_id: string | null;
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
         * TemplateHeader
         * @description One visible cell of the header row (or a row above it), as the
         *     workbook holds it.
         */
        TemplateHeader: {
            /** Column */
            column: number;
            /** Ref */
            ref: string;
            /** Text */
            text: string;
        };
        /**
         * TemplateRow
         * @description The template's header row: its sheet, its row number, its cells, and
         *     the visible cells of each row above it, from row 1 (an empty tuple for a
         *     row with none).
         */
        TemplateRow: {
            /**
             * Above
             * @default []
             */
            above: components["schemas"]["TemplateHeader"][][];
            /** Headers */
            headers: components["schemas"]["TemplateHeader"][];
            /** Row */
            row: number;
            /** Sheet */
            sheet: string;
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
        /**
         * ThreadCaseBody
         * @description The case Sales picks for a reply its thread offered several of
         *     (ticket 24): one of those, which the server checks.
         */
        ThreadCaseBody: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
        };
        /**
         * ThreadCaseView
         * @description A case a message names: one offered for a reply, or one of a mail's
         *     several POs; its kind, id and the number it goes by (the PO's, or the
         *     request's).
         */
        ThreadCaseView: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            case_kind: components["schemas"]["CaseKind"];
            /** Number */
            number: string;
        };
        /**
         * ThreadMessageView
         * @description A message of a case's mail thread received before the case opened:
         *     the talk before the PO (ticket 24, dw_sales ADR 0009). The mail itself
         *     opens in the inbox.
         */
        ThreadMessageView: {
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
        };
        /**
         * ThreadSummaryView
         * @description A summary, or why there is none; always marked as the model's.
         */
        ThreadSummaryView: {
            /**
             * Case Id
             * Format: uuid
             */
            case_id: string;
            /**
             * Dropped
             * @default 0
             */
            dropped: number;
            /**
             * Mails
             * @default 0
             */
            mails: number;
            /** Model Profile */
            model_profile?: string | null;
            /**
             * Points
             * @default []
             */
            points: components["schemas"]["SummaryPoint"][];
            /** Prompt Ref */
            prompt_ref?: string | null;
            /**
             * Status
             * @enum {string}
             */
            status: "summarized" | "empty" | "unavailable" | "refused";
        };
        /**
         * Tier
         * @description What a step's effect is, and so whether its result may apply itself.
         * @enum {string}
         */
        Tier: "applies_itself" | "hand_off" | "person_approves";
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
        /** TodayView */
        TodayView: {
            brief: components["schemas"]["BriefView"] | null;
            /** Hidden */
            hidden: number;
            /** Reminders */
            reminders: components["schemas"]["ReminderView"][];
        };
        /**
         * TrailStepView
         * @description One step of a line's trail. ``code`` is the rule's, check's or
         *     model step's own code; the other fields are what the step rests on.
         */
        TrailStepView: {
            /** Actor User Id */
            actor_user_id?: string | null;
            /** At */
            at?: string | null;
            /** Cell */
            cell?: string | null;
            /** Code */
            code: string;
            /** Confidence */
            confidence?: number | null;
            /**
             * Decided By
             * @enum {string}
             */
            decided_by: "rule" | "model" | "dw" | "person";
            /** Gate */
            gate?: string | null;
            /**
             * Kind
             * @enum {string}
             */
            kind: "read" | "convert" | "model_reading" | "mapping" | "quotation" | "checks" | "finding" | "finding_decided" | "correction" | "change" | "design_asked" | "pc_asked" | "pc_short_lead" | "pc_answer" | "model_step" | "bravo_recorded" | "cross_checked" | "confirmed";
            /** Outcome */
            outcome?: string | null;
            /** Page */
            page?: number | null;
            /** Rule Version */
            rule_version?: string | null;
            /** Severity */
            severity?: string | null;
            /** Valid From */
            valid_from?: string | null;
            /** Valid To */
            valid_to?: string | null;
            /** Value */
            value?: string | null;
        };
        /**
         * TriageCardView
         * @description A message's triage card as the inbox shows it: what it seems to be
         *     (the skill's kind, its label where the skill gives one, and the route
         *     the skill maps it onto), the one step suggested, the case it names
         *     where the caller may see it, and the decision once made.
         */
        TriageCardView: {
            case: components["schemas"]["ThreadCaseView"] | null;
            decided: components["schemas"]["CardVerdict"] | null;
            /** Kind */
            kind: string | null;
            /** Kind Label */
            kind_label: string | null;
            /** Routed As */
            routed_as: string | null;
            /** Skill */
            skill: string;
            /** Step */
            step: ("reply_to_case" | "delivery_change" | "complaint" | "sample_request" | "portal_notice") | null;
        };
        /**
         * TriggerReplay
         * @description The mail a version was proposed from (`SkillTrigger`), read with the
         *     version and with the one in force: the kind each named (None: no usable
         *     answer, or no kind read), its label where the skill gives one, and the
         *     route it took (``none``: no kind read; None: no usable answer).
         */
        TriggerReplay: {
            /** Found */
            found: boolean;
            /** Message Id */
            message_id: string;
            /** With Kind */
            with_kind?: string | null;
            /** With Label */
            with_label?: string | null;
            /** With Route */
            with_route?: ("po" | "quote_request" | "design_reply" | "reply_to_case" | "delivery_change" | "complaint" | "sample_request" | "portal_notice" | "other") | "none" | null;
            /** Without Kind */
            without_kind?: string | null;
            /** Without Label */
            without_label?: string | null;
            /** Without Route */
            without_route?: ("po" | "quote_request" | "design_reply" | "reply_to_case" | "delivery_change" | "complaint" | "sample_request" | "portal_notice" | "other") | "none" | null;
        };
        /** TurnView */
        TurnView: {
            /** Answer */
            answer: string;
            /**
             * Answered By
             * @enum {string}
             */
            answered_by: "model" | "code";
            /** Asked At */
            asked_at: string;
            /** Cites */
            cites: components["schemas"]["CaseRefView"][];
            kind: components["schemas"]["QuestionKind"];
            /** Offer */
            offer?: ("reply_draft" | "customer_reminder" | "thread_summary") | null;
            proposal?: components["schemas"]["ProposalView"] | null;
            /** Question */
            question: string;
            /** Seq */
            seq: number;
        };
        /**
         * TypedChange
         * @description A line a person types: the line, the field, the value in its one form
         *     (an ISO date from the date picker, a number from the number box).
         */
        TypedChange: {
            /**
             * Field
             * @enum {string}
             */
            field: "quantity" | "requested_date";
            /** Line No */
            line_no: number;
            /** Value */
            value: string;
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
        /**
         * UnitFactor
         * @description Multiplies the value by how many ``to`` make one ``from``.
         */
        UnitFactor: {
            /**
             * From
             * @enum {string}
             */
            from: "mm" | "cm" | "m" | "km";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            step: "unit_factor";
            /**
             * To
             * @enum {string}
             */
            to: "mm" | "cm" | "m" | "km";
        };
        /**
         * UnopenedValue
         * @description A value of the order nobody was served the page or sheet of.
         */
        UnopenedValue: {
            /** Field */
            field: string;
            /** Line No */
            line_no?: number | null;
        };
        /**
         * UpdateAnswerBody
         * @description What the customer answered to a change's answer (ticket 29), as the
         *     person recorded it: keep the PO, accept, or ask PC again.
         */
        UpdateAnswerBody: {
            /**
             * Answer
             * @enum {string}
             */
            answer: "keep" | "accept" | "ask_pc_again";
            /** Case Version */
            case_version: number;
        };
        /**
         * UpdateApprovalBody
         * @description The Bravo update file the PIC approves, drawn at ``case_version``.
         */
        UpdateApprovalBody: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
            /** Case Version */
            case_version: number;
        };
        /**
         * UpdateApprovalView
         * @description The Bravo update file the PIC approved, by its id and hash.
         */
        UpdateApprovalView: {
            /**
             * Artifact Id
             * Format: uuid
             */
            artifact_id: string;
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
            /** Case Version */
            case_version: number;
            /** Sha256 */
            sha256: string;
        };
        /**
         * UpdateDeliveryView
         * @description One delivery PC gives a changed line in the update loop (ticket 29).
         */
        UpdateDeliveryView: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Quantity */
            quantity: string;
        };
        /**
         * UpdateLineView
         * @description One line a customer's change asks about, in the update loop: what the
         *     order holds now, what is asked (None: that value is not changed) and PC's
         *     answer for it, once recorded.
         */
        UpdateLineView: {
            /** Asked Quantity */
            asked_quantity: string | null;
            /** Asked Requested Date */
            asked_requested_date: string | null;
            /** Held Quantity */
            held_quantity: string;
            /** Held Requested Date */
            held_requested_date: string | null;
            /** Line No */
            line_no: number;
            /** Pc Answered By */
            pc_answered_by: string | null;
            /** Pc Deliveries */
            pc_deliveries: components["schemas"]["UpdateDeliveryView"][] | null;
        };
        /**
         * UpdateLoopView
         * @description A customer's change on an order in Bravo (ticket 29): its step, since
         *     when, code's verdict on PC's answer (6-DW4 ``can_do`` or 6-DW3
         *     ``proposes``), the lines and the approved Bravo update file.
         */
        UpdateLoopView: {
            approval: components["schemas"]["UpdateApprovalView"] | null;
            /**
             * Awaits
             * @enum {string}
             */
            awaits: "ask_pc" | "waiting_pc" | "answer_customer" | "waiting_customer" | "approve_update" | "bravo_entry" | "cross_check" | "confirm";
            /** Lines */
            lines: components["schemas"]["UpdateLineView"][];
            /** Reason */
            reason?: ("overcapacity" | "ng" | "short_stock" | "other") | null;
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
            /**
             * Since
             * Format: date-time
             */
            since: string;
            /**
             * Step
             * @enum {string}
             */
            step: "ask_pc" | "waiting_pc" | "answer_customer" | "waiting_customer" | "bravo_update";
            /** Verdict */
            verdict: ("can_do" | "proposes") | null;
        };
        /**
         * UploadFileBody
         * @description One file of a PO upload (ticket 18): its name and its bytes, base64,
         *     decoded here and never opened: the worker reads it in the reader sandbox.
         */
        UploadFileBody: {
            /** Content B64 */
            content_b64: string;
            /** File Name */
            file_name: string;
        };
        /** UsesView */
        UsesView: {
            /** Layouts */
            layouts: boolean;
            /** Lists */
            lists: components["schemas"]["CatalogList"][];
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
        ValueState: "dw" | "uncertain" | "confirmed" | "not_opened" | "hand_entered" | "superseded";
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
            /** Due Soon */
            due_soon: boolean;
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "order" | "quote" | "message";
            /** Owner */
            owner?: string | null;
            /**
             * Received At
             * Format: date-time
             */
            received_at: string;
            /** Sla Due At */
            sla_due_at?: string | null;
            /** Sla Warn At */
            sla_warn_at?: string | null;
            /** Status */
            status: string;
        };
        /**
         * WorkedPairView
         * @description A pair as the customer's screen lists it: which PO, when, how many
         *     rows; never a cell (module docstring).
         */
        WorkedPairView: {
            /**
             * Added At
             * Format: date-time
             */
            added_at: string;
            /**
             * Added By
             * Format: uuid
             */
            added_by: string;
            /** Customer Code */
            customer_code: string;
            /** Example Id */
            example_id: string | null;
            /**
             * Pair Id
             * Format: uuid
             */
            pair_id: string;
            /** Po No */
            po_no: string;
            /**
             * Received On
             * Format: date
             */
            received_on: string;
            /** Replayed */
            replayed: boolean;
            /** Rows */
            rows: number;
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
    activity_summary_api_v1_sales_activity_get: {
        parameters: {
            query?: {
                from?: string | null;
                to?: string | null;
                lane?: components["schemas"]["CaseKind"] | null;
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
                    "application/json": components["schemas"]["ActivitySummaryView"];
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
    activity_autonomy_api_v1_sales_activity_autonomy_get: {
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
                    "application/json": components["schemas"]["AutonomySummaryView"];
                };
            };
        };
    };
    activity_labels_api_v1_sales_activity_labels_get: {
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
                    "application/json": components["schemas"]["LabelSummaryView"];
                };
            };
        };
    };
    assistant_ask_api_v1_sales_assistant_ask_post: {
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
                "application/json": components["schemas"]["AskBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnswerView"];
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
    assistant_stream_api_v1_sales_assistant_ask_stream_post: {
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
                "application/json": components["schemas"]["AskBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": unknown;
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
    assistant_cases_api_v1_sales_assistant_cases_get: {
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
                    "application/json": components["schemas"]["CaseConversationView"][];
                };
            };
        };
    };
    assistant_case_api_v1_sales_assistant_cases__kind___case_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                kind: components["schemas"]["CaseKind"];
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
                    "application/json": components["schemas"]["ConversationView"];
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
    assistant_case_ask_api_v1_sales_assistant_cases__kind___case_id__ask_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                kind: components["schemas"]["CaseKind"];
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AskBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnswerView"];
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
    assistant_case_stream_api_v1_sales_assistant_cases__kind___case_id__ask_stream_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                kind: components["schemas"]["CaseKind"];
                case_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AskBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "text/event-stream": unknown;
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
    assistant_confirm_api_v1_sales_assistant_cases__kind___case_id__turns__seq__confirm_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                kind: components["schemas"]["CaseKind"];
                case_id: string;
                seq: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecisionConfirmBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConfirmedView"];
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
    assistant_conversation_api_v1_sales_assistant_conversation_get: {
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
                    "application/json": components["schemas"]["ConversationView"];
                };
            };
        };
    };
    assistant_unread_api_v1_sales_assistant_unread_get: {
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
                    "application/json": string[];
                };
            };
        };
    };
    bravo_exports_api_v1_sales_bravo_exports_get: {
        parameters: {
            query: {
                screen: "ycbg" | "sales_orders";
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
                    "application/json": components["schemas"]["BravoExport"][];
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
    upload_bravo_export_api_v1_sales_bravo_exports_post: {
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
                "application/json": components["schemas"]["BravoExportBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["BravoExport"];
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
    customer_notation_api_v1_sales_customers__customer_code__notation_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                customer_code: string;
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
                    "application/json": components["schemas"]["CustomerNotationView"];
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
    set_customer_notation_api_v1_sales_customers__customer_code__notation_put: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                customer_code: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CustomerNotationBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CustomerNotationView"];
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
    forget_customer_notation_api_v1_sales_customers__customer_code__notation__kind__delete: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                customer_code: string;
                kind: "decimal_mark" | "date_order" | "dollar_sign" | "yen_sign";
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
                    "application/json": components["schemas"]["CustomerNotationView"];
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
    salesorder_examples_api_v1_sales_customers__customer_code__salesorder_examples_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                customer_code: string;
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
                    "application/json": components["schemas"]["SalesOrderExampleView"][];
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
    request_salesorder_example_api_v1_sales_customers__customer_code__salesorder_examples_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                customer_code: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SalesOrderExampleBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SalesOrderExampleView"];
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
    salesorder_pairs_api_v1_sales_customers__customer_code__salesorder_pairs_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                customer_code: string;
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
                    "application/json": components["schemas"]["WorkedPairView"][];
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
    upload_po_api_v1_sales_inbox_upload_post: {
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
                "application/json": components["schemas"]["PoUploadBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PoUploadView"];
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
    pick_thread_case_api_v1_sales_inbox__message_id__case_post: {
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
        requestBody: {
            content: {
                "application/json": components["schemas"]["ThreadCaseBody"];
            };
        };
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
    sender_customer_api_v1_sales_inbox__message_id__customer_get: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["SenderCustomerView"];
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
    confirm_sender_customer_api_v1_sales_inbox__message_id__customer_post: {
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
        requestBody: {
            content: {
                "application/json": components["schemas"]["SenderCustomerBody"];
            };
        };
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
    design_text_reply_api_v1_sales_inbox__message_id__design_reply_get: {
        parameters: {
            query?: never;
            header?: never;
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
                    "application/json": components["schemas"]["DesignTextReadingView"];
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
    confirm_design_text_reply_api_v1_sales_inbox__message_id__design_reply_post: {
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
        requestBody: {
            content: {
                "application/json": components["schemas"]["ModelDesignReply"];
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
    handled_api_v1_sales_inbox__message_id__handled_post: {
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
        requestBody: {
            content: {
                "application/json": components["schemas"]["HandledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HandledView"];
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
    reopen_api_v1_sales_inbox__message_id__reopen_post: {
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
                    "application/json": components["schemas"]["HandledView"];
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
    decide_triage_card_api_v1_sales_inbox__message_id__triage_post: {
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
        requestBody: {
            content: {
                "application/json": components["schemas"]["CardDecisionRequest"];
            };
        };
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
    convert_gaps_api_v1_sales_master_data_convert_gaps_get: {
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
                    "application/json": components["schemas"]["ConvertGapsView"];
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
    catalog_state_api_v1_sales_master_data_imports_get: {
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
                    "application/json": components["schemas"]["CatalogStateView"];
                };
            };
        };
    };
    catalog_preview_api_v1_sales_master_data_imports_snapshots__snapshot_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                snapshot_id: string;
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
                    "application/json": components["schemas"]["CatalogPreviewView"];
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
    catalog_submit_api_v1_sales_master_data_imports_snapshots__snapshot_id__submit_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                snapshot_id: string;
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
                    "application/json": components["schemas"]["CatalogImportView"];
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
    catalog_upload_api_v1_sales_master_data_imports__catalog_list__post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                catalog_list: components["schemas"]["CatalogList"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CatalogUploadBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CatalogImportView"];
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
    catalog_template_api_v1_sales_master_data_imports__catalog_list__template_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                catalog_list: components["schemas"]["CatalogList"];
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
            query?: {
                step?: components["schemas"]["ModelStep"] | null;
                handled_by?: ("dw1" | "person") | null;
                result?: ("accepted" | "refused" | "unavailable") | null;
                reason_code?: string | null;
                lane?: components["schemas"]["CaseKind"] | null;
                from?: string | null;
                to?: string | null;
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
                    "application/json": components["schemas"]["OrderSummaryView"][];
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
    order_activity_api_v1_sales_orders__case_id__activity_get: {
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
                    "application/json": components["schemas"]["CaseActivityView"];
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
    record_agreement_api_v1_sales_orders__case_id__agreement_post: {
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
                "application/json": components["schemas"]["AgreementBody"];
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
    send_order_mail_api_v1_sales_orders__case_id__artifacts__artifact_id__send_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                artifact_id: string;
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
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutboundMailView"];
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
    bravo_read_back_api_v1_sales_orders__case_id__bravo_read_back_get: {
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
                    "application/json": components["schemas"]["ReadBackView"];
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
    open_change_request_api_v1_sales_orders__case_id__change_requests_post: {
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
                "application/json": components["schemas"]["ChangeRequestBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangeRequestResult"];
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
    add_change_line_api_v1_sales_orders__case_id__change_requests__request_id__lines_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangeLineBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangeRequestResult"];
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
    confirm_change_line_api_v1_sales_orders__case_id__change_requests__request_id__lines__seq__confirm_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                request_id: string;
                seq: number;
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
                    "application/json": components["schemas"]["ChangeRequestResult"];
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
    reject_change_line_api_v1_sales_orders__case_id__change_requests__request_id__lines__seq__reject_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                request_id: string;
                seq: number;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangeRejectBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ChangeRequestResult"];
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
    order_reminder_api_v1_sales_orders__case_id__customer_reminder_get: {
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
                    "application/json": components["schemas"]["CustomerReminderView"];
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
    record_decline_api_v1_sales_orders__case_id__decline_post: {
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
    explain_finding_api_v1_sales_orders__case_id__findings__finding_key__explanation_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
                finding_key: string;
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
                    "application/json": components["schemas"]["FindingExplanationView"];
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
    order_history_api_v1_sales_orders__case_id__history_get: {
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
                    "application/json": components["schemas"]["CaseHistoryEntry"][];
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
    apply_internal_change_api_v1_sales_orders__case_id__internal_change_post: {
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
                "application/json": components["schemas"]["InternalApplyBody"];
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
    read_internal_change_api_v1_sales_orders__case_id__internal_change_read_post: {
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
                "application/json": components["schemas"]["InternalReadBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InternalReadView"];
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
    design_request_api_v1_sales_orders__case_id__lines__line_no__design_request_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
                line_no: number;
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
                    "application/json": components["schemas"]["DesignRequestView"];
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
    design_asked_api_v1_sales_orders__case_id__lines__line_no__design_request_post: {
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
    reject_mapping_api_v1_sales_orders__case_id__lines__line_no__mapping_reject_post: {
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
    undo_mapping_api_v1_sales_orders__case_id__lines__line_no__mapping_undo_post: {
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
    pc_answer_api_v1_sales_orders__case_id__lines__line_no__pc_answer_post: {
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
                "application/json": components["schemas"]["PcAnswerBody"];
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
    order_line_trail_api_v1_sales_orders__case_id__lines__line_no__trail_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                case_id: string;
                line_no: number;
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
                    "application/json": components["schemas"]["LineTrailView"];
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
    order_message_text_api_v1_sales_orders__case_id__message_text_get: {
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
    order_outbound_api_v1_sales_orders__case_id__outbound_get: {
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
                    "application/json": components["schemas"]["OutboundMailsView"];
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
    pc_dates_api_v1_sales_orders__case_id__pc_dates_post: {
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
                "application/json": components["schemas"]["PcDatesBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PcDatesView"];
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
    pc_dates_from_mail_api_v1_sales_orders__case_id__pc_dates_from_mail__message_id__post: {
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
                    "application/json": components["schemas"]["PcDatesView"];
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
    pc_mails_api_v1_sales_orders__case_id__pc_mails_get: {
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
                    "application/json": components["schemas"]["PcMailsView"];
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
    pc_request_api_v1_sales_orders__case_id__pc_request_get: {
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
                    "application/json": components["schemas"]["PcRequestView"];
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
    pc_asked_api_v1_sales_orders__case_id__pc_request_post: {
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
    open_quote_api_v1_sales_orders__case_id__quote_post: {
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
                    "application/json": components["schemas"]["OrderQuoteView"];
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
    quote_check_api_v1_sales_orders__case_id__quote_check_post: {
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
    order_reply_draft_api_v1_sales_orders__case_id__reply_draft_get: {
        parameters: {
            query: {
                kind: string;
                message_id?: string | null;
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
                    "application/json": components["schemas"]["ReplyDraftView"];
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
    order_thread_api_v1_sales_orders__case_id__thread_summary_get: {
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
                    "application/json": components["schemas"]["ThreadSummaryView"];
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
    update_answer_sent_api_v1_sales_orders__case_id__update_answer_sent_post: {
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
    update_bravo_file_api_v1_sales_orders__case_id__update_bravo_file_post: {
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
                "application/json": components["schemas"]["UpdateApprovalBody"];
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
    update_customer_answer_api_v1_sales_orders__case_id__update_customer_answer_post: {
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
                "application/json": components["schemas"]["UpdateAnswerBody"];
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
    update_pc_answer_api_v1_sales_orders__case_id__update_lines__line_no__pc_answer_post: {
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
                "application/json": components["schemas"]["PcAnswerBody"];
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
    update_pc_request_api_v1_sales_orders__case_id__update_pc_request_get: {
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
                    "application/json": components["schemas"]["PcRequestView"];
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
    update_pc_asked_api_v1_sales_orders__case_id__update_pc_request_post: {
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
    pipeline_api_v1_sales_pipeline_get: {
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
                    "application/json": components["schemas"]["PipelineView"];
                };
            };
        };
    };
    prompt_versions_api_v1_sales_prompts_get: {
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
                    "application/json": components["schemas"]["PromptsView"];
                };
            };
        };
    };
    quotes_api_v1_sales_quotes_get: {
        parameters: {
            query?: {
                step?: components["schemas"]["ModelStep"] | null;
                handled_by?: ("dw1" | "person") | null;
                result?: ("accepted" | "refused" | "unavailable") | null;
                reason_code?: string | null;
                lane?: components["schemas"]["CaseKind"] | null;
                from?: string | null;
                to?: string | null;
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
                    "application/json": components["schemas"]["QuoteSummaryView"][];
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
    screening_followup_api_v1_sales_quotes_screening__customer_code___prv_code__followup_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                customer_code: string;
                prv_code: string;
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
                    "application/json": components["schemas"]["FollowupDraftView"];
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
    quote_activity_api_v1_sales_quotes__case_id__activity_get: {
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
                    "application/json": components["schemas"]["CaseActivityView"];
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
    send_quote_mail_api_v1_sales_quotes__case_id__artifacts__artifact_id__send_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                case_id: string;
                artifact_id: string;
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
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OutboundMailView"];
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
    quote_reminder_api_v1_sales_quotes__case_id__customer_reminder_get: {
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
                    "application/json": components["schemas"]["CustomerReminderView"];
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
    design_from_bravo_api_v1_sales_quotes__case_id__design_from_bravo_post: {
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
    quote_history_api_v1_sales_quotes__case_id__history_get: {
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
                    "application/json": components["schemas"]["CaseHistoryEntry"][];
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
    quote_outbound_api_v1_sales_quotes__case_id__outbound_get: {
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
                    "application/json": components["schemas"]["OutboundMailsView"];
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
    pcs_price_api_v1_sales_quotes__case_id__pcs_price_post: {
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
                "application/json": components["schemas"]["PcsPriceBody"];
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
    pcs_price_request_api_v1_sales_quotes__case_id__pcs_price_request_get: {
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
                    "application/json": components["schemas"]["PcsCostSheet"];
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
    production_type_api_v1_sales_quotes__case_id__production_type_post: {
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
                "application/json": components["schemas"]["ProductionTypeBody"];
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
    upload_signed_quote_api_v1_sales_quotes__case_id__signed_copy_post: {
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
                "application/json": components["schemas"]["SignedCopyBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ArtifactView"];
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
    quote_thread_api_v1_sales_quotes__case_id__thread_summary_get: {
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
                    "application/json": components["schemas"]["ThreadSummaryView"];
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
    rule_draft_api_v1_sales_rules_drafts__draft_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                draft_id: string;
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
                    "application/json": components["schemas"]["RuleDraftView"];
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
    rules_process_api_v1_sales_rules_process_get: {
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
                    "application/json": components["schemas"]["ProcessSettingsView"];
                };
            };
        };
    };
    request_rule_draft_api_v1_sales_rules__key__drafts_post: {
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
                "application/json": components["schemas"]["RuleDraftBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RuleDraftView"];
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
    request_rule_words_api_v1_sales_rules__key__drafts_words_post: {
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
                "application/json": components["schemas"]["RuleWordsBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RuleDraftView"];
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
    salesorder_example_of_version_api_v1_sales_salesorder_examples_by_version__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: string;
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
                    "application/json": components["schemas"]["SalesOrderExampleView"];
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
    salesorder_example_api_v1_sales_salesorder_examples__example_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                example_id: string;
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
                    "application/json": components["schemas"]["SalesOrderExampleView"];
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
    submit_salesorder_example_api_v1_sales_salesorder_examples__example_id__submissions_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                example_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ExampleSubmissionBody"];
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
    withdraw_salesorder_pair_api_v1_sales_salesorder_pairs__pair_id__delete: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                pair_id: string;
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
                    "application/json": components["schemas"]["WorkedPairView"];
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
    skills_in_force_api_v1_sales_skills_get: {
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
                    "application/json": components["schemas"]["SkillsView"];
                };
            };
        };
    };
    skill_version_api_v1_sales_skills_versions__version_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                version_id: string;
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
                    "application/json": components["schemas"]["SkillComparison"];
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
    propose_skill_api_v1_sales_skills__name__versions_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                name: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SkillProposal"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SkillVersionView"];
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
    today_api_v1_sales_today_get: {
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
                    "application/json": components["schemas"]["TodayView"];
                };
            };
        };
    };
    mark_reminder_api_v1_sales_today_reminders__notification_id__mark_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                notification_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MarkIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TodayView"];
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
