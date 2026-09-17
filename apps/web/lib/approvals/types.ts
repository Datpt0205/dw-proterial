import type { ApiClient } from "@dw/api-client";

/** A context whose runs live in their own service, and the client reaching it. */
export interface ApprovalHost {
  /** Approval types starting with this prefix are decided by `client`. */
  prefix: string;
  client: () => ApiClient;
}
