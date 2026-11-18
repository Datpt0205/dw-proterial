"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { Tag, Typography } from "antd";
import type { AssistantCase, SalesSchemas } from "@dw/api-client";
import {
  AssistantChat,
  useOnline,
  OFFLINE_REASON,
  type ChatTurn,
} from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { liveAfter, NOTHING_YET } from "../../../lib/chat-live";
import { useIdempotencyKeys } from "../../../lib/idempotency";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { useResource } from "../_lib/use-resource";
import type { CaseOffers } from "./case-chat";

type Turn = SalesSchemas["TurnView"];
type CaseRef = SalesSchemas["CaseRefView"];

/** The longest question the API takes (`QUESTION_CHARS`). */
const QUESTION_MAX = 500;

export function caseHref(ref: {
  kind: CaseRef["kind"];
  case_id: string;
}): string {
  return ref.kind === "order"
    ? `/sales/orders/${ref.case_id}`
    : `/sales/quotes/${ref.case_id}`;
}

/** How DW1 read a question, in the words the page shows as its first step. */
const READ_AS: Record<Turn["kind"], string> = {
  order_status: "Hiểu là hỏi trạng thái một PO",
  quote_status: "Hiểu là hỏi trạng thái một yêu cầu báo giá",
  my_work: "Hiểu là hỏi việc đang chờ bạn",
  overdue: "Hiểu là hỏi việc quá hạn",
  draft_reply: "Hiểu là nhờ soạn thư cho khách",
  remind_customer: "Hiểu là nhờ nhắc khách",
  explain_thread: "Hiểu là nhờ tóm tắt chuỗi thư",
  out_of_scope: "Câu này ngoài những gì DW1 trả lời",
};

/** Said where the page has no control for the step at this point of the case. */
const NOT_HERE = "Ở bước hiện tại, trang hồ sơ không có nút cho việc này.";

/** What DW1 did, from what the server returned: never more than it says. */
function chatTurn(turn: Turn, offers: CaseOffers | undefined): ChatTurn {
  const steps = [{ key: "read", title: READ_AS[turn.kind] }];
  if (turn.kind !== "out_of_scope")
    steps.push({
      key: "look",
      title: turn.cites.length
        ? `Tra ${turn.cites.length} hồ sơ trong phạm vi bạn được xem`
        : "Tra trong phạm vi bạn được xem: không thấy hồ sơ khớp",
    });
  steps.push({
    key: "word",
    title:
      turn.answered_by === "model"
        ? "Máy viết câu trả lời từ dữ liệu đã tra, code kiểm không có số nào ngoài dữ liệu"
        : "DW1 trả lời bằng câu soạn sẵn từ dữ liệu",
  });
  return {
    key: String(turn.seq),
    question: turn.question,
    answer: turn.answer,
    byModel: turn.answered_by === "model",
    steps,
    // The case page's own control for a step asked of it (ticket 46).
    action: turn.offer
      ? (offers?.[turn.offer] ?? <Typography.Text>{NOT_HERE}</Typography.Text>)
      : undefined,
    cites: turn.cites.map((ref) => ({
      key: ref.case_id,
      label: (
        <Link href={caseHref(ref)}>
          <Tag>{ref.label}</Tag>
        </Link>
      ),
    })),
  };
}

/**
 * One of the person's own conversations with DW1 (dw_sales ADR 0007, ticket
 * 46): on a case (`onCase`), bound by the server to that case from the
 * route, or their one general conversation. There is no session to create
 * or pick: the server finds the conversation by the case, and an empty one
 * is simply one nobody has asked in yet. Reading a case's conversation
 * clears its unread mark; `onAnswered` lets a page refresh what shows it.
 */
export function AssistantConversation({
  onCase,
  examples,
  catalog,
  onAnswered,
  offers,
}: {
  onCase: AssistantCase | null;
  examples: string[];
  catalog?: string;
  onAnswered?: () => void;
  /** The case page's own controls (`useCaseChatOffers`). */
  offers?: CaseOffers;
}) {
  const online = useOnline();
  const keys = useIdempotencyKeys();
  const key = onCase ? `${onCase.kind}-${onCase.caseId}` : "general";
  const loaded = useResource(`assistant-conversation-${key}`, () =>
    salesApi().assistantConversation(onCase),
  );
  const [asked, setAsked] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(NOTHING_YET);
  const [error, setError] = useState<unknown>(null);
  const stopper = useRef<AbortController | null>(null);
  const turns = [...(loaded.data?.turns ?? []), ...asked];

  const ask = async (text: string) => {
    const payload = { question: text, key };
    const stop = new AbortController();
    stopper.current = stop;
    setBusy(true);
    setLive(NOTHING_YET);
    setError(null);
    try {
      const answer = await salesApi().assistantStream(
        text,
        onCase,
        keys.keyFor("assistant-ask", payload),
        (event) => setLive((now) => liveAfter(now, event)),
        stop.signal,
      );
      keys.settle("assistant-ask");
      setAsked((earlier) => [...earlier, answer.turn]);
      setQuestion("");
      onAnswered?.();
    } catch (e) {
      // A person who pressed stop was told nothing went wrong, and asking the
      // same thing again is a new question.
      if (stop.signal.aborted) keys.settle("assistant-ask");
      else setError(e);
    } finally {
      setBusy(false);
    }
  };

  if (loaded.error)
    return <LoadError error={loaded.error} onRetry={loaded.reload} compact />;
  return (
    <AssistantChat
      worker="DW1"
      catalog={catalog}
      examples={examples}
      turns={turns.map((turn) => chatTurn(turn, offers))}
      loading={loaded.loading}
      pending={busy}
      live={live}
      onStop={() => stopper.current?.abort()}
      question={question}
      onQuestion={setQuestion}
      onAsk={(text) => void ask(text)}
      maxLength={QUESTION_MAX}
      blocked={online ? null : OFFLINE_REASON}
      error={error ? <ActionError error={error} /> : null}
    />
  );
}
