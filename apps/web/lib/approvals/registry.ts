import type { ApiClient } from "@dw/api-client";
import { apiClient } from "../session";
import type { ApprovalHost } from "./types";

/**
 * Which service decides an approval — the ONLY place that mapping is made.
 *
 * The inbox is one list, but a decision resumes a checkpointed run and graphs
 * are registered per process, so the owner has to be picked per approval.
 *
 * PLUG-IN POINT: a context running in its own service ships a manifest in its
 * route folder and adds one import plus one entry here. Contexts hosted by the
 * platform API need no entry, which is why this starts empty.
 */
const HOSTS: ApprovalHost[] = [];

export function approvalClient(approvalType: string): ApiClient {
  const host = HOSTS.find((candidate) =>
    approvalType.startsWith(candidate.prefix),
  );
  return host ? host.client() : apiClient();
}
