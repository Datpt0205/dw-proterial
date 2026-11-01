"use client";

import type { ReactNode } from "react";
import { Divider, Skeleton, Typography } from "antd";

/**
 * A plain list of rows, each separated by a divider: what the DW2 pages
 * use where antd's `List` would (deprecated in antd 6.6). Loading draws a
 * skeleton, an empty list says what it is empty of.
 */
export function Rows<T>({
  items,
  loading,
  empty,
  rowKey,
  render,
}: {
  items: T[];
  loading?: boolean;
  empty: string;
  rowKey: (item: T) => string;
  render: (item: T) => ReactNode;
}) {
  if (loading) return <Skeleton active paragraph={{ rows: 2 }} />;
  if (!items.length) return <Typography.Text>{empty}</Typography.Text>;
  return (
    <ul className="m-0 list-none p-0">
      {items.map((item, index) => (
        <li key={rowKey(item)}>
          {index ? <Divider className="my-2" /> : null}
          {render(item)}
        </li>
      ))}
    </ul>
  );
}
