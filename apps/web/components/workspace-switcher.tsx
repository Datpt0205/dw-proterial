"use client";

import { useEffect, useRef, useState } from "react";
import { Building2, Check, ChevronsUpDown, Layers } from "lucide-react";
import { cn } from "@dw/ui";
import { useAuth } from "../lib/auth/auth-context";

/**
 * The active company + workspace, in the top navbar. When the signed-in user
 * belongs to more than one workspace it becomes a picker to switch between them
 * (auth context re-activates the chosen membership). A single membership just
 * shows, no dropdown. Nothing renders for an operator with no workspace.
 */
export function WorkspaceSwitcher() {
  const { active, memberships, selectWorkspace } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  if (!active) return null;
  const multiple = memberships.length > 1;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={!multiple}
        onClick={() => setOpen((v) => !v)}
        title={`${active.tenantName} · ${active.workspaceName}`}
        className={cn(
          "flex max-w-[15rem] items-center gap-2 rounded-lg border bg-white px-2.5 py-1.5 text-left",
          multiple && "hover:bg-muted",
        )}
      >
        <Building2 className="size-4 shrink-0 text-slate-400" />
        <span className="min-w-0 leading-tight">
          <span className="block truncate text-xs font-semibold text-slate-700">
            {active.tenantName}
          </span>
          <span className="block truncate text-[11px] text-slate-500">
            {active.workspaceName}
          </span>
        </span>
        {multiple && (
          <ChevronsUpDown className="size-3.5 shrink-0 text-slate-400" />
        )}
      </button>
      {open && multiple && (
        <ul className="absolute left-0 z-50 mt-1 max-h-72 w-64 overflow-auto rounded-md border bg-card shadow-lg">
          {memberships.map((m) => (
            <li key={m.workspaceId}>
              <button
                type="button"
                onClick={() => {
                  selectWorkspace(m.workspaceId);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted"
              >
                <Layers className="size-3.5 shrink-0 text-slate-400" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">
                    {m.tenantName}
                  </span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {m.workspaceName}
                  </span>
                </span>
                {m.workspaceId === active.workspaceId && (
                  <Check className="size-4 shrink-0 text-primary" />
                )}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
