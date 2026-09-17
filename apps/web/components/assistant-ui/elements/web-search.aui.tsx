"use client";

import type { ComponentProps } from "react";
import { SearchIcon } from "lucide-react";
import { SourceIcon } from "@/components/source-icon";
import { cn } from "@/lib/cn";
import { field, mono, ShimmerLabel } from "../surfaces";
import { take } from "@/lib/range";

export interface WebSearchResult {
  title: string;
  domain: string;
  /**
   * Địa chỉ trang, khi biết.
   *
   * Bản registry chỉ có `title` + `domain` và vẽ mỗi dòng bằng một `div` -
   * đọc được nhưng bấm không được. Dòng tra web tự viết trước đó thì mở được
   * trang, và mất đi là mất thật: người đọc một câu trả lời có dẫn nguồn cần
   * đường đi tới nguồn, không chỉ tên nó.
   */
  url?: string;
}

export function WebSearch({
  query,
  results,
  visibleResults,
  searching,
  cycle,
  className,
  ...props
}: Omit<
  ComponentProps<"div">,
  "children" | "query" | "results" | "visibleResults" | "searching" | "cycle"
> & {
  query: string;
  results: readonly WebSearchResult[];
  visibleResults: number;
  searching: boolean;
  cycle: number;
}) {
  return (
    <div
      data-slot="web-search"
      className={cn("flex w-full max-w-sm flex-col gap-2.5", className)}

      {...props}
    >
      <span
        className={cn(
          field,
          "text-foreground/70 inline-flex w-fit items-center gap-1.5 rounded-full px-3.5 py-2 text-xs",
        )}
      >
        <SearchIcon className="text-foreground/40 size-3" />
        {query}
      </span>
      <div className="text-foreground/45 text-xs">
        {searching ? (
          <ShimmerLabel className="relative inline-block leading-none">
            Searching
          </ShimmerLabel>
        ) : (
          <span className="fade-in animate-in duration-300">
            {/* Số thật, không phải "3" cứng như bản registry chép về; và bằng
                tiếng của sản phẩm, vì mọi dòng khác trong khung chat đều thế. */}
            {results.length > 0
              ? `Đã đọc ${results.length} nguồn`
              : "Không có kết quả nào"}
          </span>
        )}
      </div>
      <div className="flex min-h-[5.75rem] flex-col">
        {take(results, visibleResults).map((result, index) => {
          const row = (
            <>
              {/* Favicon thật khi có địa chỉ; chữ cái đầu tên miền là bản dự
                  phòng của registry, dùng khi tra cứu không trả về url. */}
              {result.url ? (
                <SourceIcon url={result.url} />
              ) : (
                <span className="bg-foreground/[0.06] text-foreground/45 flex size-4 shrink-0 items-center justify-center rounded text-[9px] font-medium">
                  {result.domain.charAt(0).toUpperCase()}
                </span>
              )}
              <span className="text-foreground/90 min-w-0 flex-1 truncate text-[13.5px]">
                {result.title}
              </span>
              <span className={cn(mono, "text-foreground/35 shrink-0")}>
                {result.domain}
              </span>
            </>
          );
          const shell =
            "fade-in slide-in-from-bottom-1 animate-in fill-mode-both hover:bg-foreground/[0.03] -mx-2.5 flex items-center gap-2.5 rounded-xl px-2.5 py-1.5 transition-colors duration-300";
          // Khoá theo cả chỉ số: hai kết quả cùng một tên miền trong một lượt
          // tìm là chuyện thường, và khoá trùng thì React bỏ mất một dòng.
          const key = `${cycle}-${index}-${result.domain}`;

          return result.url ? (
            <a
              key={key}
              href={result.url}
              target="_blank"
              rel="noopener noreferrer"
              title={result.title}
              className={cn(shell, "cursor-pointer")}
            >
              {row}
            </a>
          ) : (
            <div key={key} className={shell}>
              {row}
            </div>
          );
        })}
      </div>
    </div>
  );
}
