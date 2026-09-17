import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { cn } from "@dw/ui";

interface PageHeadingProps {
  eyebrow?: string;
  /** Usually the record name; a node when the title carries an inline control
   * (e.g. the pin button on an opportunity). */
  title: ReactNode;
  description?: ReactNode;
  icon?: LucideIcon;
  actions?: ReactNode;
  className?: string;
}

export function PageHeading({
  eyebrow,
  title,
  description,
  icon: Icon,
  actions,
  className,
}: PageHeadingProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 md:flex-row md:items-end md:justify-between",
        className,
      )}
    >
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-primary/70">
            {Icon && <Icon className="size-4" />}
            {eyebrow}
          </div>
        )}
        <h1 className="text-[1.65rem] font-semibold leading-tight tracking-[-0.035em] text-foreground sm:text-3xl">
          {title}
        </h1>
        {description && (
          <div className="mt-1.5 max-w-3xl text-sm leading-6 text-muted-foreground">
            {description}
          </div>
        )}
      </div>
      {actions && (
        <div className="flex w-full shrink-0 flex-wrap items-center gap-2 [&>button]:max-sm:flex-1 md:w-auto">
          {actions}
        </div>
      )}
    </div>
  );
}
