"use client";

import type { ReactNode } from "react";
import { Typography } from "antd";

export interface PageHeaderProps {
  title: ReactNode;
  /** One sentence: what this page is for, or the record's identity. */
  description?: ReactNode;
  /** Status tags beside the title. */
  tags?: ReactNode;
  /** The page's actions, at the end of the row (wraps below on a phone). */
  extra?: ReactNode;
}

/**
 * The header every page in the shell starts with: the same place for the
 * title, the status and the actions on every screen (ui-quality "put the
 * screen beside its sibling"). Domain-neutral; a context passes its own
 * words and tags.
 */
export function PageHeader({
  title,
  description,
  tags,
  extra,
}: PageHeaderProps) {
  return (
    <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Typography.Title level={3} className="!mb-0">
            {title}
          </Typography.Title>
          {tags}
        </div>
        {description ? (
          <Typography.Paragraph className="!mb-0 !mt-1">
            {description}
          </Typography.Paragraph>
        ) : null}
      </div>
      {extra ? (
        <div className="flex flex-wrap items-center gap-2">{extra}</div>
      ) : null}
    </header>
  );
}
