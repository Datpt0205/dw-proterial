"use client";

import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { usePathname } from "next/navigation";
import { toast } from "sonner";
import { ImagePlus, Loader2, Send, X } from "lucide-react";
import { Button, Select, Textarea } from "@dw/ui";
import { ApiError } from "@dw/api-client";
import { apiClient } from "../../lib/session";
import { NAV_ITEMS } from "../../lib/nav/registry";
import { Modal } from "../modal";

/**
 * The feedback form (spec 003 US5): exactly four things — which module, what
 * went wrong, what the person would do about it, and screenshots. Screenshots
 * arrive by paste, drag-drop or the file picker; the two questions the
 * reference form asked afterwards ("share samples?", "may we contact you?")
 * are deliberately not here.
 *
 * The limits mirror the server's (five images, 10 MB each, images only) so a
 * refusal is immediate and names the limit; the server checks again.
 */

// Same numbers as dw_platform.application.feedback_dto — one bug rarely needs
// more than a handful of screens, and a 4K PNG is well under 10 MB.
const MAX_IMAGES = 5;
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const IMAGE_MIMES = new Set([
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
]);
const OTHER_MODULE = "Khác";
const TEXT_MAX = 4000;

interface Picked {
  file: File;
  url: string;
}

/** The module whose page the person is on: the longest nav href that prefixes the path. */
function moduleForPath(pathname: string): string {
  let best: { label: string; length: number } | null = null;
  for (const item of NAV_ITEMS) {
    const matches =
      pathname === item.href || pathname.startsWith(item.href + "/");
    if (matches && (!best || item.href.length > best.length)) {
      best = { label: item.label, length: item.href.length };
    }
  }
  return best?.label ?? OTHER_MODULE;
}

function accept(
  files: FileList | File[],
  current: Picked[],
): Picked[] | string {
  const next = [...current];
  for (const file of Array.from(files)) {
    if (!IMAGE_MIMES.has(file.type)) {
      return `"${file.name}" không phải ảnh — chỉ nhận PNG, JPEG, GIF, WebP.`;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      return `"${file.name}" quá ${MAX_IMAGE_BYTES / (1024 * 1024)} MB.`;
    }
    if (next.length >= MAX_IMAGES) {
      return `Tối đa ${MAX_IMAGES} ảnh cho một phản hồi.`;
    }
    next.push({ file, url: URL.createObjectURL(file) });
  }
  return next;
}

export function FeedbackDialog({ onClose }: { onClose: () => void }) {
  const pathname = usePathname();
  const modules = useMemo(
    () => [...new Set(NAV_ITEMS.map((item) => item.label)), OTHER_MODULE],
    [],
  );
  const [module, setModule] = useState(() => moduleForPath(pathname));
  const [message, setMessage] = useState("");
  const [suggestion, setSuggestion] = useState("");
  const [images, setImages] = useState<Picked[]>([]);
  const [imageError, setImageError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  // Object URLs are revoked when the dialog goes, not per removal: a removed
  // preview may still be painting when its slot is re-rendered.
  useEffect(
    () => () => images.forEach((image) => URL.revokeObjectURL(image.url)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  function add(files: FileList | File[]) {
    const result = accept(files, images);
    if (typeof result === "string") {
      setImageError(result);
      return;
    }
    setImageError(null);
    setImages(result);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    add(event.dataTransfer.files);
  }

  async function submit() {
    const text = message.trim();
    if (!text) return;
    setSending(true);
    try {
      await apiClient().submitFeedback({
        module,
        message: text,
        suggestion: suggestion.trim() || undefined,
        page_path: pathname,
        images: images.map((image) => image.file),
      });
      toast.success("Cảm ơn — phản hồi đã tới quản trị viên.");
      onClose();
    } catch (error) {
      toast.error(
        error instanceof ApiError ? error.message : "Không gửi được phản hồi.",
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title="Gửi phản hồi"
      subtitle="Bạn gặp lỗi ở đâu, lỗi gì, và bạn muốn nó ra sao — kèm ảnh màn hình nếu có."
      className="max-w-xl"
    >
      <div
        className="space-y-4"
        onPaste={(event) => {
          const files = Array.from(event.clipboardData.files);
          if (files.length > 0) {
            event.preventDefault();
            add(files);
          }
        }}
      >
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">
            Module đang gặp lỗi <span className="text-rose-500">*</span>
          </span>
          <Select
            value={module}
            onChange={(event) => setModule(event.target.value)}
          >
            {modules.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">
            Mô tả lỗi <span className="text-rose-500">*</span>
          </span>
          <Textarea
            rows={4}
            maxLength={TEXT_MAX}
            value={message}
            onChange={(event) => setMessage(event.target.value)}
            placeholder="Bạn làm gì, chuyện gì xảy ra, bạn mong đợi gì?"
          />
        </label>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-muted-foreground">
            Đề xuất giải pháp / Khuyến nghị
          </span>
          <Textarea
            rows={2}
            maxLength={TEXT_MAX}
            value={suggestion}
            onChange={(event) => setSuggestion(event.target.value)}
            placeholder="Không bắt buộc"
          />
        </label>

        <div>
          <span className="mb-1 block text-xs font-medium text-muted-foreground">
            Ảnh đính kèm
          </span>
          <div
            role="group"
            aria-label="Ảnh đính kèm"
            onDragOver={(event) => event.preventDefault()}
            onDrop={onDrop}
            className="rounded-xl border border-dashed bg-muted/20 p-3"
          >
            {images.length > 0 && (
              <ul className="mb-3 flex flex-wrap gap-2">
                {images.map((image, index) => (
                  <li key={image.url} className="relative">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={image.url}
                      alt={image.file.name}
                      className="size-20 rounded-lg border object-cover"
                    />
                    <button
                      type="button"
                      aria-label={`Xoá ${image.file.name}`}
                      onClick={() =>
                        setImages((previous) =>
                          previous.filter((_, at) => at !== index),
                        )
                      }
                      className="absolute -right-1.5 -top-1.5 rounded-full border bg-background p-0.5 text-muted-foreground shadow hover:text-foreground"
                    >
                      <X className="size-3" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => fileInput.current?.click()}
              >
                <ImagePlus className="size-4" /> Chọn ảnh
              </Button>
              <span>hoặc kéo-thả / dán ảnh (Ctrl+V) vào đây.</span>
            </div>
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(event) => {
                if (event.target.files) add(event.target.files);
                event.target.value = "";
              }}
            />
          </div>
          {imageError && (
            <span className="mt-1 block text-xs text-rose-600">
              {imageError}
            </span>
          )}
        </div>

        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={sending}>
            Huỷ
          </Button>
          <Button
            onClick={() => void submit()}
            disabled={sending || !message.trim()}
          >
            {sending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
            Gửi
          </Button>
        </div>
      </div>
    </Modal>
  );
}
