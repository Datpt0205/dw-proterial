"use client";

import {
  createContext,
  useCallback,
  useContext,
  useState,
  type ReactNode,
} from "react";
import { Alert, Button, Form, Input, Modal, Space, Typography } from "antd";
import {
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
} as const;

interface SalesFrame {
  /** The overview: DW1's paused state and the WIV steps (one owner: the API). */
  overview: Resource<Overview>;
  paused: boolean;
}

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
  const worker = overview.data?.worker;
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

  return (
    <div className="mb-4">
      {worker.paused ? (
        <Alert
          type="warning"
          showIcon
          icon={<PauseCircleOutlined aria-hidden />}
          role="status"
          title="DW1 đang tạm dừng"
          description={
            <>
              {who ? `${who} tạm dừng` : "Đã tạm dừng"}
              {when ? ` lúc ${when}` : ""}.
              {worker.reason ? ` Lý do: ${worker.reason}.` : ""} DW1 không xử lý
              thư mới cho tới khi chạy lại; các bước của Sales vẫn làm được.
            </>
          }
          action={
            hasScope(SCOPE.pause) || hasScope(SCOPE.resume) ? (
              <GuardedButton
                icon={<PlayCircleOutlined aria-hidden />}
                reason={hasScope(SCOPE.resume) ? null : RESUME_REASON}
                onClick={() => setDialog("resume")}
              >
                Tiếp tục DW1
              </GuardedButton>
            ) : null
          }
        />
      ) : (
        <Space wrap className="w-full justify-between" role="status">
          <Typography.Text>
            <RobotOutlined aria-hidden className="me-1" />
            DW1 đang chạy
            {when
              ? ` · thay đổi lần cuối ${when}${who ? ` bởi ${who}` : ""}`
              : ""}
          </Typography.Text>
          {hasScope(SCOPE.pause) ? (
            <Button
              icon={<PauseCircleOutlined aria-hidden />}
              onClick={() => setDialog("pause")}
            >
              Tạm dừng DW1
            </Button>
          ) : null}
        </Space>
      )}
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
