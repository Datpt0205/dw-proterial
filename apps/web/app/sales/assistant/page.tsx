"use client";

import { Suspense, useState } from "react";
import type { KeyboardEvent } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import {
  App,
  Button,
  Card,
  Empty,
  Flex,
  Input,
  List,
  Skeleton,
  Space,
  Tag,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, useOnline, OFFLINE_REASON } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
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

function Conversation({
  sessionId,
  onOpened,
}: {
  sessionId: string | null;
  onOpened: (id: string) => void;
}) {
  const { message } = App.useApp();
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
  const [error, setError] = useState<unknown>(null);
  const turns = [...(loaded.data?.turns ?? []), ...asked];

  const ask = async () => {
    const text = question.trim();
    if (!text || busy) return;
    if (!online) {
      setError(new Error(OFFLINE_REASON));
      return;
    }
    const payload = { question: text, sessionId };
    setBusy(true);
    setError(null);
    try {
      const answer = await salesApi().assistantAsk(
        text,
        sessionId,
        keys.keyFor("assistant-ask", payload),
      );
      keys.settle("assistant-ask");
      setAsked((earlier) => [...earlier, answer.turn]);
      setQuestion("");
      onOpened(answer.session_id);
    } catch (e) {
      setError(e);
      void message.error("DW1 chưa trả lời được câu này.");
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter breaks the line; never mid-composition
    // (Telex, Gboard), or a half-typed word is sent.
    if (
      event.key === "Enter" &&
      !event.shiftKey &&
      !event.nativeEvent.isComposing
    ) {
      event.preventDefault();
      void ask();
    }
  };

  return (
    <Card
      size="small"
      title={sessionId ? (loaded.data?.title ?? "Phiên hỏi đáp") : "Phiên mới"}
    >
      <Flex vertical gap={12}>
        {loaded.error ? (
          <LoadError error={loaded.error} onRetry={loaded.reload} compact />
        ) : sessionId && loaded.loading ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : turns.length === 0 ? (
          <Typography.Text>
            Ví dụ: “PO NRV-PO-26-0457 tới đâu rồi?”, “Tôi còn việc gì?”, “Có
            việc nào quá hạn không?”. Hỏi tiếp “PO đó đã xác nhận chưa?” thì DW1
            hiểu là PO vừa hỏi.
          </Typography.Text>
        ) : (
          <ol
            className="m-0 flex list-none flex-col gap-3 p-0"
            aria-label="Các lượt hỏi đáp"
            aria-live="polite"
          >
            {turns.map((turn) => (
              <TurnItem key={turn.seq} turn={turn} />
            ))}
          </ol>
        )}
        <Flex vertical gap={6}>
          <Input.TextArea
            aria-label="Câu hỏi cho DW1"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={onKeyDown}
            maxLength={QUESTION_MAX}
            showCount
            autoSize={{ minRows: 2, maxRows: 6 }}
            placeholder="Ví dụ: PO NRV-PO-26-0457 tới đâu rồi?"
            disabled={busy}
          />
          <Space wrap>
            <Button
              type="primary"
              loading={busy}
              disabled={!question.trim()}
              onClick={() => void ask()}
            >
              Hỏi DW1
            </Button>
            <Typography.Text>
              Enter để gửi, Shift+Enter để xuống dòng.
            </Typography.Text>
          </Space>
          <ActionError error={error} />
        </Flex>
      </Flex>
    </Card>
  );
}

function TurnItem({ turn }: { turn: Turn }) {
  return (
    <li>
      <Flex vertical gap={4}>
        <Typography.Text strong>Bạn: {turn.question}</Typography.Text>
        <Space wrap size={4}>
          <Typography.Text strong>DW1:</Typography.Text>
          {turn.answered_by === "model" ? <Tag>Máy viết</Tag> : null}
        </Space>
        <Typography.Paragraph className="mb-0! whitespace-pre-wrap">
          {turn.answer}
        </Typography.Paragraph>
        {turn.cites.length ? (
          <Space wrap size={4}>
            <Typography.Text>Căn cứ:</Typography.Text>
            {turn.cites.map((ref) => (
              <Link key={ref.case_id} href={caseHref(ref)}>
                <Tag>{ref.label}</Tag>
              </Link>
            ))}
          </Space>
        ) : null}
      </Flex>
    </li>
  );
}
