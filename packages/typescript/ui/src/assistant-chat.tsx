"use client";

import {
  useEffect,
  useMemo,
  useRef,
  type ComponentProps,
  type ReactNode,
} from "react";
import {
  Alert,
  Avatar,
  Flex,
  Input,
  Skeleton,
  Space,
  Tag,
  theme,
  Typography,
} from "antd";
import {
  BulbOutlined,
  LinkOutlined,
  MessageOutlined,
  RobotOutlined,
  UserOutlined,
} from "@ant-design/icons";
// One component per path: the package's index also loads its diagram and
// code renderers (mermaid), which no chat here draws.
import ActionsCopy from "@ant-design/x/es/actions/ActionsCopy";
import Bubble from "@ant-design/x/es/bubble";
import Prompts from "@ant-design/x/es/prompts";
import Sender from "@ant-design/x/es/sender";
import Think from "@ant-design/x/es/think";
import ThoughtChain from "@ant-design/x/es/thought-chain";
import Welcome from "@ant-design/x/es/welcome";
import XProvider from "@ant-design/x/es/x-provider";
import type { Locale } from "@ant-design/x/es/locale";

/** Ant Design X ships no Vietnamese: the words it draws itself, in ours. */
const VI_VN: Locale = {
  locale: "vi",
  Conversations: { create: "Phiên mới" },
  Sender: { stopLoading: "Dừng", speechRecording: "Đang ghi âm" },
  Actions: {
    feedbackLike: "Hữu ích",
    feedbackDislike: "Chưa đúng",
    audio: "Phát âm thanh",
    audioRunning: "Đang phát",
    audioError: "Không phát được",
    audioLoading: "Đang tải âm thanh",
  },
  Bubble: { editableOk: "Xong", editableCancel: "Hủy" },
  Mermaid: {
    zoomIn: "Phóng to",
    zoomOut: "Thu nhỏ",
    zoomReset: "Về cỡ gốc",
    download: "Tải về",
    code: "Mã",
    image: "Hình",
  },
  Folder: {
    selectFile: "Chọn một tệp",
    loadError: "Không tải được tệp",
    noService: "Chưa cấu hình dịch vụ đọc tệp",
    loadFailed: "Không tải được tệp",
  },
};

/** What the worker did to answer, as the server says it: never invented here. */
export interface ChatStep {
  key: string;
  title: string;
  description?: string;
}

export interface ChatTurn {
  key: string;
  question: string;
  answer: string;
  /** The model worded the answer ("Máy viết"); else code's own sentence. */
  byModel: boolean;
  steps: ChatStep[];
  /** The records the answer rests on, each a link the app renders. */
  cites: { key: string; label: ReactNode }[];
  /** A control the app offers under the answer (a case page's own button),
   * with that page's gate and API; the chat itself starts nothing. */
  action?: ReactNode;
}

/** The turn being answered, as far as it has come. */
export interface ChatLive {
  steps: ChatStep[];
  answer: string;
}

export interface AssistantChatProps {
  /** The worker's name as people call it: "DW1", "DW2". */
  worker: string;
  /** What it answers, said before anyone asks; leave it out where the page
   * header says it already. */
  catalog?: string;
  examples: string[];
  turns: ChatTurn[];
  /** The session's turns are loading. */
  loading?: boolean;
  /** A question is being answered. */
  pending?: boolean;
  /** How far the answer has come, while ``pending``. */
  live?: ChatLive | null;
  /** Stops the answer being written. */
  onStop?: () => void;
  question: string;
  onQuestion: (value: string) => void;
  onAsk: (question: string) => void;
  maxLength: number;
  /** Why asking is not possible now (offline, no scope), shown in words. */
  blocked?: string | null;
  /** The last refusal, in the server's words. */
  error?: ReactNode;
}

/** The nearest ancestor that scrolls itself (a drawer's body, a side
 * panel), never the page: following the newest turn must not move the case
 * the person is reading. */
function scroller(el: HTMLElement): HTMLElement | null {
  for (
    let p = el.parentElement;
    p && p !== document.body;
    p = p.parentElement
  ) {
    const y = getComputedStyle(p).overflowY;
    if ((y === "auto" || y === "scroll") && p.scrollHeight > p.clientHeight) {
      return p;
    }
  }
  return null;
}

/** A finished step and the one under way, as `ThoughtChain` draws them. */
function chainOf(steps: ChatStep[], running: boolean) {
  return steps.map((step, index) => ({
    key: step.key,
    title: step.title,
    description: step.description,
    status:
      running && index === steps.length - 1
        ? ("loading" as const)
        : ("success" as const),
  }));
}

/**
 * One chat frame for every worker's Q&A, on Ant Design X (CLAUDE.md "Web UI",
 * 2026-11-04): the person's question on the right; the worker's answer on the
 * left with "Máy viết" when the model worded it, what it did to answer
 * (`steps`, from the server) and the records it rests on. Enter sends,
 * Shift+Enter breaks the line, never mid-composition (the `Sender` waits for
 * Telex and Gboard). Domain-neutral: the app says what a step and a record
 * are, and links them.
 *
 * Drawn like an agent at work (Đạt, 2026-11-26, antd and Ant Design X parts
 * only): avatars for the worker and the person; while answering, a `Think`
 * panel whose `ThoughtChain` shows the server's steps as they arrive, the
 * one under way loading; once answered, the steps fold into "đã làm gì", and
 * the answer can be copied. Every step shown is one the server sent: the
 * frame never invents progress.
 */
export function AssistantChat({
  worker,
  catalog,
  examples,
  turns,
  loading = false,
  pending = false,
  live = null,
  onStop,
  question,
  onQuestion,
  onAsk,
  maxLength,
  blocked = null,
  error,
}: AssistantChatProps) {
  // The input has a name of its own: a placeholder is no label.
  const Labelled = useMemo(
    () =>
      function LabelledInput(props: ComponentProps<typeof Input.TextArea>) {
        return (
          <Input.TextArea {...props} aria-label={`Câu hỏi cho ${worker}`} />
        );
      },
    [worker],
  );
  const ask = (text: string) => {
    const trimmed = text.trim();
    if (trimmed && !pending && !blocked) onAsk(trimmed.slice(0, maxLength));
  };
  const { token } = theme.useToken();
  // The newest turn stays in view: whenever the frame changes size (a turn
  // added, words arriving, a hidden tab shown), its own scroll box goes to
  // the end.
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = root.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const follow = new ResizeObserver(() => {
      const box = scroller(el);
      if (box) box.scrollTop = box.scrollHeight;
    });
    follow.observe(el);
    return () => follow.disconnect();
  }, []);
  const workerAvatar = (size?: number) => (
    <Avatar
      size={size}
      icon={<RobotOutlined aria-hidden />}
      style={{ backgroundColor: token.colorPrimary }}
    />
  );
  const personAvatar = <Avatar icon={<UserOutlined aria-hidden />} />;
  const answerText = (text: string) => (
    <Typography.Paragraph className="mb-0! whitespace-pre-wrap">
      {text}
    </Typography.Paragraph>
  );
  const asked = (text: string) => (
    <Bubble
      placement="end"
      avatar={personAvatar}
      variant="filled"
      shape="corner"
      content={text}
    />
  );

  return (
    <XProvider locale={VI_VN}>
      <Flex vertical gap={12} ref={root}>
        {loading ? (
          <Skeleton active avatar paragraph={{ rows: 4 }} />
        ) : turns.length === 0 && !pending ? (
          <Flex vertical gap={12}>
            <Welcome
              icon={workerAvatar(48)}
              title={`Hỏi đáp ${worker}`}
              description={catalog}
            />
            <Prompts
              title={
                <Space size={6}>
                  <BulbOutlined aria-hidden />
                  <span>Thử hỏi</span>
                </Space>
              }
              wrap
              items={examples.map((text) => ({
                key: text,
                icon: <MessageOutlined aria-hidden />,
                description: text,
              }))}
              onItemClick={({ data }) => ask(String(data.description ?? ""))}
            />
          </Flex>
        ) : (
          <ol
            className="m-0 flex list-none flex-col gap-3 p-0"
            aria-label="Các lượt hỏi đáp"
            aria-live="polite"
            aria-busy={pending}
          >
            {turns.map((turn) => (
              <li key={turn.key}>
                <Flex vertical gap={8}>
                  {asked(turn.question)}
                  <Bubble
                    placement="start"
                    avatar={workerAvatar()}
                    variant="outlined"
                    shape="corner"
                    header={
                      <Flex vertical gap={6}>
                        <Space size={4}>
                          <Typography.Text strong>{worker}</Typography.Text>
                          {turn.byModel ? (
                            <Tag icon={<RobotOutlined aria-hidden />}>
                              Máy viết
                            </Tag>
                          ) : null}
                        </Space>
                        {turn.steps.length ? (
                          <Think
                            title={`${worker} đã làm gì · ${turn.steps.length} bước`}
                            defaultExpanded={false}
                          >
                            <ThoughtChain items={chainOf(turn.steps, false)} />
                          </Think>
                        ) : null}
                      </Flex>
                    }
                    content={turn.answer}
                    contentRender={answerText}
                    footer={
                      <Flex vertical gap={6}>
                        <Flex align="center" gap={8} wrap>
                          <ActionsCopy
                            text={turn.answer}
                            aria-label="Sao chép câu trả lời"
                          />
                          {turn.cites.length ? (
                            <Space wrap size={4}>
                              <Typography.Text>
                                <LinkOutlined aria-hidden /> Căn cứ:
                              </Typography.Text>
                              {turn.cites.map((cite) => (
                                <span key={cite.key}>{cite.label}</span>
                              ))}
                            </Space>
                          ) : null}
                        </Flex>
                        {turn.action ?? null}
                      </Flex>
                    }
                  />
                </Flex>
              </li>
            ))}
            {pending ? (
              // The question just asked, and that the worker is on it: a
              // first answer can take a minute while the model loads.
              <li>
                <Flex vertical gap={8}>
                  {question.trim() ? asked(question.trim()) : null}
                  <Think
                    title={
                      <Typography.Text role="status">
                        {live?.steps.at(-1)?.title ?? `${worker} đang trả lời…`}
                      </Typography.Text>
                    }
                    loading
                    blink
                    defaultExpanded
                  >
                    {live?.steps.length ? (
                      <ThoughtChain items={chainOf(live.steps, true)} />
                    ) : null}
                  </Think>
                  {live?.answer ? (
                    <Bubble
                      placement="start"
                      avatar={workerAvatar()}
                      variant="outlined"
                      shape="corner"
                      header={
                        <Typography.Text strong>{worker}</Typography.Text>
                      }
                      content={live.answer}
                      streaming
                      contentRender={answerText}
                    />
                  ) : (
                    <Bubble
                      placement="start"
                      avatar={workerAvatar()}
                      variant="outlined"
                      shape="corner"
                      loading
                      content=""
                    />
                  )}
                </Flex>
              </li>
            ) : null}
          </ol>
        )}
        <Sender
          value={question}
          onChange={(value) => onQuestion(value.slice(0, maxLength))}
          onSubmit={ask}
          loading={pending}
          onCancel={onStop}
          disabled={blocked !== null}
          placeholder={
            blocked ??
            `Hỏi ${worker}… (Enter để gửi, Shift+Enter để xuống dòng)`
          }
          autoSize={{ minRows: 2, maxRows: 6 }}
          components={{ input: Labelled }}
          // The Sender waits out composition events; a key event that says it
          // is mid-composition (Telex, Gboard) is never a send either.
          onKeyDown={(event) =>
            (event.nativeEvent as KeyboardEvent).isComposing ? false : undefined
          }
        />
        <Typography.Text>
          {question.length}/{maxLength}
        </Typography.Text>
        {error ? <Alert type="error" showIcon title={error} /> : null}
      </Flex>
    </XProvider>
  );
}
