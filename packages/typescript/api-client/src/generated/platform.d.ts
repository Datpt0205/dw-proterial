/**
 * Auto-generated types for context "platform" — do not edit.
 * Regenerate with `make generate-contracts`.
 */
export interface paths {
    "/api/v1/admin/accounts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Accounts
         * @description The sign-in accounts this tenant created, and whether each may sign in.
         */
        get: operations["list_accounts_api_v1_admin_accounts_get"];
        put?: never;
        /**
         * Create Account
         * @description Create the person, their roles and their sign-in account, with a
         *     temporary password they must change at their first sign-in.
         */
        post: operations["create_account_api_v1_admin_accounts_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/accounts/{user_id}/enabled": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Set Enabled
         * @description Lock (and end the open sessions of) or unlock a person's sign-in.
         */
        put: operations["set_enabled_api_v1_admin_accounts__user_id__enabled_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/accounts/{user_id}/password-reset": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reset Password
         * @description A new temporary password; the old one stops working at once.
         */
        post: operations["reset_password_api_v1_admin_accounts__user_id__password_reset_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/background-failures": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Background Failures */
        get: operations["list_background_failures_api_v1_admin_background_failures_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/background-failures/{event_id}/retry": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Retry Background Failure */
        post: operations["retry_background_failure_api_v1_admin_background_failures__event_id__retry_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/hierarchy": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Hierarchy
         * @description The org chart: every member of the workspace and who they report to.
         */
        get: operations["get_hierarchy_api_v1_admin_hierarchy_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/hierarchy/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Manager */
        put: operations["set_manager_api_v1_admin_hierarchy__user_id__put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/invitations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Invite Member
         * @description Create the person (no sign-in yet) and their memberships. No email is
         *     sent: the admin tells the person, who then signs in with that email.
         */
        post: operations["invite_member_api_v1_admin_invitations_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Members
         * @description Everyone in the caller's tenant, by name (Vietnamese collation), with
         *     their roles in each workspace.
         */
        get: operations["list_members_api_v1_admin_members_get"];
        put?: never;
        /** Grant Member */
        post: operations["grant_member_api_v1_admin_members_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/members/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Revoke Member */
        delete: operations["revoke_member_api_v1_admin_members__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/members/{user_id}/memberships": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Set Memberships
         * @description Replace the person's non-administrative roles, workspace by workspace,
         *     in one transaction. A workspace in the body without a membership gets one;
         *     one left out keeps only its administrative roles, and goes without any.
         *     Answers the person's memberships as they now are (empty: none left).
         */
        put: operations["set_memberships_api_v1_admin_members__user_id__memberships_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/members/{user_id}/permission-sets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /** Set Permission Sets */
        put: operations["set_permission_sets_api_v1_admin_members__user_id__permission_sets_put"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/permission-sets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Permission Sets */
        get: operations["list_permission_sets_api_v1_admin_permission_sets_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Roles */
        get: operations["list_roles_api_v1_admin_roles_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/separation-of-duties": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Separation Of Duties */
        get: operations["list_separation_of_duties_api_v1_admin_separation_of_duties_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/separation-of-duties/{rule_key}/waiver": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Waive Separation Of Duties Rule */
        post: operations["waive_separation_of_duties_rule_api_v1_admin_separation_of_duties__rule_key__waiver_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/separation-of-duties/{rule_key}/waiver/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Confirm Separation Of Duties Waiver */
        post: operations["confirm_separation_of_duties_waiver_api_v1_admin_separation_of_duties__rule_key__waiver_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/separation-of-duties/{rule_key}/waiver/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revoke Separation Of Duties Waiver */
        post: operations["revoke_separation_of_duties_waiver_api_v1_admin_separation_of_duties__rule_key__waiver_revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/tenant": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Tenant */
        get: operations["get_tenant_api_v1_admin_tenant_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Tenant */
        patch: operations["update_tenant_api_v1_admin_tenant_patch"];
        trace?: never;
    };
    "/api/v1/admin/workspaces": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Workspaces */
        get: operations["list_workspaces_api_v1_admin_workspaces_get"];
        put?: never;
        /** Create Workspace */
        post: operations["create_workspace_api_v1_admin_workspaces_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/workspaces/{workspace_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Rename Workspace */
        patch: operations["rename_workspace_api_v1_admin_workspaces__workspace_id__patch"];
        trace?: never;
    };
    "/api/v1/admin/workspaces/{workspace_id}/archive": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Archive Workspace */
        post: operations["archive_workspace_api_v1_admin_workspaces__workspace_id__archive_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Pending */
        get: operations["list_pending_api_v1_approvals_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{approval_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Approval */
        get: operations["get_approval_api_v1_approvals__approval_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{approval_id}/decisions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decide */
        post: operations["decide_api_v1_approvals__approval_id__decisions_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/approvals/{approval_id}/view": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** View Approval */
        post: operations["view_approval_api_v1_approvals__approval_id__view_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/audit/events": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Events */
        get: operations["list_events_api_v1_audit_events_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/bootstrap": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Bootstrap */
        get: operations["bootstrap_api_v1_auth_bootstrap_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dev/demo-users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Demo Users */
        get: operations["demo_users_api_v1_dev_demo_users_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dev/session": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Session */
        post: operations["create_session_api_v1_dev_session_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/directory/candidates": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Candidates
         * @description Signed-in identities an admin can grant into the workspace — the picker
         *     behind the 'add member' email box, so an already-known account is chosen,
         *     not retyped.
         */
        get: operations["list_candidates_api_v1_directory_candidates_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/directory/members": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Members */
        get: operations["list_members_api_v1_directory_members_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/feedback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Feedback */
        get: operations["list_feedback_api_v1_feedback_get"];
        put?: never;
        /** Submit Feedback */
        post: operations["submit_feedback_api_v1_feedback_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/feedback/{feedback_id}/attachments/{attachment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Read Attachment
         * @description The screenshot bytes, for the inbox. Same scope as the inbox itself.
         */
        get: operations["read_attachment_api_v1_feedback__feedback_id__attachments__attachment_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Health */
        get: operations["health_api_v1_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/integrations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Integrations */
        get: operations["list_integrations_api_v1_integrations_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Documents */
        get: operations["list_documents_api_v1_knowledge_documents_get"];
        put?: never;
        /** Upload Document */
        post: operations["upload_document_api_v1_knowledge_documents_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/documents/jobs/{job_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Ingest Job */
        get: operations["get_ingest_job_api_v1_knowledge_documents_jobs__job_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/knowledge/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Delete Document */
        delete: operations["delete_document_api_v1_knowledge_documents__document_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Me */
        get: operations["me_api_v1_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/candidates/{candidate_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Candidate */
        get: operations["get_candidate_api_v1_memory_candidates__candidate_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/memory/items": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Items */
        get: operations["list_items_api_v1_memory_items_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Notifications */
        get: operations["list_notifications_api_v1_notifications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/read-all": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark All Notifications Read */
        post: operations["mark_all_notifications_read_api_v1_notifications_read_all_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/{notification_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Mark Notification Read */
        post: operations["mark_notification_read_api_v1_notifications__notification_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/operators": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Operators */
        get: operations["list_operators_api_v1_platform_operators_get"];
        put?: never;
        /** Add Operator */
        post: operations["add_operator_api_v1_platform_operators_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/operators/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Operator */
        delete: operations["remove_operator_api_v1_platform_operators__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/support-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Support Requests
         * @description Every tenant's grants waiting for assignment (`pending_assignment`), oldest first.
         */
        get: operations["list_support_requests_api_v1_platform_support_requests_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/support-requests/{grant_id}/assign": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Assign Support Request
         * @description 409 `support_staff_required` when the person is not support staff, 409
         *     `support_grant_wrong_status` when the grant is not waiting for assignment.
         *     No conflict-of-interest check yet (ADR 0024).
         */
        post: operations["assign_support_request_api_v1_platform_support_requests__grant_id__assign_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/support-staff": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Support Staff */
        get: operations["list_support_staff_api_v1_platform_support_staff_get"];
        put?: never;
        /**
         * Add Support Staff
         * @description By the email of an identity that has signed in; idempotent.
         */
        post: operations["add_support_staff_api_v1_platform_support_staff_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/support-staff/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /** Remove Support Staff */
        delete: operations["remove_support_staff_api_v1_platform_support_staff__user_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/tenants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Tenants */
        get: operations["list_tenants_api_v1_platform_tenants_get"];
        put?: never;
        /** Create Tenant */
        post: operations["create_tenant_api_v1_platform_tenants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/tenants/{tenant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Rename Tenant */
        patch: operations["rename_tenant_api_v1_platform_tenants__tenant_id__patch"];
        trace?: never;
    };
    "/api/v1/platform/tenants/{tenant_id}/lock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Lock Tenant */
        post: operations["lock_tenant_api_v1_platform_tenants__tenant_id__lock_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/tenants/{tenant_id}/offboard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Offboarding Status */
        get: operations["get_offboarding_status_api_v1_platform_tenants__tenant_id__offboard_get"];
        put?: never;
        /**
         * Initiate Offboarding
         * @description Files the request and flips the tenant to `offboarding` immediately.
         *
         *     202, not 200 or 204: the export/purge itself runs later, on the worker's
         *     offboarding lane — this call only starts it.
         */
        post: operations["initiate_offboarding_api_v1_platform_tenants__tenant_id__offboard_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/tenants/{tenant_id}/offboard/finalize": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Finalize Offboarding
         * @description The operator's explicit second step, once GET .../offboard reports
         *     `completed` — see ProvisioningService.finalize_offboarding's docstring
         *     for why this is not automatic.
         */
        post: operations["finalize_offboarding_api_v1_platform_tenants__tenant_id__offboard_finalize_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/tenants/{tenant_id}/org-admins": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Assign Org Admin */
        post: operations["assign_org_admin_api_v1_platform_tenants__tenant_id__org_admins_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/tenants/{tenant_id}/unlock": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Unlock Tenant */
        post: operations["unlock_tenant_api_v1_platform_tenants__tenant_id__unlock_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/platform/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Users
         * @description Every signed-in identity — the picker behind the assign-admin / add-operator
         *     email boxes, so an operator selects an account instead of retyping it.
         */
        get: operations["list_users_api_v1_platform_users_get"];
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
    "/api/v1/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ready */
        get: operations["ready_api_v1_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/runs/threads/{thread_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Thread
         * @description Stop the run in flight on this thread.
         *
         *     The runner's own `cancel_thread` takes a thread id and nothing else: it
         *     looks the task up in an in-process dict, which is safe while the only caller
         *     is a run that started it. Over HTTP the id is whatever the caller typed, so
         *     ownership is established HERE, against the database under the caller's
         *     tenant, before the runner is asked to do anything.
         *
         *     A thread this tenant has never run on is a 404 rather than a 403. "Not
         *     yours" and "never existed" are the same answer to someone probing ids, and
         *     the difference between them is exactly what a prober is trying to learn.
         */
        post: operations["cancel_thread_api_v1_runs_threads__thread_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Run */
        get: operations["get_run_api_v1_runs__run_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/runs/{run_id}/timeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Timeline */
        get: operations["get_timeline_api_v1_runs__run_id__timeline_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/support/catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Catalog */
        get: operations["catalog_api_v1_support_catalog_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/support/grants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Grants
         * @description `support.grant`: every grant of this workspace. `support.request` only:
         *     the caller's own requests.
         */
        get: operations["list_grants_api_v1_support_grants_get"];
        put?: never;
        /**
         * Request Grant
         * @description With `support.grant` the grant is made (`pending_assignment`); with only
         *     `support.request` it waits for a granter (`pending_approval`).
         */
        post: operations["request_grant_api_v1_support_grants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/support/grants/{grant_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Approve Grant */
        post: operations["approve_grant_api_v1_support_grants__grant_id__approve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/support/grants/{grant_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reject Grant */
        post: operations["reject_grant_api_v1_support_grants__grant_id__reject_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/support/grants/{grant_id}/revoke": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Revoke Grant
         * @description Takes effect at the staff member's next request.
         */
        post: operations["revoke_grant_api_v1_support_grants__grant_id__revoke_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/support/my-grants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * My Grants
         * @description The caller's grants, in force or ended in the last 30 days. Support
         *     staff only (403 `support_staff_required`); no tenant header is read.
         */
        get: operations["my_grants_api_v1_support_my_grants_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/zalo/connect": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Zalo Connect */
        post: operations["zalo_connect_api_v1_zalo_connect_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/zalo/disconnect": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Zalo Disconnect */
        post: operations["zalo_disconnect_api_v1_zalo_disconnect_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/zalo/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Zalo Status */
        get: operations["zalo_status_api_v1_zalo_status_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/zalo/workspace": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Zalo Workspace */
        get: operations["zalo_workspace_api_v1_zalo_workspace_get"];
        /** Zalo Choose Workspace */
        put: operations["zalo_choose_workspace_api_v1_zalo_workspace_put"];
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
        /** AddOperatorRequest */
        AddOperatorRequest: {
            /** Email */
            email: string;
            /** Note */
            note?: string | null;
        };
        /** AddSupportStaffRequest */
        AddSupportStaffRequest: {
            /** Email */
            email: string;
            /** Note */
            note?: string | null;
        };
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
        /** ApprovalView */
        ApprovalView: {
            /** Approval Type */
            approval_type: string;
            /** Can Decide */
            can_decide: boolean;
            /** Created At */
            created_at: string | null;
            /** Decided At */
            decided_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Payload */
            payload: {
                [key: string]: unknown;
            };
            /** Reason */
            reason: string;
            /** Requested By Me */
            requested_by_me: boolean;
            /** Required Scope */
            required_scope: string | null;
            /** Requires Comment */
            requires_comment: boolean;
            /** Run Id */
            run_id: string | null;
            /** Status */
            status: string;
        };
        /** ApprovalViewOutcome */
        ApprovalViewOutcome: {
            /** Code */
            code: string | null;
            /** Command Approve */
            command_approve: string | null;
            /** Command Reject */
            command_reject: string | null;
            /** Expires At */
            expires_at: string | null;
            /** Requires Comment */
            requires_comment: boolean;
            unavailable_reason: components["schemas"]["CodeUnavailable"] | null;
            /**
             * Viewed At
             * Format: date-time
             */
            viewed_at: string;
        };
        /** AssignOrgAdminRequest */
        AssignOrgAdminRequest: {
            /** Email */
            email: string;
        };
        /** AssignSupportRequest */
        AssignSupportRequest: {
            /**
             * Staff User Id
             * Format: uuid
             */
            staff_user_id: string;
        };
        /** AssignedSupportGrantView */
        AssignedSupportGrantView: {
            /**
             * Activated At
             * Format: date-time
             */
            activated_at: string;
            /** Code */
            code: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Grant Id
             * Format: uuid
             */
            grant_id: string;
            /**
             * Staff User Id
             * Format: uuid
             */
            staff_user_id: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
        };
        /**
         * AuditActorKind
         * @description Who the actor of an event was, as the customer's trail shows it.
         *
         *     `support` is a member of the support team acting under a grant: the event
         *     names the grant (`details.support_grant_id`) AND its actor is the person
         *     that grant was assigned to. The grant id alone is not enough, because the
         *     customer's own request, approval and revocation of a grant carry it too and
         *     were done by the customer's people.
         * @enum {string}
         */
        AuditActorKind: "user" | "support";
        /**
         * AuditEventView
         * @description One audit row as the screen shows it.
         *
         *     ``actor_id`` is here because it was the one thing the table could not show:
         *     the column exists on the row and is not inside ``details``, so dropping it
         *     from this view made "who did this" unanswerable from the UI for every action,
         *     not only sharing (spec 03.1 BR10 names it explicitly).
         *
         *     ``actor_display_name`` is the actor's name today (``None`` for an actor
         *     that is no user, such as a background lane), and ``actor_kind`` says
         *     whether the actor was the support team acting under a grant: support
         *     staff are no member of the customer's, so a name alone would not say it.
         */
        AuditEventView: {
            /** Action */
            action: string;
            /** Actor Display Name */
            actor_display_name: string | null;
            /** Actor Id */
            actor_id: string;
            actor_kind: components["schemas"]["AuditActorKind"];
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Policy Decision */
            policy_decision: string | null;
            /** Resource Id */
            resource_id: string;
            /** Resource Type */
            resource_type: string;
            /** Trace Id */
            trace_id: string | null;
        };
        /** Body_submit_feedback_api_v1_feedback_post */
        Body_submit_feedback_api_v1_feedback_post: {
            /**
             * Images
             * @default []
             */
            images: string[];
            /** Message */
            message: string;
            /** Module */
            module: string;
            /** Page Path */
            page_path?: string | null;
            /** Suggestion */
            suggestion?: string | null;
        };
        /** Body_upload_document_api_v1_knowledge_documents_post */
        Body_upload_document_api_v1_knowledge_documents_post: {
            /**
             * Classification
             * @default internal
             */
            classification: string;
            /**
             * Domain
             * @default shared
             */
            domain: string;
            /** File */
            file: string;
            /**
             * Scope
             * @default tenant
             */
            scope: string;
            /**
             * Source Version
             * @default 1
             */
            source_version: string;
            /** Title */
            title: string;
        };
        /** BootstrapResponse */
        BootstrapResponse: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /**
             * Is Platform Operator
             * @default false
             */
            is_platform_operator: boolean;
            /**
             * Is Support Staff
             * @default false
             */
            is_support_staff: boolean;
            /** Memberships */
            memberships: components["schemas"]["WorkspaceMembershipModel"][];
            /**
             * Principal Id
             * Format: uuid
             */
            principal_id: string;
            /** Subject */
            subject: string;
        };
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
            /** Sheet */
            sheet: string;
        };
        /**
         * CancelResult
         * @description Whether a run was actually stopped, not whether the request was understood.
         *
         *     `False` is an ordinary answer: the turn had already finished, or another
         *     process holds it. A caller pressing Stop twice should get 200 both times —
         *     the second one describes a thread that is already not running, which is what
         *     they asked for.
         */
        CancelResult: {
            /** Cancelled */
            cancelled: boolean;
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
        CaseStatus: "received" | "awaiting_approval" | "approved" | "rejected" | "rfq_drafted" | "supplier_selected" | "po_drafted";
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
        /**
         * CodeUnavailable
         * @description Why the portal offers no code. Each one is a sentence on the page.
         * @enum {string}
         */
        CodeUnavailable: "not_pending" | "cannot_decide" | "requester" | "web_only" | "not_linked" | "comment_required" | "channel_off";
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
        /** CreateAccountRequest */
        CreateAccountRequest: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /** Memberships */
            memberships: components["schemas"]["WorkspaceRolesBody"][];
        };
        /** CreateTenantRequest */
        CreateTenantRequest: {
            /** Name */
            name: string;
            /** Plan Id */
            plan_id: string;
            /** Slug */
            slug: string;
        };
        /** CreateWorkspaceBody */
        CreateWorkspaceBody: {
            /** Name */
            name: string;
            /** Slug */
            slug: string;
        };
        /** CreatedAccountView */
        CreatedAccountView: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /** Temporary Password */
            temporary_password: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
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
        /** DecisionRequest */
        DecisionRequest: {
            /** Approve */
            approve: boolean;
            /** Approved Action Ids */
            approved_action_ids?: string[] | null;
            /**
             * Comment
             * @default
             */
            comment: string;
            /** Reasons */
            reasons?: {
                [key: string]: string;
            };
            /** Subject Version */
            subject_version?: number | null;
        };
        /** DemoUser */
        DemoUser: {
            /** Description */
            description: string;
            /** Display Name */
            display_name: string;
            /** Roles */
            roles: string[];
            /** Subject */
            subject: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Tenant Name */
            tenant_name: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** DevSessionRequest */
        DevSessionRequest: {
            /** Subject */
            subject: string;
        };
        /** DevSessionResponse */
        DevSessionResponse: {
            /** Display Name */
            display_name: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /** Roles */
            roles: string[];
            /** Subject */
            subject: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Tenant Name */
            tenant_name: string;
            /** Token */
            token: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /**
         * Disposition
         * @description What DW2 did with one mail.
         * @enum {string}
         */
        Disposition: "opened" | "to_person";
        /** FeedbackAttachmentView */
        FeedbackAttachmentView: {
            /** Content Type */
            content_type: string;
            /** Id */
            id: string;
            /** Size Bytes */
            size_bytes: number;
        };
        /** FeedbackView */
        FeedbackView: {
            /**
             * Attachments
             * @default []
             */
            attachments: components["schemas"]["FeedbackAttachmentView"][];
            /** Author Name */
            author_name: string;
            /** Category */
            category: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Id */
            id: string;
            /** Message */
            message: string;
            /** Module */
            module?: string | null;
            /** Page Path */
            page_path?: string | null;
            /** Suggestion */
            suggestion?: string | null;
        };
        /** Finding */
        Finding: {
            code: components["schemas"]["PurchaseFindingCode"];
            /** Line No */
            line_no?: number | null;
        };
        /** GrantMemberRequest */
        GrantMemberRequest: {
            /**
             * Department
             * @default general
             */
            department: string;
            /** Email */
            email: string;
            /** Role Keys */
            role_keys: string[];
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HealthResponse */
        HealthResponse: {
            /** Api Version */
            api_version: string;
            /** Status */
            status: string;
            /** Version */
            version: string;
        };
        /** HierarchyMemberView */
        HierarchyMemberView: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /** Manager User Id */
            manager_user_id: string | null;
            /** Role Keys */
            role_keys: string[];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** IdentityRefView */
        IdentityRefView: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
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
        /** InboxView */
        InboxView: {
            /** Items */
            items: components["schemas"]["NotificationView"][];
            /** Unread */
            unread: number;
        };
        /** IngestJobView */
        IngestJobView: {
            /** Attempts */
            attempts: number;
            /** Chunk Count */
            chunk_count: number | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Document Id */
            document_id: string | null;
            /** Error */
            error: string | null;
            /** Filename */
            filename: string;
            /**
             * Job Id
             * Format: uuid
             */
            job_id: string;
            /** Scope */
            scope: string;
            /** Status */
            status: string;
            /** Title */
            title: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /**
             * Warnings
             * @default []
             */
            warnings: string[];
        };
        /** IntegrationView */
        IntegrationView: {
            /** Approval Policy */
            approval_policy: string;
            /** Description */
            description: string;
            /** Idempotent */
            idempotent: boolean;
            /** Required Scopes */
            required_scopes: string[];
            /**
             * Requires Approval
             * @description True if this tool always requires approval, at every autonomy level. False does not mean it never pauses: whether a given call does depends on the run.
             */
            requires_approval: boolean;
            /** Side Effect Level */
            side_effect_level: string;
            /** Timeout Seconds */
            timeout_seconds: number;
            /** Tool */
            tool: string;
            /** Version */
            version: string;
        };
        /** InviteMemberRequest */
        InviteMemberRequest: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string;
            /** Memberships */
            memberships: components["schemas"]["WorkspaceRolesBody"][];
        };
        /** KnowledgeDocumentView */
        KnowledgeDocumentView: {
            /** Chunk Count */
            chunk_count: number;
            /** Classification */
            classification: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Document Id
             * Format: uuid
             */
            document_id: string;
            /** Domain */
            domain: string;
            /** Index Version */
            index_version: string | null;
            /** Scope */
            scope: string;
            /** Source Version */
            source_version: string;
            /** Title */
            title: string;
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
        /** LoginAccountView */
        LoginAccountView: {
            /** Email */
            email: string;
            /** Enabled */
            enabled: boolean;
        };
        /** MeResponse */
        MeResponse: {
            /** Clearance */
            clearance: string;
            /** Feature Flags */
            feature_flags: string[];
            /** Plan Id */
            plan_id: string;
            /**
             * Principal Id
             * Format: uuid
             */
            principal_id: string;
            /** Roles */
            roles: string[];
            /** Scopes */
            scopes: string[];
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /**
         * MemberMembershipsView
         * @description A person's memberships in this tenant after a change; empty when none is left.
         */
        MemberMembershipsView: {
            /** Memberships */
            memberships: components["schemas"]["MemberWorkspaceView"][];
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** MemberRefView */
        MemberRefView: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** MemberWorkspaceView */
        MemberWorkspaceView: {
            /** Role Keys */
            role_keys: string[];
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
            /** Workspace Name */
            workspace_name: string;
        };
        /** MemoryCandidateView */
        MemoryCandidateView: {
            /**
             * Candidate Id
             * Format: uuid
             */
            candidate_id: string;
            /** Classification */
            classification: string;
            /** Confidence */
            confidence: number;
            /** Content */
            content: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By Run Id
             * Format: uuid
             */
            created_by_run_id: string;
            /** Decision */
            decision: string;
            /** Fact Key */
            fact_key: string | null;
            /** Memory Id */
            memory_id: string | null;
            /** Memory Type */
            memory_type: string;
            /** Provenance Refs */
            provenance_refs: {
                [key: string]: unknown;
            }[];
            /** Structured Facts */
            structured_facts: {
                [key: string]: unknown;
            };
            /** Subject Refs */
            subject_refs: string[];
            /** Worker Id */
            worker_id: string;
        };
        /** MemoryItemView */
        MemoryItemView: {
            /** Classification */
            classification: string;
            /** Confidence */
            confidence: number;
            /** Content */
            content: string;
            /**
             * Created By Run Id
             * Format: uuid
             */
            created_by_run_id: string;
            /**
             * Memory Id
             * Format: uuid
             */
            memory_id: string;
            /** Memory Type */
            memory_type: string;
            /** Provenance Count */
            provenance_count: number;
            /**
             * Valid From
             * Format: date-time
             */
            valid_from: string;
            /** Worker Id */
            worker_id: string;
        };
        /**
         * MySupportGrantModel
         * @description A grant assigned to the caller: enough to open it, nothing the customer
         *     wrote (no reason).
         */
        MySupportGrantModel: {
            /** Activated At */
            activated_at: string | null;
            /** Code */
            code: string;
            /** Expires At */
            expires_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Resource Id */
            resource_id: string | null;
            /** Resource Label */
            resource_label: string;
            /** Resource Type */
            resource_type: string;
            /** Revoked At */
            revoked_at: string | null;
            /** Scope Set Key */
            scope_set_key: string;
            /** Scope Set Label */
            scope_set_label: string;
            /** Scopes */
            scopes: string[];
            /** State */
            state: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Tenant Name */
            tenant_name: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
            /** Workspace Name */
            workspace_name: string;
        };
        /** NewTenantView */
        NewTenantView: {
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** NotificationView */
        NotificationView: {
            /** Body */
            body: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Link */
            link: string | null;
            /** Read At */
            read_at: string | null;
            /** Title */
            title: string;
        };
        /** OffboardingStatusView */
        OffboardingStatusView: {
            /** Error */
            error: string | null;
            /** Export Key */
            export_key: string | null;
            /**
             * Request Id
             * Format: uuid
             */
            request_id: string;
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
            /** Status */
            status: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
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
        /** OperatorView */
        OperatorView: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /** Note */
            note: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * Page
         * @description A page of results and the cursor that continues it.
         *
         *     ``next_cursor`` is ``None`` on the last page, and that — not an empty
         *     ``items`` — is the client's stop condition: a filtered listing can return an
         *     empty page in the middle of a run and still have more rows behind it.
         */
        Page_ApprovalView_: {
            /** Items */
            items: components["schemas"]["ApprovalView"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /**
         * Page
         * @description A page of results and the cursor that continues it.
         *
         *     ``next_cursor`` is ``None`` on the last page, and that — not an empty
         *     ``items`` — is the client's stop condition: a filtered listing can return an
         *     empty page in the middle of a run and still have more rows behind it.
         */
        Page_AuditEventView_: {
            /** Items */
            items: components["schemas"]["AuditEventView"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /**
         * Page
         * @description A page of results and the cursor that continues it.
         *
         *     ``next_cursor`` is ``None`` on the last page, and that — not an empty
         *     ``items`` — is the client's stop condition: a filtered listing can return an
         *     empty page in the middle of a run and still have more rows behind it.
         */
        Page_FeedbackView_: {
            /** Items */
            items: components["schemas"]["FeedbackView"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /**
         * Page
         * @description A page of results and the cursor that continues it.
         *
         *     ``next_cursor`` is ``None`` on the last page, and that — not an empty
         *     ``items`` — is the client's stop condition: a filtered listing can return an
         *     empty page in the middle of a run and still have more rows behind it.
         */
        Page_KnowledgeDocumentView_: {
            /** Items */
            items: components["schemas"]["KnowledgeDocumentView"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /**
         * Page
         * @description A page of results and the cursor that continues it.
         *
         *     ``next_cursor`` is ``None`` on the last page, and that — not an empty
         *     ``items`` — is the client's stop condition: a filtered listing can return an
         *     empty page in the middle of a run and still have more rows behind it.
         */
        Page_MemoryItemView_: {
            /** Items */
            items: components["schemas"]["MemoryItemView"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** PermissionSetView */
        PermissionSetView: {
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Scopes */
            scopes: string[];
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
         *     this slice reads the first and the third).
         * @enum {string}
         */
        PrSource: "form" | "mail";
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
            rfq?: components["schemas"]["RfqRound"] | null;
            /** Rules Ref */
            rules_ref: string;
            selection?: components["schemas"]["Selection"] | null;
            source: components["schemas"]["PrSource"];
            /** Source Ref */
            source_ref?: string | null;
            status: components["schemas"]["CaseStatus"];
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
         * PurchasingRuleKey
         * @description What a tenant may hold its own version of.
         * @enum {string}
         */
        PurchasingRuleKey: "purchasing_rules";
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
        /** PurchasingRulesView */
        PurchasingRulesView: {
            /** Keys */
            keys: components["schemas"]["PurchasingKeyInForce"][];
            /** Versions */
            versions: components["schemas"]["PurchasingRuleVersionView"][];
        };
        /** ReadinessResponse */
        ReadinessResponse: {
            /** Checks */
            checks: {
                [key: string]: string;
            };
            /** Status */
            status: string;
        };
        /** RejectSupportGrantBody */
        RejectSupportGrantBody: {
            /** Reason */
            reason: string;
        };
        /** RenameTenantRequest */
        RenameTenantRequest: {
            /** Name */
            name: string;
        };
        /** RenameWorkspaceBody */
        RenameWorkspaceBody: {
            /** Name */
            name: string;
        };
        /** RequestSupportGrantBody */
        RequestSupportGrantBody: {
            /** Duration Hours */
            duration_hours: number;
            /** Reason */
            reason: string;
            /** Resource Id */
            resource_id?: string | null;
            /** Resource Type */
            resource_type: string;
            /** Scope Set Key */
            scope_set_key: string;
        };
        /**
         * RfqDraft
         * @description One supplier's RFQ: who receives it, which lines, and the words.
         */
        RfqDraft: {
            /** Body */
            body: string;
            /** Line Nos */
            line_nos: number[];
            /** Subject */
            subject: string;
            /** Supplier Code */
            supplier_code: string;
            /** To */
            to: string[];
            /**
             * Written By
             * @enum {string}
             */
            written_by: "model" | "template";
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
        /** RoleView */
        RoleView: {
            /** Administrative */
            administrative: boolean;
            /** Key */
            key: string;
            /** Name */
            name: string;
            /** Scopes */
            scopes: string[];
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
        /** RunView */
        RunView: {
            /** Approval Request Id */
            approval_request_id: string | null;
            /** Error */
            error: {
                [key: string]: unknown;
            } | null;
            /** Graph Version */
            graph_version: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Release Manifest Ref */
            release_manifest_ref: string | null;
            /** Result */
            result: {
                [key: string]: unknown;
            } | null;
            /** Status */
            status: string;
            /** Worker Id */
            worker_id: string;
            /** Worker Version */
            worker_version: string;
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
        /** SetEnabledRequest */
        SetEnabledRequest: {
            /** Enabled */
            enabled: boolean;
        };
        /** SetManagerBody */
        SetManagerBody: {
            /** Manager User Id */
            manager_user_id?: string | null;
        };
        /** SetMembershipsRequest */
        SetMembershipsRequest: {
            /** Memberships */
            memberships: components["schemas"]["WorkspaceRolesBody"][];
        };
        /** SetPermissionSetsBody */
        SetPermissionSetsBody: {
            /** Permission Set Keys */
            permission_set_keys: string[];
        };
        /** SodRuleView */
        SodRuleView: {
            /** Description */
            description: string;
            /** Key */
            key: string;
            /** Left Scopes */
            left_scopes: string[];
            /** Right Scopes */
            right_scopes: string[];
            /** Waivable */
            waivable: boolean;
            waiver: components["schemas"]["SodWaiverView"] | null;
        };
        /** SodWaiverView */
        SodWaiverView: {
            /** Confirmed At */
            confirmed_at: string | null;
            /** Confirmed By */
            confirmed_by: string | null;
            /**
             * Granted At
             * Format: date-time
             */
            granted_at: string;
            /**
             * Granted By
             * Format: uuid
             */
            granted_by: string;
            /** Reason */
            reason: string;
        };
        /**
         * StalledEventView
         * @description An outbox event that spent its attempts: the kind of its error only,
         *     never the text, which can carry what the failing statement held.
         */
        StalledEventView: {
            /** Attempts */
            attempts: number;
            /** Error Kind */
            error_kind: string;
            /** Event Type */
            event_type: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
        };
        /** SupportGrantModel */
        SupportGrantModel: {
            /** Activated At */
            activated_at: string | null;
            /** Code */
            code: string;
            /** Duration Hours */
            duration_hours: number;
            /** Expires At */
            expires_at: string | null;
            /** Granted At */
            granted_at: string | null;
            /** Granted By */
            granted_by: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Reason */
            reason: string;
            /** Reject Reason */
            reject_reason: string | null;
            /** Rejected At */
            rejected_at: string | null;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /** Requested By */
            requested_by: string | null;
            /** Resource Id */
            resource_id: string | null;
            /** Resource Label */
            resource_label: string;
            /** Resource Type */
            resource_type: string;
            /** Revoked At */
            revoked_at: string | null;
            /** Scope Set Key */
            scope_set_key: string;
            /** Scope Set Label */
            scope_set_label: string;
            /** Staff User Id */
            staff_user_id: string | null;
            /** State */
            state: string;
            /** Status */
            status: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /**
         * SupportRequestView
         * @description A grant waiting for a person: what the operator chooses by, no more.
         */
        SupportRequestView: {
            /** Code */
            code: string;
            /** Duration Hours */
            duration_hours: number;
            /**
             * Grant Id
             * Format: uuid
             */
            grant_id: string;
            /** Reason */
            reason: string;
            /**
             * Requested At
             * Format: date-time
             */
            requested_at: string;
            /** Resource Label */
            resource_label: string;
            /** Resource Type */
            resource_type: string;
            /** Scope Set Key */
            scope_set_key: string;
            /** Scope Set Label */
            scope_set_label: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Tenant Name */
            tenant_name: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
            /** Workspace Name */
            workspace_name: string;
        };
        /**
         * SupportScopeSetView
         * @description A grantable set: no scope list, only what a person chooses by.
         */
        SupportScopeSetView: {
            /** Key */
            key: string;
            /** Label */
            label: string;
            /** Resource Types */
            resource_types: string[];
        };
        /** SupportStaffView */
        SupportStaffView: {
            /**
             * Added At
             * Format: date-time
             */
            added_at: string;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /** Note */
            note: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** TemporaryPasswordView */
        TemporaryPasswordView: {
            /** Temporary Password */
            temporary_password: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** TenantMemberView */
        TenantMemberView: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /** Memberships */
            memberships: components["schemas"]["MemberWorkspaceView"][];
            /** Status */
            status: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** TenantSettingsView */
        TenantSettingsView: {
            /** Locale */
            locale: string | null;
            /**
             * Max Autonomy Level
             * @enum {string}
             */
            max_autonomy_level: "A0" | "A1" | "A2" | "A3" | "A4";
            /** Name */
            name: string;
            /** Record Visibility */
            record_visibility: string;
            /** Slug */
            slug: string;
            /** Status */
            status: string;
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Timezone */
            timezone: string | null;
        };
        /** TenantView */
        TenantView: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Member Count */
            member_count: number;
            /** Name */
            name: string;
            /** Plan Id */
            plan_id: string | null;
            /** Slug */
            slug: string;
            /** Status */
            status: string;
            /** Workspace Count */
            workspace_count: number;
        };
        /** TimelineEvent */
        TimelineEvent: {
            /** Action */
            action: string;
            /** Details */
            details: {
                [key: string]: unknown;
            };
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /** Policy Decision */
            policy_decision: string | null;
            /** Resource Id */
            resource_id: string;
            /** Resource Type */
            resource_type: string;
        };
        /** UpdateTenantBody */
        UpdateTenantBody: {
            /** Locale */
            locale?: string | null;
            /** Max Autonomy Level */
            max_autonomy_level?: ("A0" | "A1" | "A2" | "A3" | "A4") | null;
            /** Name */
            name?: string | null;
            /** Record Visibility */
            record_visibility?: string | null;
            /** Timezone */
            timezone?: string | null;
        };
        /** UserRefView */
        UserRefView: {
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
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
        /** ViewRequest */
        ViewRequest: {
            /**
             * Comment
             * @default
             */
            comment: string;
            /**
             * Issue Code
             * @default false
             */
            issue_code: boolean;
        };
        /** WaiverDecisionBody */
        WaiverDecisionBody: {
            /** Reason */
            reason: string;
        };
        /** WorkspaceMemberView */
        WorkspaceMemberView: {
            /** Department */
            department: string;
            /** Display Name */
            display_name: string;
            /** Email */
            email: string | null;
            /** Permission Set Keys */
            permission_set_keys: string[];
            /** Role Keys */
            role_keys: string[];
            /** Service */
            service: boolean;
            /** Status */
            status: string;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /** WorkspaceMembershipModel */
        WorkspaceMembershipModel: {
            /** Role Names */
            role_names?: {
                [key: string]: string;
            };
            /** Roles */
            roles: string[];
            /** Scopes */
            scopes: string[];
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /** Tenant Name */
            tenant_name: string;
            /** Tenant Slug */
            tenant_slug: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
            /** Workspace Name */
            workspace_name: string;
            /** Workspace Slug */
            workspace_slug: string;
        };
        /** WorkspaceRefView */
        WorkspaceRefView: {
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** WorkspaceRolesBody */
        WorkspaceRolesBody: {
            /** Role Keys */
            role_keys: string[];
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** WorkspaceSummaryView */
        WorkspaceSummaryView: {
            /** Archived */
            archived: boolean;
            /** Member Count */
            member_count: number;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** ZaloConnectView */
        ZaloConnectView: {
            /** Code */
            code: string;
            /** Deep Link */
            deep_link: string | null;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
        };
        /** ZaloStatusView */
        ZaloStatusView: {
            /** Linked */
            linked: boolean;
        };
        /** ZaloWorkspaceChoice */
        ZaloWorkspaceChoice: {
            /**
             * Tenant Id
             * Format: uuid
             */
            tenant_id: string;
            /**
             * Workspace Id
             * Format: uuid
             */
            workspace_id: string;
        };
        /** ZaloWorkspaceView */
        ZaloWorkspaceView: {
            /** Tenant Id */
            tenant_id: string | null;
            /** Workspace Id */
            workspace_id: string | null;
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
    list_accounts_api_v1_admin_accounts_get: {
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
                    "application/json": components["schemas"]["LoginAccountView"][];
                };
            };
        };
    };
    create_account_api_v1_admin_accounts_post: {
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
                "application/json": components["schemas"]["CreateAccountRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CreatedAccountView"];
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
    set_enabled_api_v1_admin_accounts__user_id__enabled_put: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetEnabledRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
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
    reset_password_api_v1_admin_accounts__user_id__password_reset_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["TemporaryPasswordView"];
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
    list_background_failures_api_v1_admin_background_failures_get: {
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
                    "application/json": components["schemas"]["StalledEventView"][];
                };
            };
        };
    };
    retry_background_failure_api_v1_admin_background_failures__event_id__retry_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                event_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    get_hierarchy_api_v1_admin_hierarchy_get: {
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
                    "application/json": components["schemas"]["HierarchyMemberView"][];
                };
            };
        };
    };
    set_manager_api_v1_admin_hierarchy__user_id__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetManagerBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
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
    invite_member_api_v1_admin_invitations_post: {
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
                "application/json": components["schemas"]["InviteMemberRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemberRefView"];
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
    list_members_api_v1_admin_members_get: {
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
                    "application/json": components["schemas"]["TenantMemberView"][];
                };
            };
        };
    };
    grant_member_api_v1_admin_members_post: {
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
                "application/json": components["schemas"]["GrantMemberRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemberRefView"];
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
    revoke_member_api_v1_admin_members__user_id__delete: {
        parameters: {
            query: {
                workspace_id: string;
            };
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    set_memberships_api_v1_admin_members__user_id__memberships_put: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetMembershipsRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MemberMembershipsView"];
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
    set_permission_sets_api_v1_admin_members__user_id__permission_sets_put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SetPermissionSetsBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
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
    list_permission_sets_api_v1_admin_permission_sets_get: {
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
                    "application/json": components["schemas"]["PermissionSetView"][];
                };
            };
        };
    };
    list_roles_api_v1_admin_roles_get: {
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
                    "application/json": components["schemas"]["RoleView"][];
                };
            };
        };
    };
    list_separation_of_duties_api_v1_admin_separation_of_duties_get: {
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
                    "application/json": components["schemas"]["SodRuleView"][];
                };
            };
        };
    };
    waive_separation_of_duties_rule_api_v1_admin_separation_of_duties__rule_key__waiver_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WaiverDecisionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
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
    confirm_separation_of_duties_waiver_api_v1_admin_separation_of_duties__rule_key__waiver_confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WaiverDecisionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
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
    revoke_separation_of_duties_waiver_api_v1_admin_separation_of_duties__rule_key__waiver_revoke_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                rule_key: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WaiverDecisionBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            204: {
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
    get_tenant_api_v1_admin_tenant_get: {
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
                    "application/json": components["schemas"]["TenantSettingsView"];
                };
            };
        };
    };
    update_tenant_api_v1_admin_tenant_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateTenantBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantSettingsView"];
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
    list_workspaces_api_v1_admin_workspaces_get: {
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
                    "application/json": components["schemas"]["WorkspaceSummaryView"][];
                };
            };
        };
    };
    create_workspace_api_v1_admin_workspaces_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateWorkspaceBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceRefView"];
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
    rename_workspace_api_v1_admin_workspaces__workspace_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RenameWorkspaceBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WorkspaceRefView"];
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
    archive_workspace_api_v1_admin_workspaces__workspace_id__archive_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                workspace_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    list_pending_api_v1_approvals_get: {
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
                    "application/json": components["schemas"]["Page_ApprovalView_"];
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
    get_approval_api_v1_approvals__approval_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                approval_id: string;
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
                    "application/json": components["schemas"]["ApprovalView"];
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
    decide_api_v1_approvals__approval_id__decisions_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                approval_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DecisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalView"];
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
    view_approval_api_v1_approvals__approval_id__view_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                approval_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ViewRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ApprovalViewOutcome"];
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
    list_events_api_v1_audit_events_get: {
        parameters: {
            query?: {
                limit?: number;
                /** @description Opaque cursor from a previous page. */
                cursor?: string | null;
                /** @description Only the events of this support grant. */
                support_grant_id?: string | null;
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
                    "application/json": components["schemas"]["Page_AuditEventView_"];
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
    bootstrap_api_v1_auth_bootstrap_get: {
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
                    "application/json": components["schemas"]["BootstrapResponse"];
                };
            };
        };
    };
    demo_users_api_v1_dev_demo_users_get: {
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
                    "application/json": components["schemas"]["DemoUser"][];
                };
            };
        };
    };
    create_session_api_v1_dev_session_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DevSessionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DevSessionResponse"];
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
    list_candidates_api_v1_directory_candidates_get: {
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
                    "application/json": components["schemas"]["IdentityRefView"][];
                };
            };
        };
    };
    list_members_api_v1_directory_members_get: {
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
                    "application/json": components["schemas"]["WorkspaceMemberView"][];
                };
            };
        };
    };
    list_feedback_api_v1_feedback_get: {
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
                    "application/json": components["schemas"]["Page_FeedbackView_"];
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
    submit_feedback_api_v1_feedback_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_submit_feedback_api_v1_feedback_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
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
    read_attachment_api_v1_feedback__feedback_id__attachments__attachment_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                feedback_id: string;
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
    health_api_v1_health_get: {
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
                    "application/json": components["schemas"]["HealthResponse"];
                };
            };
        };
    };
    list_integrations_api_v1_integrations_get: {
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
                    "application/json": components["schemas"]["IntegrationView"][];
                };
            };
        };
    };
    list_documents_api_v1_knowledge_documents_get: {
        parameters: {
            query?: {
                limit?: number;
                /** @description Opaque cursor from a previous page. */
                cursor?: string | null;
                /** @description Narrow the listing to one domain. */
                domain?: string | null;
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
                    "application/json": components["schemas"]["Page_KnowledgeDocumentView_"];
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
    upload_document_api_v1_knowledge_documents_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": components["schemas"]["Body_upload_document_api_v1_knowledge_documents_post"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["IngestJobView"];
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
    get_ingest_job_api_v1_knowledge_documents_jobs__job_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_id: string;
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
                    "application/json": components["schemas"]["IngestJobView"];
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
    delete_document_api_v1_knowledge_documents__document_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    me_api_v1_me_get: {
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
                    "application/json": components["schemas"]["MeResponse"];
                };
            };
        };
    };
    get_candidate_api_v1_memory_candidates__candidate_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                candidate_id: string;
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
                    "application/json": components["schemas"]["MemoryCandidateView"];
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
    list_items_api_v1_memory_items_get: {
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
                    "application/json": components["schemas"]["Page_MemoryItemView_"];
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
    list_notifications_api_v1_notifications_get: {
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
                    "application/json": components["schemas"]["InboxView"];
                };
            };
        };
    };
    mark_all_notifications_read_api_v1_notifications_read_all_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    mark_notification_read_api_v1_notifications__notification_id__read_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                notification_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    list_operators_api_v1_platform_operators_get: {
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
                    "application/json": components["schemas"]["OperatorView"][];
                };
            };
        };
    };
    add_operator_api_v1_platform_operators_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddOperatorRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserRefView"];
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
    remove_operator_api_v1_platform_operators__user_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    list_support_requests_api_v1_platform_support_requests_get: {
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
                    "application/json": components["schemas"]["SupportRequestView"][];
                };
            };
        };
    };
    assign_support_request_api_v1_platform_support_requests__grant_id__assign_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                grant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssignSupportRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AssignedSupportGrantView"];
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
    list_support_staff_api_v1_platform_support_staff_get: {
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
                    "application/json": components["schemas"]["SupportStaffView"][];
                };
            };
        };
    };
    add_support_staff_api_v1_platform_support_staff_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AddSupportStaffRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserRefView"];
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
    remove_support_staff_api_v1_platform_support_staff__user_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    list_tenants_api_v1_platform_tenants_get: {
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
                    "application/json": components["schemas"]["TenantView"][];
                };
            };
        };
    };
    create_tenant_api_v1_platform_tenants_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateTenantRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NewTenantView"];
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
    rename_tenant_api_v1_platform_tenants__tenant_id__patch: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RenameTenantRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TenantView"];
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
    lock_tenant_api_v1_platform_tenants__tenant_id__lock_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    get_offboarding_status_api_v1_platform_tenants__tenant_id__offboard_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
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
                    "application/json": components["schemas"]["OffboardingStatusView"];
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
    initiate_offboarding_api_v1_platform_tenants__tenant_id__offboard_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
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
                    "application/json": components["schemas"]["OffboardingStatusView"];
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
    finalize_offboarding_api_v1_platform_tenants__tenant_id__offboard_finalize_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    assign_org_admin_api_v1_platform_tenants__tenant_id__org_admins_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["AssignOrgAdminRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserRefView"];
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
    unlock_tenant_api_v1_platform_tenants__tenant_id__unlock_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tenant_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
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
    list_users_api_v1_platform_users_get: {
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
                    "application/json": components["schemas"]["UserRefView"][];
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
    ready_api_v1_ready_get: {
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
                    "application/json": components["schemas"]["ReadinessResponse"];
                };
            };
        };
    };
    cancel_thread_api_v1_runs_threads__thread_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                thread_id: string;
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
                    "application/json": components["schemas"]["CancelResult"];
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
    get_run_api_v1_runs__run_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
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
                    "application/json": components["schemas"]["RunView"];
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
    get_timeline_api_v1_runs__run_id__timeline_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
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
                    "application/json": components["schemas"]["TimelineEvent"][];
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
    catalog_api_v1_support_catalog_get: {
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
                    "application/json": components["schemas"]["SupportScopeSetView"][];
                };
            };
        };
    };
    list_grants_api_v1_support_grants_get: {
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
                    "application/json": components["schemas"]["SupportGrantModel"][];
                };
            };
        };
    };
    request_grant_api_v1_support_grants_post: {
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
                "application/json": components["schemas"]["RequestSupportGrantBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupportGrantModel"];
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
    approve_grant_api_v1_support_grants__grant_id__approve_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                grant_id: string;
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
                    "application/json": components["schemas"]["SupportGrantModel"];
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
    reject_grant_api_v1_support_grants__grant_id__reject_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                grant_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RejectSupportGrantBody"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SupportGrantModel"];
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
    revoke_grant_api_v1_support_grants__grant_id__revoke_post: {
        parameters: {
            query?: never;
            header?: {
                /** @description Optional. Retrying with the same key returns the first response instead of acting twice; reusing it for a different request is a 409. */
                "Idempotency-Key"?: string | null;
            };
            path: {
                grant_id: string;
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
                    "application/json": components["schemas"]["SupportGrantModel"];
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
    my_grants_api_v1_support_my_grants_get: {
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
                    "application/json": components["schemas"]["MySupportGrantModel"][];
                };
            };
        };
    };
    zalo_connect_api_v1_zalo_connect_post: {
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
                    "application/json": components["schemas"]["ZaloConnectView"];
                };
            };
        };
    };
    zalo_disconnect_api_v1_zalo_disconnect_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    zalo_status_api_v1_zalo_status_get: {
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
                    "application/json": components["schemas"]["ZaloStatusView"];
                };
            };
        };
    };
    zalo_workspace_api_v1_zalo_workspace_get: {
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
                    "application/json": components["schemas"]["ZaloWorkspaceView"];
                };
            };
        };
    };
    zalo_choose_workspace_api_v1_zalo_workspace_put: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ZaloWorkspaceChoice"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ZaloWorkspaceView"];
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
