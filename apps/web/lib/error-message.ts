import { ApiError } from "@dw/api-client";

/**
 * The sentence to show a person when a call fails.
 *
 * `ApiError.message` is `"<code>: <sentence>"` because the code is what a
 * developer reading a stack trace needs. A seller reading a toast does not:
 * "validation_failed: hai đầu quan hệ chưa có trên bản đồ" leaks a machine
 * word into the product. The server already writes the sentence in Vietnamese
 * — take that, and keep the code for the console.
 */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.body.message;
  if (error instanceof Error) return error.message;
  return String(error);
}

/** The server's machine code, when there is one — for branching, not display. */
export function errorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.body.code : null;
}
