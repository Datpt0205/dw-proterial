"use client";

import type { ReactNode } from "react";
import { Breadcrumb, Typography, type BreadcrumbProps } from "antd";

export interface PageHeaderProps {
  title: ReactNode;
  /** One sentence: what this page holds now, or the record's identity. */
  description?: ReactNode;
  /** Where the page sits: the context, the list, the record. */
  breadcrumb?: BreadcrumbProps["items"];
  /** A record's state and versions, on the line above its title. */
  meta?: ReactNode;
  /** Status tags beside the title. */
  tags?: ReactNode;
  /** The page's actions, at the end of the row (wraps below on a phone). */
  extra?: ReactNode;
}

/**
 * The header every page in the shell starts with (the prototype's list and
 * record headers): the breadcrumb, the record's state above the title, the
 * title, one line of summary, and the actions at the end of the row. The same
 * place for each on every screen (ui-quality "put the screen beside its
 * sibling"). Domain-neutral; a context passes its own words and tags.
 */
export function PageHeader({
  title,
  description,
  breadcrumb,
  meta,
  tags,
  extra,
}: PageHeaderProps) {
  return (
    <header className="mb-4 flex flex-col gap-1">
      {breadcrumb?.length ? <Breadcrumb items={breadcrumb} /> : null}
      {meta ? (
        <div className="flex flex-wrap items-center gap-2">{meta}</div>
      ) : null}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Typography.Title level={3} className="!mb-0">
              {title}
            </Typography.Title>
            {tags}
          </div>
          {description ? (
            <Typography.Paragraph type="secondary" className="!mb-0 !mt-1">
              {description}
            </Typography.Paragraph>
          ) : null}
        </div>
        {extra ? (
          <div className="flex flex-wrap items-center gap-2">{extra}</div>
        ) : null}
      </div>
    </header>
  );
}
