import type { ReactNode } from "react";
import { AssistantWidget } from "./_components/assistant-widget";
import { SalesFrameProvider } from "./_components/sales-frame";

/** Every Sales page: DW1's state on top, then the page, with the "Hỏi DW1"
 * widget beside it. */
export default function SalesLayout({ children }: { children: ReactNode }) {
  return (
    <SalesFrameProvider>
      <AssistantWidget>{children}</AssistantWidget>
    </SalesFrameProvider>
  );
}
