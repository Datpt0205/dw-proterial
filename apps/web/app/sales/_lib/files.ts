import { toBase64 } from "./catalog";

/** The largest scanned document the API keeps (10 MiB, `SIGNED_MAX_BYTES`
 * and the export-control documents alike). */
export const SCAN_MAX_BYTES = 10 * 1024 * 1024;
/** What a scan or a photo of a signed paper may be. */
export const SCAN_ACCEPT = ".pdf,.jpg,.jpeg,.png";

/** The file's bytes as base64, the way the API takes an upload. */
export async function base64(file: File): Promise<string> {
  return toBase64(new Uint8Array(await file.arrayBuffer()));
}
