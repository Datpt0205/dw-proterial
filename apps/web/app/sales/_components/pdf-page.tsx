"use client";

import { useEffect, useRef, useState } from "react";
import { Alert, Skeleton, theme } from "antd";
import type { SalesSchemas } from "@dw/api-client";

type PageBox = SalesSchemas["PageBox"];

export interface DrawnBox {
  key: string;
  box: PageBox;
  /** The value the person is looking at: drawn stronger than the rest. */
  focused: boolean;
  label: string;
}

/**
 * One page of the original PDF, rendered in the browser, with the boxes the
 * reader stamped drawn on the rendered page itself (spec decision 12, ADR
 * 0009) — never on extracted text.
 *
 * The bytes come from the API's source route, never from a link. pdf.js runs
 * with no scripting: the core library never executes a PDF's JavaScript (that
 * needs the viewer's `pdf.sandbox`, which is not loaded), XFA forms are off,
 * and annotations and form widgets are not rendered. pdf.js 6 has no
 * `isEvalSupported` option any more: measured 2026-10-05, its builds contain
 * no `eval(` and no `new Function`, so there is nothing to switch off.
 */
export function PdfPage({
  data,
  page,
  boxes,
}: {
  /** The whole file, base64, as the source route serves it. */
  data: string;
  page: number;
  boxes: DrawnBox[];
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [error, setError] = useState<string | null>(null);
  const { token } = theme.useToken();

  useEffect(() => {
    let cancelled = false;
    let destroy: (() => void) | undefined;
    setState("loading");
    (async () => {
      const pdfjs = await import("pdfjs-dist");
      pdfjs.GlobalWorkerOptions.workerSrc = new URL(
        "pdfjs-dist/build/pdf.worker.min.mjs",
        import.meta.url,
      ).toString();
      const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
      const task = pdfjs.getDocument({
        data: bytes,
        enableXfa: false,
        stopAtErrors: true,
        // pdf.js's CMaps and standard fonts, from this app (app/pdfjs): a
        // Japanese quotation's text needs the CMaps to be drawn at all.
        cMapUrl: "/pdfjs/cmaps/",
        cMapPacked: true,
        standardFontDataUrl: "/pdfjs/standard_fonts/",
      });
      destroy = () => void task.destroy();
      const doc = await task.promise;
      const pdfPage = await doc.getPage(page);
      const canvas = canvasRef.current;
      if (cancelled || !canvas) return;
      const base = pdfPage.getViewport({ scale: 1 });
      const width = canvas.parentElement?.clientWidth || base.width;
      const ratio = window.devicePixelRatio || 1;
      const viewport = pdfPage.getViewport({
        scale: (width / base.width) * ratio,
      });
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.style.width = "100%";
      canvas.style.height = "auto";
      await pdfPage.render({
        canvas,
        viewport,
        annotationMode: pdfjs.AnnotationMode.DISABLE,
      }).promise;
      if (!cancelled) setState("ready");
    })().catch((failure: unknown) => {
      if (cancelled) return;
      setError(failure instanceof Error ? failure.message : String(failure));
      setState("error");
    });
    return () => {
      cancelled = true;
      destroy?.();
    };
  }, [data, page]);

  if (state === "error")
    return (
      <Alert
        type="error"
        showIcon
        title="Không hiển thị được trang này"
        description={`Trình duyệt không vẽ được trang ${page} của bản gốc (${error}). Bản gốc trên máy chủ không đổi.`}
      />
    );

  return (
    <div className="relative w-full" aria-label={`Trang ${page} của bản gốc`}>
      {state === "loading" ? (
        <Skeleton.Node active className="!h-96 !w-full" />
      ) : null}
      <canvas
        ref={canvasRef}
        className="block w-full"
        style={{ border: `1px solid ${token.colorBorderSecondary}` }}
        aria-hidden
      />
      {state === "ready"
        ? boxes.map(({ key, box, focused, label }) => (
            <span
              key={key}
              title={label}
              className="pointer-events-none absolute"
              style={{
                left: `${box.x * 100}%`,
                top: `${box.y * 100}%`,
                width: `${box.w * 100}%`,
                height: `${box.h * 100}%`,
                outline: `${focused ? 3 : 1}px solid ${focused ? token.colorWarning : token.colorPrimary}`,
                outlineOffset: 1,
                background: focused ? token.colorWarningBg : "transparent",
                mixBlendMode: "multiply",
              }}
            />
          ))
        : null}
    </div>
  );
}
