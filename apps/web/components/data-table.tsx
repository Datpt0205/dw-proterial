"use client";

import type { ReactNode } from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { Skeleton, cn } from "@dw/ui";

/**
 * The one table every list screen renders through, built on TanStack Table.
 *
 * A page describes its columns (id, header, width, how a cell reads) and hands
 * over its rows; this owns the shell — a fixed layout so column widths come from
 * the column and not the longest cell, a horizontal scroll so wide tables never
 * push the page sideways, ellipsis + tooltip on the columns that opt in, and the
 * loading and empty states. Sorting, filtering and paging stay on the server and
 * are driven by the page (their controls ride in the column `header`), so this
 * runs TanStack in manual mode and only draws what the server already decided.
 */
export interface DataColumn<T> {
  /** Stable id, also the React key for the column. */
  id: string;
  /** Header content — plain text, or a node carrying a sort/filter control. */
  header: ReactNode;
  /** CSS width for the column's `<col>` (e.g. "16%", "10rem"). */
  width?: string;
  align?: "left" | "right" | "center";
  /** Clip to one line with an ellipsis (and a tooltip via `title`) rather than
   *  letting the cell wrap or overflow into its neighbour. */
  truncate?: boolean;
  /** The cell renders its own multi-line content (e.g. a name over a subtitle):
   *  the column only clips overflow, it does not force one line. */
  block?: boolean;
  cell: (row: T) => ReactNode;
  /** Tooltip text for a truncated cell; defaults to no title. */
  title?: (row: T) => string;
}

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  loading = false,
  onRowClick,
  onRowHover,
  minWidth = "56rem",
  minRows,
  maxHeight,
  empty,
}: {
  columns: DataColumn<T>[];
  rows: T[];
  getRowId: (row: T) => string;
  loading?: boolean;
  onRowClick?: (row: T) => void;
  onRowHover?: (row: T) => void;
  /** Minimum table width before the wrapper scrolls sideways. */
  minWidth?: string;
  /** Pad to this many rows (empty ones) so the table is the same height on
   *  every page — the footer doesn't jump when a page holds fewer rows. */
  minRows?: number;
  /** Cap the body height and scroll the rows inside it (the header is sticky),
   *  so a larger page size does not push the pager down the screen. */
  maxHeight?: string;
  /** Shown when there are no rows and nothing is loading. */
  empty?: ReactNode;
}) {
  const defs: ColumnDef<T>[] = columns.map((column) => ({
    id: column.id,
    header: () => column.header,
    cell: ({ row }) => column.cell(row.original),
    meta: column,
  }));
  const table = useReactTable({
    data: rows,
    columns: defs,
    getCoreRowModel: getCoreRowModel(),
    getRowId,
  });

  const alignClass = (align?: DataColumn<T>["align"]) =>
    align === "right" ? "text-right" : align === "center" ? "text-center" : "";

  return (
    <div
      className={cn(
        "rounded-2xl border bg-card shadow-sm",
        maxHeight ? "overflow-auto" : "overflow-x-auto",
      )}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <table className="w-full table-fixed text-[13px]" style={{ minWidth }}>
        <colgroup>
          {columns.map((column) => (
            <col key={column.id} style={{ width: column.width }} />
          ))}
        </colgroup>
        <thead>
          {table.getHeaderGroups().map((group) => (
            <tr key={group.id} className="text-left">
              {group.headers.map((header) => {
                const meta = header.column.columnDef.meta as DataColumn<T>;
                return (
                  <th
                    key={header.id}
                    className={cn(
                      // Sticky so the header stays put once a list is long
                      // enough to scroll; an opaque ground so rows don't show
                      // through it.
                      "sticky top-0 z-10 border-b bg-muted px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground",
                      alignClass(meta.align),
                    )}
                  >
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext(),
                    )}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: minRows ?? 5 }).map((_, index) => (
              <tr key={index}>
                <td colSpan={columns.length} className="h-9 px-3 align-middle">
                  <Skeleton className="h-5 w-full" />
                </td>
              </tr>
            ))}
          {!loading &&
            table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={cn(
                  // Zebra striping instead of a rule on every row — the eye
                  // tracks a wide row across the stripe, and the table reads
                  // less busy than one divider per line.
                  "transition-colors",
                  row.index % 2 === 1 ? "bg-muted/30" : "bg-transparent",
                  "hover:bg-primary/5",
                  onRowClick && "cursor-pointer",
                )}
                onMouseEnter={
                  onRowHover ? () => onRowHover(row.original) : undefined
                }
                onClick={
                  onRowClick ? () => onRowClick(row.original) : undefined
                }
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta as DataColumn<T>;
                  return (
                    <td
                      key={cell.id}
                      className={cn(
                        // One compact fixed row height for every table and every
                        // cell, whatever it holds — plain text, an avatar badge,
                        // a quick-edit button. Row height tracked the tallest
                        // cell otherwise, so a page with badges (Lead/Account)
                        // sat taller than one without and needed scrolling that
                        // Opp did not; pinning it tight is the single knob that
                        // fits every list on one page.
                        "h-9 px-3 align-middle",
                        meta.truncate
                          ? "truncate"
                          : meta.block
                            ? "overflow-hidden"
                            : "overflow-hidden whitespace-nowrap",
                        alignClass(meta.align),
                      )}
                      title={meta.title ? meta.title(row.original) : undefined}
                    >
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          {!loading &&
            minRows !== undefined &&
            rows.length > 0 &&
            rows.length < minRows &&
            Array.from({ length: minRows - rows.length }).map((_, index) => (
              <tr key={`pad-${index}`} aria-hidden>
                <td colSpan={columns.length} className="h-9 px-3 align-middle">
                  &nbsp;
                </td>
              </tr>
            ))}
        </tbody>
      </table>
      {!loading && rows.length === 0 && empty}
    </div>
  );
}
