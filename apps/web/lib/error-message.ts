import { ApiError } from "@dw/api-client";
import { SALES_REFUSALS } from "../app/sales/_meta/refusals";

/**
 * Vietnamese for a refusal the API names by a code in its details, where the
 * server's own sentence is still English, by the context that owns the codes.
 * A code belongs to one table only, and never to a refusal the platform
 * raises: the platform words its own sentences, and a code in two tables would
 * read whichever was merged last. `error-message.test.ts` holds both.
 */
export const REFUSAL_TABLES: Readonly<
  Record<string, Readonly<Record<string, string>>>
> = {
  // PLUG-IN POINT: a bounded context adds its table here, as Sales does.
  sales: SALES_REFUSALS,
};

const REFUSALS: Readonly<Record<string, string>> = Object.assign(
  {},
  ...Object.values(REFUSAL_TABLES),
);

/** The Vietnamese for a refusal's `details.rule`, else `details.reason`. */
function refusalSentence(details: Record<string, unknown> | undefined) {
  for (const key of ["rule", "reason"] as const) {
    const code = details?.[key];
    if (typeof code === "string" && Object.hasOwn(REFUSALS, code))
      return REFUSALS[code];
  }
  return null;
}

/**
 * The sentence to show a person when a call fails.
 *
 * `ApiError.message` is `"<code>: <sentence>"` because the code is what a
 * developer reading a stack trace needs. A seller reading a toast does not:
 * "validation_failed: hai đầu quan hệ chưa có trên bản đồ" leaks a machine
 * word into the product. A refusal whose code has Vietnamese here reads that;
 * any other reads the server's sentence, and the code stays in the console.
 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError)
    return refusalSentence(error.body.details) ?? error.body.message;
  if (error instanceof Error) return error.message;
  return String(error);
}

/** The server's machine code, when there is one — for branching, not display. */
export function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.body.code : null;
}

/**
 * A failure, as the shared `RegionState` reads it (`stateForError` in
 * `@dw/ui` owns which code draws which state): the server's code and sentence
 * (never `"<code>: …"`), or `"offline"` when the request never reached the
 * server (ui-quality §4) — the browser says it is offline, or `fetch`
 * rejected with its network TypeError ("Failed to fetch", Firefox's
 * "NetworkError…", Safari's "Load failed").
 */
export function toRegionError(
  error: unknown,
): { code: string; message: string; requestId?: string | null } | "offline" {
  if (error instanceof ApiError) {
    return {
      code: error.body.code,
      message: errorMessage(error),
      requestId: error.body.request_id ?? null,
    };
  }
  if (
    (typeof navigator !== "undefined" && navigator.onLine === false) ||
    (error instanceof TypeError &&
      /fetch|network|load failed/i.test(error.message))
  ) {
    return "offline";
  }
  return { code: "internal", message: errorMessage(error) };
}
