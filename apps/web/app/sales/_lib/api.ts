"use client";

import { SalesApi } from "@dw/api-client";
import { apiClient } from "../../../lib/session";

/**
 * The Sales routes, on the session's client: the bearer token, the active
 * workspace headers and the 401 handling come from `lib/session.ts`.
 */
export function salesApi(): SalesApi {
  return new SalesApi(apiClient());
}
