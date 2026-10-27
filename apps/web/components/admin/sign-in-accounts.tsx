"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  App,
  Button,
  Flex,
  Form,
  Input,
  Modal,
  Select,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  KeyOutlined,
  LockOutlined,
  PlusOutlined,
  UnlockOutlined,
} from "@ant-design/icons";
import { ApiError } from "@dw/api-client";
import { apiClient } from "../../lib/session";
import { errorMessage } from "../../lib/error-message";
import { useIdempotencyKeys } from "../../lib/idempotency";

/**
 * Sign-in accounts an Org Admin creates for people the company has no
 * directory for (`member_accounts.py`): "Thêm người" makes the person, their
 * role and their account at once; each row resets the password or locks the
 * sign-in. The server decides every refusal; this only draws them, disabled
 * with the reason in words (ui-quality §5).
 *
 * A temporary password is shown once, in a dialog that a click outside does
 * not close, and is never put in a toast, the URL or the console.
 */

/** Which sign-in accounts this tenant created: email → may sign in. */
export type AccountsState =
  | { kind: "loading" }
  | { kind: "ready"; enabledByEmail: ReadonlyMap<string, boolean> }
  | { kind: "unavailable"; reason: string };

export function useLoginAccounts(): {
  state: AccountsState;
  reload: () => Promise<void>;
} {
  const [state, setState] = useState<AccountsState>({ kind: "loading" });
  const reload = useCallback(async () => {
    try {
      const accounts = await apiClient().listLoginAccounts();
      setState({
        kind: "ready",
        enabledByEmail: new Map(
          accounts.map((a) => [a.email.toLowerCase(), a.enabled]),
        ),
      });
    } catch (e) {
      // `login_accounts_not_configured` words its own reason (the server's
      // sentence); anything else is a failure to read, said as such.
      const configured =
        !(e instanceof ApiError) ||
        e.body.details?.reason_code !== "login_accounts_not_configured";
      setState({
        kind: "unavailable",
        reason: configured
          ? `Không đọc được tài khoản đăng nhập: ${errorMessage(e)}`
          : errorMessage(e),
      });
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { state, reload };
}

/** What the password dialog shows; `password` null on a replayed request. */
export interface ShownPassword {
  name: string;
  email: string;
  password: string | null;
}

export function TemporaryPasswordDialog({
  shown,
  onClose,
}: {
  shown: ShownPassword | null;
  onClose: () => void;
}) {
  return (
    <Modal
      open={shown !== null}
      title={shown ? `Mật khẩu tạm của ${shown.name}` : undefined}
      maskClosable={false}
      onCancel={onClose}
      footer={
        <Button type="primary" onClick={onClose}>
          Đã ghi lại
        </Button>
      }
    >
      {shown?.password ? (
        <Flex vertical gap="small">
          <Typography.Paragraph
            copyable={{ text: shown.password }}
            className="!mb-0"
          >
            <Typography.Text code>{shown.password}</Typography.Text>
          </Typography.Paragraph>
          <Typography.Text>
            Mật khẩu chỉ hiện một lần. Đưa trực tiếp cho người dùng, đừng gửi
            vào nhóm chat chung. Lần đầu đăng nhập bằng email{" "}
            <Typography.Text strong>{shown.email}</Typography.Text>, họ phải đặt
            mật khẩu mới.
          </Typography.Text>
        </Flex>
      ) : (
        <Typography.Text>
          Yêu cầu này đã chạy ở lần bấm trước và máy chủ không lưu lại mật khẩu
          tạm. Nếu chưa ghi lại, bấm “Đặt lại mật khẩu” ở dòng của người này.
        </Typography.Text>
      )}
    </Modal>
  );
}

interface NewPerson {
  displayName: string;
  email: string;
  role: string;
}

export function AddPersonButton({
  workspaceId,
  roles,
  disabledReason,
  onCreated,
}: {
  workspaceId: string | null;
  roles: { value: string; label: string }[];
  disabledReason: string | null;
  onCreated: (shown: ShownPassword) => void;
}) {
  const keys = useIdempotencyKeys();
  const [form] = Form.useForm<NewPerson>();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(values: NewPerson) {
    if (!workspaceId) return;
    setBusy(true);
    setError(null);
    const input = {
      displayName: values.displayName.trim(),
      email: values.email.trim(),
      workspaceId,
      roleKeys: [values.role],
    };
    try {
      const created = await apiClient().createMemberAccount(
        input,
        keys.keyFor("create-account", input),
      );
      keys.settle("create-account");
      setOpen(false);
      form.resetFields();
      onCreated({
        name: created.display_name,
        email: created.email ?? input.email,
        password: created.temporary_password,
      });
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const button = (
    <Button
      icon={<PlusOutlined aria-hidden />}
      disabled={disabledReason !== null || !workspaceId}
      onClick={() => setOpen(true)}
    >
      Thêm người
    </Button>
  );
  return (
    <>
      {disabledReason ? (
        <Flex vertical gap={4}>
          <Tooltip title={disabledReason}>
            <span className="inline-block">{button}</span>
          </Tooltip>
          <Typography.Text>{disabledReason}</Typography.Text>
        </Flex>
      ) : (
        button
      )}
      <Modal
        open={open}
        title="Thêm người và tạo tài khoản đăng nhập"
        okText="Tạo tài khoản"
        cancelText="Hủy"
        confirmLoading={busy}
        onOk={() => form.submit()}
        onCancel={() => {
          setOpen(false);
          setError(null);
        }}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          validateTrigger="onBlur"
          scrollToFirstError={{ focus: true }}
          initialValues={{ role: roles[0]?.value }}
          onFinish={(values) => void create(values)}
        >
          <Form.Item
            name="displayName"
            label="Họ và tên"
            rules={[
              { required: true, message: "Nhập họ và tên." },
              { min: 4, max: 120, message: "Họ và tên dài 4 đến 120 ký tự." },
            ]}
          >
            <Input autoComplete="off" placeholder="Ví dụ: Phạm Thị Lan" />
          </Form.Item>
          <Form.Item
            name="email"
            label="Email công ty"
            rules={[
              { required: true, message: "Nhập email." },
              { type: "email", message: "Email chưa đúng dạng." },
            ]}
          >
            <Input autoComplete="off" placeholder="lan.pham@congty.vn" />
          </Form.Item>
          <Form.Item
            name="role"
            label="Vai"
            rules={[{ required: true, message: "Chọn vai." }]}
          >
            <Select options={roles} />
          </Form.Item>
        </Form>
        <Typography.Text>
          DW tạo tài khoản đăng nhập kèm mật khẩu tạm, chỉ hiện một lần sau khi
          tạo. Bộ quyền bổ sung gán sau ở dòng của người này.
        </Typography.Text>
        {error && (
          <Alert type="error" showIcon title={error} className="!mt-3" />
        )}
      </Modal>
    </>
  );
}

/** The two sign-in actions of one member's row. */
export function SignInActions({
  userId,
  name,
  email,
  accounts,
  blockedReason,
  lockBlockedReason,
  onChanged,
  onPassword,
  onError,
}: {
  userId: string;
  name: string;
  email: string | null;
  accounts: AccountsState;
  /** Why neither action is this admin's to take (an administrator's row).
   * The row writes it out; these actions carry it in their tooltips. */
  blockedReason: string | null;
  /** Why locking is not (the admin's own row). */
  lockBlockedReason: string | null;
  onChanged: () => Promise<void>;
  onPassword: (shown: ShownPassword) => void;
  onError: (message: string) => void;
}) {
  const { message, modal } = App.useApp();
  const keys = useIdempotencyKeys();
  const [busy, setBusy] = useState<"reset" | "lock" | null>(null);

  const enabled =
    accounts.kind === "ready" && email
      ? accounts.enabledByEmail.get(email.toLowerCase())
      : undefined;
  const reason =
    accounts.kind === "loading"
      ? "Đang đọc tài khoản đăng nhập…"
      : accounts.kind === "unavailable"
        ? accounts.reason
        : enabled === undefined
          ? "Tài khoản đăng nhập của người này không do DW tạo (ví dụ đăng nhập qua AD), nên đổi ở nơi quản lý tài khoản đó."
          : blockedReason;
  const lockReason = reason ?? (enabled ? lockBlockedReason : null);
  // Written out under the buttons: a reason of these actions' own, not the
  // row's (`blockedReason`), which the row writes once.
  const written = [reason, lockReason].find(
    (why) => why !== null && why !== blockedReason,
  );

  function reset() {
    modal.confirm({
      title: `Đặt lại mật khẩu của ${name}?`,
      content:
        "Mật khẩu hiện tại ngừng dùng được ngay. Người này đăng nhập bằng mật khẩu tạm mới và phải đổi ở lần đầu.",
      okText: "Đặt lại",
      cancelText: "Hủy",
      autoFocusButton: "cancel",
      onOk: async () => {
        setBusy("reset");
        try {
          const result = await apiClient().resetMemberPassword(
            userId,
            keys.keyFor("reset", userId),
          );
          keys.settle("reset");
          onPassword({
            name,
            email: email ?? "",
            password: result.temporary_password,
          });
        } catch (e) {
          onError(errorMessage(e));
        } finally {
          setBusy(null);
        }
      },
    });
  }

  async function setSignIn(next: boolean) {
    setBusy("lock");
    const action = `sign-in/${String(next)}`;
    try {
      await apiClient().setMemberSignIn(
        userId,
        next,
        keys.keyFor(action, { userId, next }),
      );
      keys.settle(action);
      message.success(
        next
          ? `Đã mở khóa đăng nhập của ${name}.`
          : `Đã khóa đăng nhập của ${name}.`,
      );
      await onChanged();
    } catch (e) {
      onError(errorMessage(e));
    } finally {
      setBusy(null);
    }
  }

  function lock() {
    modal.confirm({
      title: `Khóa đăng nhập của ${name}?`,
      content:
        "Người này bị đăng xuất ngay và không đăng nhập được cho tới khi mở khóa. Vai và dữ liệu vẫn giữ nguyên.",
      okText: "Khóa đăng nhập",
      okButtonProps: { danger: true },
      cancelText: "Hủy",
      autoFocusButton: "cancel",
      onOk: () => setSignIn(false),
    });
  }

  const withReason = (why: string | null, node: ReactNode) =>
    why ? (
      <Tooltip title={why}>
        <span className="inline-block">{node}</span>
      </Tooltip>
    ) : (
      node
    );

  return (
    <Flex align="center" gap="small" wrap>
      {enabled === false && <Tag>Đã khóa đăng nhập</Tag>}
      {withReason(
        reason,
        <Button
          size="small"
          icon={<KeyOutlined aria-hidden />}
          loading={busy === "reset"}
          disabled={reason !== null}
          onClick={reset}
        >
          Đặt lại mật khẩu
        </Button>,
      )}
      {withReason(
        lockReason,
        enabled === false ? (
          <Button
            size="small"
            icon={<UnlockOutlined aria-hidden />}
            loading={busy === "lock"}
            disabled={lockReason !== null}
            onClick={() => void setSignIn(true)}
          >
            Mở khóa đăng nhập
          </Button>
        ) : (
          <Button
            size="small"
            danger
            icon={<LockOutlined aria-hidden />}
            loading={busy === "lock"}
            disabled={lockReason !== null}
            onClick={lock}
          >
            Khóa đăng nhập
          </Button>
        ),
      )}
      {/* A disabled button takes no tap and no focus: the reason is also
          written out, or a phone never shows it (2026-10-27). */}
      {written ? <Typography.Text>{written}</Typography.Text> : null}
    </Flex>
  );
}
