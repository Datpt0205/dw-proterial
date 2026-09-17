"use client";

import Link from "next/link";
import { LayoutDashboard } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@dw/ui";
import { EmptyState } from "../components/empty-state";
import { PageHeading } from "../components/page-heading";
import { useAuth } from "../lib/auth/auth-context";
import { NAV_ITEMS } from "../lib/nav/registry";
import { hasAnyRole } from "../lib/nav/roles";

/**
 * The platform landing page.
 *
 * A bounded context owns its own home screen; this one only points at the
 * platform areas the signed-in person can actually reach, read from the same
 * nav registry the sidebar renders — so a page added to the registry appears
 * here too, and nothing here can offer a link the sidebar would hide.
 */
export default function HomePage() {
  const { displayName, active, isPlatformOperator, hasScope, roles } =
    useAuth();

  const destinations = NAV_ITEMS.filter(
    (item) =>
      item.href !== "/" &&
      (!item.operatorOnly || isPlatformOperator) &&
      (!item.scope || hasScope(item.scope)) &&
      (!item.roles || hasAnyRole(roles, item.roles)),
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeading
        icon={LayoutDashboard}
        title={displayName ? `Welcome, ${displayName}` : "Welcome"}
        description={
          active
            ? `You are working in ${active.workspaceName}. Every run, decision and side effect below is scoped to it.`
            : "Pick a workspace to start working."
        }
      />
      {destinations.length === 0 && (
        <EmptyState
          icon={LayoutDashboard}
          title="Nothing to show yet"
          description="Your roles carry no scope for any area of this workspace. Ask an administrator for access."
        />
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {destinations.map((item) => {
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href} className="group">
              <Card className="h-full transition-colors group-hover:border-primary">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-muted text-muted-foreground transition-colors group-hover:bg-primary/10 group-hover:text-primary">
                      <Icon className="size-4" />
                    </span>
                    {item.label}
                  </CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">
                  {item.hint}
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
