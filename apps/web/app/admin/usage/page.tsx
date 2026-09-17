"use client";

import { BarChart3 } from "lucide-react";
import { EmptyState } from "../../../components/empty-state";
import { UsageStatsPanel } from "../../../components/admin/usage-stats";
import { PageHeading } from "../../../components/page-heading";
import { useAuth } from "../../../lib/auth/auth-context";

/** F6 — which usecases are used, how often, and what they cost. */
export default function AdminUsagePage() {
  const { hasScope } = useAuth();
  if (!hasScope("platform.usage.read")) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No access"
        description="You need the usage-statistics permission to view this page."
      />
    );
  }
  return (
    <div className="space-y-4">
      <PageHeading
        icon={BarChart3}
        title="Thống kê AI theo usecase"
        description="Lượt dùng, tần suất và chi phí model của từng tính năng AI — đọc từ sổ usage của tenant này."
      />
      <UsageStatsPanel />
    </div>
  );
}
