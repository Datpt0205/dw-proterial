"use client";

import { useMemo, type ComponentProps, type ReactNode } from "react";
import { Alert, Flex, Input, Skeleton, Space, Tag, Typography } from "antd";
// One component per path: the package's index also loads its diagram and
// code renderers (mermaid), which no chat here draws.
import Bubble from "@ant-design/x/es/bubble";
import Prompts from "@ant-design/x/es/prompts";
import Sender from "@ant-design/x/es/sender";
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
  question: string;
  onQuestion: (value: string) => void;
  onAsk: (question: string) => void;
  maxLength: number;
  /** Why asking is not possible now (offline, no scope), shown in words. */
  blocked?: string | null;
  /** The last refusal, in the server's words. */
  error?: ReactNode;
}

/**
 * One chat frame for every worker's Q&A, on Ant Design X (CLAUDE.md "Web UI",
 * 2026-11-04): the person's question on the right; the worker's answer on the
 * left with "Máy viết" when the model worded it, what it did to answer
 * (`steps`, from the server) and the records it rests on. Enter sends,
 * Shift+Enter breaks the line, never mid-composition (the `Sender` waits for
 * Telex and Gboard). Domain-neutral: the app says what a step and a record
 * are, and links them.
 */
export function AssistantChat({
  worker,
  catalog,
  examples,
  turns,
  loading = false,
  pending = false,
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

  return (
    <XProvider locale={VI_VN}>
      <Flex vertical gap={12}>
        {loading ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : turns.length === 0 ? (
          <Flex vertical gap={12}>
            <Welcome title={`Hỏi đáp ${worker}`} description={catalog} />
            <Prompts
              title="Thử hỏi"
              wrap
              items={examples.map((text) => ({ key: text, description: text }))}
              onItemClick={({ data }) => ask(String(data.description ?? ""))}
            />
          </Flex>
        ) : (
          <ol
            className="m-0 flex list-none flex-col gap-3 p-0"
            aria-label="Các lượt hỏi đáp"
            aria-live="polite"
          >
            {turns.map((turn) => (
              <li key={turn.key}>
                <Flex vertical gap={8}>
                  <Bubble placement="end" content={turn.question} />
                  <Bubble
                    placement="start"
                    header={
                      <Space size={4}>
                        <Typography.Text strong>{worker}</Typography.Text>
                        {turn.byModel ? <Tag>Máy viết</Tag> : null}
                      </Space>
                    }
                    content={turn.answer}
                    contentRender={(text) => (
                      <Typography.Paragraph className="mb-0! whitespace-pre-wrap">
                        {text}
                      </Typography.Paragraph>
                    )}
                    footer={
                      <Flex vertical gap={4}>
                        {turn.steps.length ? (
                          <ThoughtChain
                            items={[
                              {
                                key: "done",
                                title: `${worker} đã làm gì`,
                                collapsible: true,
                                status: "success",
                                content: (
                                  <ThoughtChain
                                    items={turn.steps.map((step) => ({
                                      key: step.key,
                                      title: step.title,
                                      description: step.description,
                                      status: "success",
                                    }))}
                                  />
                                ),
                              },
                            ]}
                          />
                        ) : null}
                        {turn.cites.length ? (
                          <Space wrap size={4}>
                            <Typography.Text>Căn cứ:</Typography.Text>
                            {turn.cites.map((cite) => (
                              <span key={cite.key}>{cite.label}</span>
                            ))}
                          </Space>
                        ) : null}
                      </Flex>
                    }
                  />
                </Flex>
              </li>
            ))}
            {pending ? (
              <li>
                <Bubble placement="start" loading content="" />
              </li>
            ) : null}
          </ol>
        )}
        <Sender
          value={question}
          onChange={(value) => onQuestion(value.slice(0, maxLength))}
          onSubmit={ask}
          loading={pending}
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
