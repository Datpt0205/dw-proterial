"use client";

import type { ReactNode } from "react";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import { UiProvider } from "@dw/ui";
// dayjs's locale and time-zone plugins are set up in one place, and antd's
// date pickers read dayjs's global locale: loaded here, before any renders.
import "../lib/dates";

/**
 * Where antd's styles enter the page, and the cascade layer they enter in.
 *
 * `layer` wraps every antd rule in `@layer antd`, which `globals.css` orders
 * between Tailwind's `base` and `utilities`: antd's components beat the
 * preflight reset, and a Tailwind class on an antd component beats antd. Get
 * either half wrong and nothing errors, the classes are just ignored, so
 * `__tests__/layer-order.test.tsx` renders this component and checks both.
 */
export function UiRoot({ children }: { children: ReactNode }) {
  return (
    <AntdRegistry layer>
      <UiProvider>{children}</UiProvider>
    </AntdRegistry>
  );
}
