import type { ReactNode } from "react";
import { SalesFrameProvider } from "./_components/sales-frame";

/** Every Sales page: DW1's state on top, then the page. */
export default function SalesLayout({ children }: { children: ReactNode }) {
  return <SalesFrameProvider>{children}</SalesFrameProvider>;
}
