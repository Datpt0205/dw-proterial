import type {
  InputHTMLAttributes,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";
import { cn } from "./cn";

export function Input({
  className,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "flex h-10 w-full rounded-lg border border-input bg-white px-3 py-2 text-sm shadow-sm transition-colors file:mr-3 file:rounded-md file:border-0 file:bg-muted file:px-2 file:py-1 file:text-sm file:font-semibold placeholder:text-muted-foreground focus-visible:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/10 disabled:cursor-not-allowed disabled:bg-muted/50 disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}

export function Textarea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "flex min-h-[80px] w-full rounded-lg border border-input bg-white px-3 py-2.5 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/10 disabled:cursor-not-allowed disabled:bg-muted/50 disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}

export function Select({
  className,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        // py-1 (not py-2) + leading-tight: a native <select> clips its text when
        // the content box is shorter than the line box, which is exactly what a
        // compact height override (h-8) + py-2 produced — the "half-cut" text.
        // py-1 leaves ~22px inside an h-8 control, enough for the 20px line.
        "flex h-10 w-full rounded-lg border border-input bg-white px-3 py-1 text-sm leading-tight shadow-sm transition-colors focus-visible:border-primary/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/10 disabled:cursor-not-allowed disabled:bg-muted/50 disabled:opacity-60",
        className,
      )}
      {...props}
    />
  );
}
