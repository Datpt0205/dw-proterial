/** The largest scanned document the API keeps (10 MiB, `SIGNED_MAX_BYTES`
 * and the export-control documents alike). */
export const SCAN_MAX_BYTES = 10 * 1024 * 1024;
/** What a scan or a photo of a signed paper may be. */
export const SCAN_ACCEPT = ".pdf,.jpg,.jpeg,.png";

/** The file's bytes as base64, the way the API takes an upload. */
export async function base64(file: File): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000)
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}
