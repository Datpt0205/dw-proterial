"use client";

import type { ComponentProps, ReactNode } from "react";
import { CheckIcon, Loader2Icon, TerminalIcon, XIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import { field, inkButton, paper } from "../surfaces";

export type ApprovalState = "request" | "running" | "done" | "denied";

export function ApprovalCard({
  state,
  command,
  title,
  subtitle,
  onAllowOnce,
  onDeny,
  footer,
  className,
  ...props
}: Omit<
  ComponentProps<"div">,
  | "children"
  | "state"
  | "command"
  | "title"
  | "subtitle"
  | "onAllowOnce"
  | "onDeny"
  | "footer"
> & {
  state: ApprovalState;
  /**
   * Cái sắp được ghi.
   *
   * Bản registry nhận một chuỗi và vẽ nó bằng font mono - hợp với một lệnh
   * shell. Ở đây thứ cần duyệt là một bộ trường CRM có nhãn tiếng Việt, nên nó
   * nhận luôn ReactNode: người bấm Approve phải nhìn thấy tên sắp được ghi,
   * không phải một chuỗi đã bị ép phẳng.
   */
  command: ReactNode;
  title: string;
  subtitle: string;
  onAllowOnce?: () => void;
  onDeny?: () => void;
  /** Chỗ cho ô ghi chú, khi quyết định này bắt buộc phải kèm một câu. */
  footer?: ReactNode;
}) {
  return (
    <div
      data-slot="approval-card"
      className={cn(
        paper,
        "flex w-full max-w-sm flex-col gap-3.5 rounded-[20px] p-4",
        className,
      )}

      {...props}
    >
      <div className="flex items-center gap-3">
        <span className="bg-foreground/[0.05] text-foreground/45 flex size-9 shrink-0 items-center justify-center rounded-xl">
          <TerminalIcon className="size-4" />
        </span>
        <div className="flex flex-col">
          <p className="text-[13.5px] font-medium">{title}</p>
          <p className="text-foreground/45 text-xs">{subtitle}</p>
        </div>
      </div>

      <div
        className={cn(
          field,
          "text-foreground/70 rounded-xl px-3.5 py-2.5 text-xs",
        )}
      >
        {command}
      </div>

      {footer}

      <div className="flex h-8 items-center justify-end gap-2">
        {state === "request" ? (
          <>
            <button
              type="button"
              onClick={onDeny}
              className="text-foreground/55 hover:bg-foreground/[0.06] hover:text-foreground/90 h-8 rounded-full px-3.5 text-xs font-medium transition-[background-color,color,scale] duration-150 active:scale-[0.96]"
            >
              Từ chối
            </button>
            {/* "Always allow" của bản registry bị bỏ: ở đây không có khái
                niệm cho phép vĩnh viễn - mỗi lần ghi vào hồ sơ khách hàng là
                một quyết định riêng, và đó là điều kiện của bản ghi audit. */}
            <button
              type="button"
              onClick={onAllowOnce}
              className={cn(
                inkButton,
                "flex h-8 items-center rounded-full px-3.5 text-xs font-medium",
              )}
            >
              Duyệt
            </button>
          </>
        ) : (
          <div
            key={state}
            className="fade-in animate-in text-foreground/55 flex items-center gap-2 text-xs duration-300"
          >
            {state === "running" ? (
              <>
                <Loader2Icon className="text-foreground/45 size-3.5 animate-spin" />
                Đã duyệt, đang chạy
              </>
            ) : state === "denied" ? (
              <>
                <XIcon className="text-foreground/45 size-3.5" />
                Đã từ chối
              </>
            ) : (
              <>
                <CheckIcon className="size-3.5 text-emerald-500" />
                Đã xong
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
