"use client";

import { Suspense, useCallback, useState } from "react";
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
import type { PurchaseAssistantTurn } from "@dw/api-client";
import {
  AssistantChat,
  OFFLINE_REASON,
  PageHeader,
  useOnline,
  type ChatTurn,
} from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { errorMessage } from "../../../lib/error-message";
import { useIdempotencyKeys } from "../../../lib/idempotency";
import { useCachedResource } from "../../../lib/use-cached-resource";
import { purchasingApi } from "../_lib/api";
import { SCOPE } from "../_lib/scopes";
import { purchasingCrumbs, ScopeGate } from "../_components/frame";

/** The longest question the API takes (`QUESTION_CHARS`). */
const QUESTION_MAX = 500;

/** What DW2 answers, said before anyone asks (`domain.assistant.CATALOG`). */
const CATALOG =
  "Hỏi một yêu cầu mua hàng đang ở bước nào (theo số PR), việc đang chờ bạn, hoặc đơn nào trễ hạn. Câu trả lời không có số tiền.";

const EXAMPLES = [
  "PR-2611-004 tới đâu rồi?",
  "Việc của tôi là gì?",
  "Đơn nào trễ hạn?",
];

/**
 * Hỏi đáp DW2 (DW02 function 6), on the one chat frame: the model reads the
 * question, code answers from the cases the person may see, and what DW2
 * did is the server's own list of steps. A session is the person's own; its
 * id is in the URL so it can be reopened.
 */
export default function PurchasingAssistantPage() {
  return (
    <ScopeGate scope={[SCOPE.read, SCOPE.readOwn]}>
      <Suspense>
        <Assistant />
      </Suspense>
    </ScopeGate>
  );
}

function Assistant() {
  const router = useRouter();
  const pathname = usePathname();
  const sessionId = useSearchParams().get("session");
  const sessions = useCachedResource(
    "purchasing/assistant-sessions",
    useCallback(() => purchasingApi().assistantSessions(), []),
  );
  const open = (id: string | null) =>
    router.replace(
      id ? `${pathname}?session=${encodeURIComponent(id)}` : pathname,
    );

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Hỏi đáp DW2"
        breadcrumb={purchasingCrumbs("Hỏi đáp DW2")}
        subtitle={CATALOG}
        help="DW2 trả lời từ dữ liệu đang có trong hệ thống, trong phạm vi hồ sơ bạn được xem."
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
          ) : !sessions.data ? (
            <Skeleton active paragraph={{ rows: 3 }} />
          ) : (
            <List
              size="small"
              dataSource={sessions.data}
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

function chatTurn(turn: PurchaseAssistantTurn): ChatTurn {
  return {
    key: String(turn.seq),
    question: turn.question,
    answer: turn.answer,
    byModel: turn.answered_by === "model",
    steps: turn.steps.map((s) => ({ key: s.key, title: s.title })),
    cites: turn.cites.map((ref) => ({
      key: ref.case_id,
      label: (
        <Link href={`/purchasing/requests/${ref.case_id}`}>
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
  const loaded = useCachedResource(
    `purchasing/assistant-session/${sessionId ?? "new"}`,
    useCallback(
      () =>
        sessionId
          ? purchasingApi().assistantSession(sessionId)
          : Promise.resolve(null),
      [sessionId],
    ),
  );
  const [asked, setAsked] = useState<PurchaseAssistantTurn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const turns = [...(loaded.data?.turns ?? []), ...asked];

  const ask = async (text: string) => {
    const payload = { question: text, sessionId };
    setBusy(true);
    setError(null);
    try {
      const answer = await purchasingApi().assistantAsk(
        text,
        sessionId,
        keys.keyFor("purchasing-assistant-ask", payload),
      );
      keys.settle("purchasing-assistant-ask");
      setAsked((earlier) => [...earlier, answer.turn]);
      setQuestion("");
      onOpened(answer.session_id);
    } catch (e) {
      setError(e);
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
          worker="DW2"
          examples={EXAMPLES}
          turns={turns.map(chatTurn)}
          loading={sessionId !== null && !loaded.data}
          pending={busy}
          question={question}
          onQuestion={setQuestion}
          onAsk={(text) => void ask(text)}
          maxLength={QUESTION_MAX}
          blocked={online ? null : OFFLINE_REASON}
          error={error ? errorMessage(error) : null}
        />
      )}
    </Card>
  );
}
