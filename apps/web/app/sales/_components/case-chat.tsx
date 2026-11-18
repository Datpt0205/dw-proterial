"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Card, Drawer, FloatButton, Grid } from "antd";
import { CommentOutlined } from "@ant-design/icons";
import type { AssistantCase, SalesSchemas } from "@dw/api-client";
import { AssistantConversation } from "./assistant-conversation";

const TITLE = "Hỏi DW1 về hồ sơ này";

/** What a case's conversation answers, said before anyone asks. */
const CATALOG =
  "Trạng thái, các mốc ngày và cờ đang mở của hồ sơ này; nhờ soạn thư cho khách, nhắc khách hoặc tóm tắt chuỗi thư thì DW1 đưa nút của hồ sơ. Câu trả lời không có số tiền.";

const EXAMPLES = [
  "Hồ sơ này đang ở bước nào?",
  "Còn cờ nào đang mở?",
  "Tóm tắt chuỗi thư của hồ sơ này",
];

/** A step of a case the conversation offers a control for (ticket 46). */
export type CaseOffer = NonNullable<SalesSchemas["TurnView"]["offer"]>;
/** The case page's own controls, by the step each answers; a step the page
 * draws nothing for at this point of the case is left out. */
export type CaseOffers = Partial<Record<CaseOffer, ReactNode>>;

const OffersContext = createContext<((offers: CaseOffers) => void) | null>(
  null,
);

/**
 * Hands the case page's own controls to its conversation (ticket 46), so a
 * step asked in the chat is answered with the very control the page draws,
 * under the page's own conditions, gate and API: the chat never decides which
 * exist. Pass a memoised object (its identity is the dependency).
 */
export function useCaseChatOffers(offers: CaseOffers) {
  const set = useContext(OffersContext);
  useEffect(() => {
    set?.(offers);
  }, [set, offers]);
}

/**
 * A case page with its conversation (ticket 46): the case is the
 * conversation, so opening the case opens it, with nothing to create or pick.
 * From `lg` up it sits open beside the case; below, a button opens it as a
 * bottom sheet (ui-quality §9), mounted on first open and kept, so an answer
 * still arriving is not lost by closing it. The page's own content keeps its
 * place in the tree whichever way it is drawn, so a breakpoint never reloads
 * the case.
 */
export function WithCaseChat({
  onCase,
  children,
}: {
  onCase: AssistantCase;
  children: ReactNode;
}) {
  // Undefined until measured: neither is drawn, so a desktop never flashes
  // the phone's button and a phone never reads (and so clears) the chat.
  const lg = Grid.useBreakpoint().lg;
  const [open, setOpen] = useState(false);
  const [offers, setOffers] = useState<CaseOffers>({});
  const chat = (
    <AssistantConversation
      onCase={onCase}
      examples={EXAMPLES}
      catalog={CATALOG}
      offers={offers}
    />
  );
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <OffersContext.Provider value={setOffers}>
        <div className="min-w-0">{children}</div>
      </OffersContext.Provider>
      {lg === true ? (
        <aside aria-label={TITLE} className="self-start lg:sticky lg:top-4">
          <Card size="small" title={TITLE}>
            <div className="max-h-[calc(100vh-160px)] overflow-y-auto">
              {chat}
            </div>
          </Card>
        </aside>
      ) : lg === false ? (
        <>
          <FloatButton
            type="primary"
            icon={<CommentOutlined aria-hidden />}
            aria-label={TITLE}
            tooltip={TITLE}
            onClick={() => setOpen(true)}
            style={{ insetInlineEnd: 20, bottom: 20 }}
          />
          <Drawer
            open={open}
            onClose={() => setOpen(false)}
            placement="bottom"
            size="88vh"
            title={TITLE}
          >
            {chat}
          </Drawer>
        </>
      ) : null}
    </div>
  );
}
