import { readFile } from "node:fs/promises";
import { join } from "node:path";

/**
 * pdf.js's own data files, served from the installed `pdfjs-dist` so the
 * browser renders a PDF without reaching any other host: the Adobe CMaps a
 * CJK document's text needs (a Japanese quotation, say) and the standard
 * fonts a PDF may name without embedding. Only these two folders, only plain
 * file names; anything else is 404. The files are public library data, never
 * a tenant's.
 */
const FOLDERS = new Set(["cmaps", "standard_fonts"]);
const FILE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/;
// The web app's own `node_modules`: the app's directory in development, and
// where the standalone server keeps the traced files once built.
const ROOTS = [
  join(process.cwd(), "node_modules", "pdfjs-dist"),
  join(process.cwd(), "apps", "web", "node_modules", "pdfjs-dist"),
];

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ kind: string; file: string }> },
) {
  const { kind, file } = await params;
  if (!FOLDERS.has(kind) || !FILE.test(file) || file.includes(".."))
    return new Response("not found", { status: 404 });
  for (const root of ROOTS) {
    try {
      const bytes = await readFile(join(root, kind, file));
      return new Response(new Uint8Array(bytes), {
        headers: {
          "Content-Type": "application/octet-stream",
          "Cache-Control": "public, max-age=31536000, immutable",
        },
      });
    } catch {
      // Not under this root; try the next.
    }
  }
  return new Response("not found", { status: 404 });
}
