"use client";

import { Suspense, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  Button,
  Card,
  Empty,
  Flex,
  List,
  Skeleton,
  Tag,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import {
  AssistantChat,
  PageHeader,
  useOnline,
  OFFLINE_REASON,
  type ChatTurn,
} from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { liveAfter, NOTHING_YET } from "../../../lib/chat-live";
import { formatDateTime } from "../../../lib/dates";
import { useIdempotencyKeys } from "../../../lib/idempotency";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { useResource } from "../_lib/use-resource";
import { salesCrumbs } from "../_components/crumbs";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";

type Turn = SalesSchemas["TurnView"];
type CaseRef = SalesSchemas["CaseRefView"];

/** The longest question the API takes (`QUESTION_CHARS`). */
const QUESTION_MAX = 500;

/** Questions to start from; a follow-up ("PO đó…") reads as the PO just asked. */
const EXAMPLES = [
  "PO NRV-PO-26-0457 tới đâu rồi?",
  "Tôi còn việc gì?",
  "Có việc nào quá hạn không?",
];

/** What DW1 answers: the agreed list (ADR 0007), said before anyone asks. */
const CATALOG =
  "Hỏi trạng thái một PO, một yêu cầu báo giá, việc đang chờ bạn hoặc việc quá hạn. Câu trả lời không có số tiền.";

function caseHref(ref: CaseRef): string {
  return ref.kind === "order"
    ? `/sales/orders/${ref.case_id}`
    : `/sales/quotes/${ref.case_id}`;
}

/**
 * Hỏi đáp DW1 (dw_sales ADR 0007; the contract's DW01 criterion 6): status
 * questions answered from live data, in the person's own sessions. The model
 * reads the question; code finds the case among those the person may see and
 * answers, each answer linking the cases it rests on and marked "Máy viết"
 * when the model worded it. The session is in the URL, so a conversation can
 * be reopened; nobody else can open it.
 */
export default function AssistantPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Suspense>
        <Assistant />
      </Suspense>
    </ScopeGate>
  );
}

function Assistant() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const sessionId = params.get("session");
  const sessions = useResource("assistant-sessions", () =>
    salesApi().assistantSessions(),
  );
  const open = (id: string | null) =>
    router.replace(
      id ? `${pathname}?session=${encodeURIComponent(id)}` : pathname,
    );

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Hỏi đáp DW1"
        breadcrumb={salesCrumbs("Hỏi đáp DW1")}
        subtitle={CATALOG}
        help="DW1 trả lời từ dữ liệu đang có trong hệ thống, trong phạm vi hồ sơ bạn được xem."
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[300px_1fr]">
        <Card
          size="small"
          title="Phiên hỏi đáp"
          extra={
            <Button size="small" onClick={() => open(null)}>
              Phiên mới
            </Button>
          }
        >
          {sessions.error ? (
            <LoadError
              error={sessions.error}
              onRetry={sessions.reload}
              compact
            />
          ) : sessions.loading ? (
            <Skeleton active paragraph={{ rows: 3 }} />
          ) : (
            <List
              size="small"
              dataSource={sessions.data ?? []}
              locale={{
                emptyText: (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="Chưa có phiên nào. Đặt câu hỏi đầu tiên ở bên cạnh."
                  />
                ),
              }}
              renderItem={(s) => (
                <List.Item>
                  <Link
                    href={`${pathname}?session=${encodeURIComponent(s.session_id)}`}
                    aria-current={
                      s.session_id === sessionId ? "page" : undefined
                    }
                  >
                    <Flex vertical>
                      <Typography.Text strong={s.session_id === sessionId}>
                        {s.title}
                      </Typography.Text>
                      <Typography.Text>
                        {formatDateTime(s.last_turn_at)}
                      </Typography.Text>
                    </Flex>
                  </Link>
                </List.Item>
              )}
            />
          )}
        </Card>
        <Conversation
          key={sessionId ?? "new"}
          sessionId={sessionId}
          onOpened={(id) => {
            sessions.reload();
            if (id !== sessionId) open(id);
          }}
        />
      </div>
    </div>
  );
}

/** How DW1 read a question, in the words the page shows as its first step. */
const READ_AS: Record<Turn["kind"], string> = {
  order_status: "Hiểu là hỏi trạng thái một PO",
  quote_status: "Hiểu là hỏi trạng thái một yêu cầu báo giá",
  my_work: "Hiểu là hỏi việc đang chờ bạn",
  overdue: "Hiểu là hỏi việc quá hạn",
  out_of_scope: "Câu này ngoài những gì DW1 trả lời",
};

/** What DW1 did, from what the server returned: never more than it says. */
function chatTurn(turn: Turn): ChatTurn {
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

function Conversation({
  sessionId,
  onOpened,
}: {
  sessionId: string | null;
  onOpened: (id: string) => void;
}) {
  const online = useOnline();
  const keys = useIdempotencyKeys();
  const loaded = useResource(
    `assistant-session-${sessionId ?? "new"}`,
    () => salesApi().assistantSession(sessionId!),
    { enabled: sessionId !== null },
  );
  const [asked, setAsked] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState(NOTHING_YET);
  const [error, setError] = useState<unknown>(null);
  const stopper = useRef<AbortController | null>(null);
  const turns = [...(loaded.data?.turns ?? []), ...asked];

  const ask = async (text: string) => {
    const payload = { question: text, sessionId };
    const stop = new AbortController();
    stopper.current = stop;
    setBusy(true);
    setLive(NOTHING_YET);
    setError(null);
    try {
      const answer = await salesApi().assistantStream(
        text,
        sessionId,
        keys.keyFor("assistant-ask", payload),
        (event) => setLive((now) => liveAfter(now, event)),
        stop.signal,
      );
      keys.settle("assistant-ask");
      setAsked((earlier) => [...earlier, answer.turn]);
      setQuestion("");
      onOpened(answer.session_id);
    } catch (e) {
      // A person who pressed stop was told nothing went wrong, and asking the
      // same thing again is a new question.
      if (stop.signal.aborted) keys.settle("assistant-ask");
      else setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      size="small"
      title={sessionId ? (loaded.data?.title ?? "Phiên hỏi đáp") : "Phiên mới"}
    >
      {loaded.error ? (
        <LoadError error={loaded.error} onRetry={loaded.reload} compact />
      ) : (
        <AssistantChat
          worker="DW1"
          examples={EXAMPLES}
          turns={turns.map(chatTurn)}
          loading={sessionId !== null && loaded.loading}
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
      )}
    </Card>
  );
}
