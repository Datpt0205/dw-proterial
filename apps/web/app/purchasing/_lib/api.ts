"use client";

import { PurchasingApi } from "@dw/api-client";
import { apiClient } from "../../../lib/session";

/**
 * The Purchasing routes, on the session's client: the bearer token, the
 * active workspace headers and the 401 handling come from `lib/session.ts`.
 */
export function purchasingApi(): PurchasingApi {
  return new PurchasingApi(apiClient());
}
