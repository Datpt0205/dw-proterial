"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import Link from "next/link";
import {
  Avatar,
  Badge,
  Button,
  Card,
  Drawer,
  Empty,
  Flex,
  FloatButton,
  Grid,
  Segmented,
  Skeleton,
  Tag,
  theme,
  Typography,
} from "antd";
import {
  ArrowRightOutlined,
  FolderOpenOutlined,
  HistoryOutlined,
  MessageOutlined,
  RightOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import { useOnline } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { useResource } from "../_lib/use-resource";
import {
  AssistantConversation,
  caseHref,
  GENERAL_CATALOG,
  GENERAL_EXAMPLES,
} from "./assistant-conversation";
import { SCOPE } from "./sales-frame";

const NAME = "Trợ lý DW1";
const OPEN = "Hỏi DW1";

type Tab = "sessions" | "chat";

/** A page's way to say it draws a conversation of its own. */
const HideContext = createContext<((delta: 1 | -1) => void) | null>(null);

/**
 * A page that already draws a DW1 conversation (a case's, or the general one
 * on "Hỏi đáp DW1") hides the widget while it is mounted, so one screen never
 * offers two chats. Outside the widget's provider it does nothing.
 */
export function useHideAssistantWidget() {
  const hide = useContext(HideContext);
  useEffect(() => {
    if (!hide) return;
    hide(1);
    return () => hide(-1);
  }, [hide]);
}

/**
 * The person's general conversation with DW1 (dw_sales ADR 0007, ticket 46)
 * as a widget on every Sales page (Đạt, 2026-11-26), for whoever reads
 * cases: a button at the bottom right opens a drawer, from the right on a
 * desktop and from the bottom below `lg` (ui-quality §9), drawn after the
 * landing page's assistant Đạt pointed to, in antd parts only. Two tabs:
 * "Phiên" (a greeting, questions to start from, and the person's
 * conversations: the general one and each case asked about, an unseen
 * answer marked) and "Tin nhắn" (the general conversation itself, the same
 * server-side one as the "Hỏi đáp DW1" page). A case's conversation opens on
 * its page, where the case's own controls are. Mounted on first open and
 * kept, tab switches included, so an answer still arriving is not lost.
 */
export function AssistantWidget({ children }: { children: ReactNode }) {
  const { hasScope } = useAuth();
  const lg = Grid.useBreakpoint().lg;
  const [hidden, setHidden] = useState(0);
  const [open, setOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [tab, setTab] = useState<Tab>("sessions");
  const [prompt, setPrompt] = useState<{ text: string; at: number }>();
  const hide = useCallback((delta: 1 | -1) => setHidden((n) => n + delta), []);
  const shown = hasScope(SCOPE.caseRead) && hidden === 0;

  // Leaving for a page with its own conversation closes the drawer, so it
  // does not pop open again on the way back.
  useEffect(() => {
    if (!shown) setOpen(false);
  }, [shown]);

  const askNow = (text: string) => {
    setPrompt({ text, at: Date.now() });
    setTab("chat");
  };

  return (
    <HideContext.Provider value={hide}>
      {children}
      {shown ? (
        <>
          <FloatButton
            type="primary"
            icon={<MessageOutlined aria-hidden />}
            aria-label={OPEN}
            tooltip={OPEN}
            onClick={() => {
              setMounted(true);
              setOpen(true);
            }}
            style={{ insetInlineEnd: 20, bottom: 20 }}
          />
          {mounted ? (
            <Drawer
              open={open}
              onClose={() => setOpen(false)}
              placement={lg === false ? "bottom" : "right"}
              size={lg === false ? "88vh" : 440}
              title={<WidgetTitle />}
              footer={
                <Segmented<Tab>
                  block
                  value={tab}
                  onChange={setTab}
                  aria-label="Chọn mục của trợ lý"
                  options={[
                    {
                      value: "sessions",
                      label: "Phiên",
                      icon: <HistoryOutlined aria-hidden />,
                    },
                    {
                      value: "chat",
                      label: "Tin nhắn",
                      icon: <MessageOutlined aria-hidden />,
                    },
                  ]}
                />
              }
            >
              {tab === "sessions" ? (
                <Sessions onAsk={askNow} onChat={() => setTab("chat")} />
              ) : null}
              <div hidden={tab !== "chat"}>
                <AssistantConversation
                  onCase={null}
                  examples={GENERAL_EXAMPLES}
                  catalog={GENERAL_CATALOG}
                  prompt={prompt}
                />
              </div>
            </Drawer>
          ) : null}
        </>
      ) : null}
    </HideContext.Provider>
  );
}

/** Who answers, and whether this browser can reach it. */
function WidgetTitle() {
  const { token } = theme.useToken();
  const online = useOnline();
  return (
    <Flex align="center" gap={10}>
      <Avatar
        icon={<RobotOutlined aria-hidden />}
        style={{ backgroundColor: token.colorPrimary }}
      />
      <Flex vertical>
        <Flex align="center" gap={6}>
          <Typography.Text strong>{NAME}</Typography.Text>
          <Tag>AI</Tag>
        </Flex>
        <Badge
          status={online ? "success" : "default"}
          text={online ? "Đang kết nối" : "Mất kết nối mạng"}
        />
      </Flex>
    </Flex>
  );
}

/**
 * "Phiên": a greeting, the questions to start from (each asked at once), and
 * the person's conversations, newest first.
 */
function Sessions({
  onAsk,
  onChat,
}: {
  onAsk: (text: string) => void;
  onChat: () => void;
}) {
  const { token } = theme.useToken();
  const { displayName } = useAuth();
  const recent = useResource(
    "assistant-cases",
    useCallback(() => salesApi().assistantCases(), []),
  );

  return (
    <Flex vertical gap={16}>
      <div
        style={{
          background: token.colorPrimaryBg,
          borderRadius: token.borderRadiusLG,
          padding: token.paddingLG,
        }}
      >
        <Typography.Title level={3} className="mb-1!">
          {displayName ? `Xin chào, ${displayName}!` : "Xin chào!"}
        </Typography.Title>
        <Typography.Paragraph className="mb-0!">
          {GENERAL_CATALOG}
        </Typography.Paragraph>
      </div>

      <Card size="small">
        <Flex align="center" justify="space-between" gap={12}>
          <Flex vertical>
            <Typography.Text strong>Đặt câu hỏi cho DW1</Typography.Text>
            <Typography.Text>Trả lời từ dữ liệu bạn được xem</Typography.Text>
          </Flex>
          <Button
            type="primary"
            shape="circle"
            size="large"
            icon={<ArrowRightOutlined aria-hidden />}
            aria-label="Đặt câu hỏi cho DW1"
            onClick={onChat}
          />
        </Flex>
      </Card>

      <Card size="small" title="Thử hỏi">
        <Flex vertical>
          {GENERAL_EXAMPLES.map((text) => (
            <Button
              key={text}
              type="text"
              block
              onClick={() => onAsk(text)}
              className="justify-between!"
            >
              <span>{text}</span>
              <RightOutlined aria-hidden />
            </Button>
          ))}
        </Flex>
      </Card>

      <Card
        size="small"
        title="Phiên gần đây"
        extra={<Link href="/sales/assistant">Xem tất cả</Link>}
      >
        <Flex vertical gap={8}>
          <Button
            type="text"
            block
            icon={<MessageOutlined aria-hidden />}
            onClick={onChat}
            className="justify-start!"
          >
            Trò chuyện chung
          </Button>
          {recent.error ? (
            <LoadError error={recent.error} onRetry={recent.reload} compact />
          ) : recent.loading ? (
            <Skeleton active paragraph={{ rows: 2 }} />
          ) : recent.data?.length ? (
            recent.data.map((c) => (
              <Link key={c.case.case_id} href={caseHref(c.case)}>
                <Flex align="center" gap={8} className="px-4 py-1">
                  <FolderOpenOutlined aria-hidden />
                  <Flex vertical>
                    <Badge dot={c.unread} offset={[6, 0]}>
                      <Typography.Text strong={c.unread}>
                        {c.case.label}
                      </Typography.Text>
                    </Badge>
                    <Typography.Text>
                      {c.unread ? "Có trả lời chưa xem · " : ""}
                      {formatDateTime(c.last_turn_at)}
                    </Typography.Text>
                  </Flex>
                </Flex>
              </Link>
            ))
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="Chưa hỏi hồ sơ nào. Hỏi trên trang của một hồ sơ để mở phiên của nó."
            />
          )}
        </Flex>
      </Card>
    </Flex>
  );
}
