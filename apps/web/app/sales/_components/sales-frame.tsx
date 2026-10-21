"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  Alert,
  Button,
  Flex,
  Form,
  Input,
  Modal,
  theme,
  Tooltip,
  Typography,
} from "antd";
import {
  InfoCircleOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { label, SALES_ROLE } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useAction } from "../_lib/use-action";
import { useResource, type Resource } from "../_lib/use-resource";
import { GuardedButton } from "./guarded-button";

type Overview = SalesSchemas["OverviewView"];
type Message = SalesSchemas["InboxMessageView"];

/** How often the bar reads the mailbox again while DW1 has work queued. */
const PROGRESS_POLL_MS = 5_000;

/** The scopes the Sales screens branch on; the API checks them regardless. */
export const SCOPE = {
  overview: "sales.overview.read",
  caseRead: "sales.case.read",
  price: "sales.price.read",
  otherPrices: "sales.price.other_customers.read",
  inbox: "sales.inbox.process",
  prepare: "sales.order.prepare",
  crossCheck: "sales.order.cross_check",
  quote: "sales.quote.prepare",
  approve: "sales.quote.approve",
  ack: "sales.compliance.ack",
  pause: "sales.worker.pause",
  resume: "sales.worker.resume",
  assign: "sales.case.assign",
  layoutApprove: "sales.layout.approve",
  rulesPropose: "sales.rules.propose",
} as const;

interface SalesFrame {
  /** The overview: DW1's paused state and the WIV steps (one owner: the API). */
  overview: Resource<Overview>;
  paused: boolean;
}

/**
 * Why a step that is DW1's own work (processing a message, rendering a file
 * or a draft) is refused while DW1 is paused: one sentence for every button.
 * The server refuses the same step (`worker_paused`) whatever a button shows.
 */
export const PAUSED_REASON =
  "DW1 đang tạm dừng: chỉ Trưởng bộ phận Sales cho DW1 chạy lại.";

const SalesFrameContext = createContext<SalesFrame | null>(null);

export function useSalesFrame(): SalesFrame {
  const value = useContext(SalesFrameContext);
  if (!value)
    throw new Error("useSalesFrame must be used inside <SalesFrameProvider>");
  return value;
}

/**
 * What every Sales page sits in: DW1's state (running, or paused by whom and
 * when), read from the overview the API owns, and the pause and resume
 * controls. A viewer who may read the overview sees the state and no control.
 */
export function SalesFrameProvider({ children }: { children: ReactNode }) {
  const { hasScope } = useAuth();
  const overview = useResource<Overview>(
    "sales/overview",
    useCallback(() => salesApi().overview(), []),
    { enabled: hasScope(SCOPE.overview) },
  );
  const paused = overview.data?.worker.paused ?? false;
  return (
    <SalesFrameContext.Provider value={{ overview, paused }}>
      <WorkerBar overview={overview} />
      {children}
    </SalesFrameContext.Provider>
  );
}

const RESUME_REASON = `Chỉ ${label(SALES_ROLE, "sales_head")} cho DW1 chạy lại.`;

function WorkerBar({ overview }: { overview: Resource<Overview> }) {
  const { hasScope } = useAuth();
  const name = usePeople();
  const { run, pending } = useAction();
  const [dialog, setDialog] = useState<"pause" | "resume" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [form] = Form.useForm<{ reason?: string }>();
  const { token } = theme.useToken();
  const worker = overview.data?.worker;
  const progress = useWorkerProgress(Boolean(worker));
  if (!worker) return null;

  const submit = async ({ reason }: { reason?: string }) => {
    const text = reason?.trim() || null;
    const result =
      dialog === "pause"
        ? await run(
            "worker/pause",
            { reason: text },
            (key) => salesApi().pause(text, key),
            "Đã tạm dừng DW1",
          )
        : await run(
            "worker/resume",
            { reason: text },
            (key) => salesApi().resume(text ?? "", key),
            "DW1 đã chạy lại",
          );
    if (result.ok) {
      setDialog(null);
      setError(null);
      form.resetFields();
      overview.reload();
    } else setError(result.error);
  };

  const who = name(worker.changed_by);
  const when = worker.changed_at ? formatDateTime(worker.changed_at) : null;
  const explain = worker.paused
    ? "DW1 không xử lý thư mới và không soạn tệp hay thư nháp cho tới khi chạy lại; các bước của Sales vẫn làm được, tệp đã soạn vẫn tải được."
    : when
      ? `Thay đổi lần cuối ${when}${who ? ` bởi ${who}` : ""}.`
      : null;

  return (
    <div className="mb-3">
      <Alert
        type={worker.paused ? "warning" : "info"}
        showIcon
        icon={
          worker.paused ? (
            <PauseCircleOutlined aria-hidden />
          ) : (
            <RobotOutlined aria-hidden />
          )
        }
        role="status"
        className="py-1!"
        title={
          <Flex wrap gap={4} align="center">
            <Typography.Text strong>
              {worker.paused ? "DW1 đang tạm dừng" : headline(progress)}
            </Typography.Text>
            {worker.paused ? (
              <Typography.Text>
                · {who ? `bởi ${who}` : ""}
                {when ? ` lúc ${when}` : ""}
                {worker.reason ? ` · Lý do: ${worker.reason}` : ""}
              </Typography.Text>
            ) : null}
            {progress ? (
              <Typography.Text
                type="secondary"
                style={{ fontSize: token.fontSizeSM }}
              >
                · {progressLine(progress)}
              </Typography.Text>
            ) : null}
            {explain ? (
              <Tooltip title={explain}>
                <InfoCircleOutlined
                  aria-label={explain}
                  tabIndex={0}
                  role="img"
                />
              </Tooltip>
            ) : null}
          </Flex>
        }
        action={
          worker.paused ? (
            hasScope(SCOPE.pause) || hasScope(SCOPE.resume) ? (
              <GuardedButton
                size="small"
                inlineReason={false}
                icon={<PlayCircleOutlined aria-hidden />}
                reason={hasScope(SCOPE.resume) ? null : RESUME_REASON}
                onClick={() => setDialog("resume")}
              >
                Tiếp tục DW1
              </GuardedButton>
            ) : null
          ) : hasScope(SCOPE.pause) ? (
            <Button
              size="small"
              icon={<PauseCircleOutlined aria-hidden />}
              onClick={() => setDialog("pause")}
            >
              Tạm dừng DW1
            </Button>
          ) : null
        }
      />
      <Modal
        open={dialog !== null}
        title={dialog === "pause" ? "Tạm dừng DW1" : "Cho DW1 chạy lại"}
        okText={dialog === "pause" ? "Tạm dừng DW1" : "Cho DW1 chạy lại"}
        cancelText="Hủy"
        okButtonProps={{
          loading: pending !== null,
          danger: dialog === "pause",
        }}
        onOk={() => form.submit()}
        onCancel={() => {
          setDialog(null);
          setError(null);
        }}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          validateTrigger="onBlur"
          onFinish={submit}
        >
          <Typography.Paragraph>
            {dialog === "pause"
              ? `DW1 ngừng xử lý thư mới. ${RESUME_REASON} Người giữ quyền cho chạy lại sẽ nhận thông báo.`
              : "DW1 xử lý lại thư mới từ lúc này. Lý do được ghi vào nhật ký."}
          </Typography.Paragraph>
          <Form.Item
            name="reason"
            label="Lý do"
            rules={
              dialog === "resume"
                ? [
                    {
                      required: true,
                      message: "Lý do là bắt buộc",
                      validateTrigger: "onSubmit",
                    },
                  ]
                : []
            }
          >
            <Input.TextArea rows={3} maxLength={500} showCount />
          </Form.Item>
          <ActionError error={error} />
        </Form>
      </Modal>
    </div>
  );
}

interface Progress {
  /** The messages DW1 is reading now. */
  reading: Message[];
  queued: number;
  failed: number;
  done: number;
  total: number;
  /** When DW1 last decided a message. */
  lastAt: string | null;
}

/**
 * Where DW1 stands on the mailbox, read from the mailbox the API owns
 * (`InboxMessageView.processing`), again every few seconds while anything is
 * queued or running. Null for a viewer who may not read the mailbox.
 */
function useWorkerProgress(workerKnown: boolean): Progress | null {
  const { hasScope } = useAuth();
  const inbox = useResource<Message[]>(
    "sales/worker-progress",
    useCallback(() => salesApi().inbox(), []),
    // Only once DW1's own state is known: the bar is drawn from both.
    { enabled: workerKnown && hasScope(SCOPE.caseRead) },
  );
  const messages = inbox.data ?? [];
  const state = (m: Message) => m.processing?.status ?? null;
  const reading = messages.filter((m) => state(m) === "running");
  const queued = messages.filter((m) => state(m) === "queued").length;
  const busy = reading.length + queued > 0;
  const { reload } = inbox;
  useEffect(() => {
    if (!busy) return;
    const timer = window.setInterval(reload, PROGRESS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [busy, reload]);
  if (!inbox.data) return null;
  const times = messages
    .map((m) => m.disposition.processed_at)
    .filter((t): t is string => Boolean(t))
    .sort();
  return {
    reading,
    queued,
    failed: messages.filter((m) => state(m) === "failed").length,
    done: messages.filter((m) => m.disposition.kind !== "not_yet_processed")
      .length,
    total: messages.length,
    lastAt: times.at(-1) ?? null,
  };
}

/** What DW1 is doing now, in words (Đạt, 2026-10-21: never just "đang chạy"). */
function headline(progress: Progress | null): string {
  if (!progress) return "DW1 đang bật";
  if (progress.reading.length)
    return `DW1 đang đọc ${progress.reading
      .map((m) => `“${m.subject}”`)
      .join(", ")}`;
  if (progress.queued) return `DW1 sắp đọc ${progress.queued} thư đang chờ`;
  return "DW1 đã xử lý hết thư, đang chờ thư mới";
}

function progressLine(progress: Progress): string {
  return [
    `đã xử lý ${progress.done}/${progress.total} thư`,
    progress.reading.length && progress.queued
      ? `${progress.queued} thư đang chờ`
      : null,
    progress.failed ? `${progress.failed} thư chưa xử lý được` : null,
    progress.lastAt
      ? `thư gần nhất lúc ${formatDateTime(progress.lastAt, { zoneLabel: false })}`
      : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
