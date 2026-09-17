"use client";

import { useCallback } from "react";
import { BrainCircuit } from "lucide-react";
import { Badge, Card, Skeleton } from "@dw/ui";
import { EmptyState } from "../../components/empty-state";
import { LoadMore } from "../../components/load-more";
import { PageHeading } from "../../components/page-heading";
import { apiClient } from "../../lib/session";
import { useCachedPages } from "../../lib/use-cached-pages";

const TYPE_LABELS: Record<string, string> = {
  episodic: "Episode",
  semantic: "Knowledge",
  procedural: "Procedure",
  preference: "Preference",
  commitment: "Commitment",
};

export default function MemoryPage() {
  const { items, loading, loadingMore, error, hasMore, loadMore } =
    useCachedPages(
      "memory:items",
      useCallback(
        (cursor: string | null) => apiClient().listMemoryItems({ cursor }),
        [],
      ),
    );

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeading
        icon={BrainCircuit}
        title="Long-term memory"
        description="Only information with clear evidence that meets policy is stored long-term."
      />
      {error != null && (
        <p className="text-sm text-red-600">
          {error instanceof Error ? error.message : "unknown error"}
        </p>
      )}
      {loading && error == null && <Skeleton className="h-56 rounded-2xl" />}
      {!loading && items.length === 0 && (
        <EmptyState
          icon={BrainCircuit}
          title="No long-term memories yet"
          description="Evidence-backed items appear once the system completes a qualifying run."
        />
      )}
      <div className="space-y-2">
        {items.map((item) => (
          <Card key={item.memory_id} className="p-4 text-sm">
            <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:justify-between">
              <Badge variant="secondary">
                {TYPE_LABELS[item.memory_type] ?? item.memory_type}
              </Badge>
              <span className="text-xs text-slate-500">
                confidence {(item.confidence * 100).toFixed(0)}% ·{" "}
                {item.provenance_count} sources
              </span>
            </div>
            <p className="mt-2">{item.content}</p>
            <p className="mt-1 text-xs text-slate-400">
              Run id: {item.created_by_run_id}
            </p>
          </Card>
        ))}
      </div>

      {!loading && items.length > 0 && (
        <LoadMore
          hasMore={hasMore}
          loading={loadingMore}
          onLoadMore={loadMore}
          shown={items.length}
          noun="memories"
        />
      )}
    </div>
  );
}
