"use client";

import { useEffect, useState } from "react";
import { Alert, App, Button, Modal, Space, Typography } from "antd";
import {
  pushIsOn,
  pushSupport,
  registerWorker,
  renewPush,
  turnOff,
  turnOn,
} from "../lib/push";

/**
 * Registers the service worker and renews this device's push subscription
 * each time a signed-in person opens the app (Sales ticket 48). Draws
 * nothing.
 */
export function PushRenewal() {
  useEffect(() => {
    void registerWorker().then(() => renewPush());
  }, []);
  return null;
}

/**
 * "Thông báo trên điện thoại", from the account menu: on or off for this
 * device. On an iPhone outside the installed app it says, once and briefly,
 * how to install it, because iOS offers pushes only there.
 */
export function PushSettingsDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { message } = App.useApp();
  const [on, setOn] = useState<boolean | null>(null);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const support = pushSupport();

  useEffect(() => {
    if (!open) return;
    setProblem(null);
    void pushIsOn().then(setOn);
  }, [open]);

  const press = async () => {
    setPending(true);
    setProblem(null);
    try {
      if (on) {
        await turnOff();
        setOn(false);
        void message.success("Đã tắt thông báo trên thiết bị này");
        return;
      }
      const result = await turnOn();
      if (result === "on") {
        setOn(true);
        void message.success("Đã bật thông báo trên thiết bị này");
      } else if (result === "denied") {
        setProblem(
          "Trình duyệt đang chặn thông báo của DW. Mở cài đặt trang web để cho phép, rồi bật lại.",
        );
      } else {
        setProblem("Máy chủ DW chưa bật thông báo đẩy. Liên hệ quản trị.");
      }
    } catch {
      setProblem("Chưa bật được thông báo. Thử lại sau.");
    } finally {
      setPending(false);
    }
  };

  return (
    <Modal
      open={open}
      onCancel={onClose}
      title="Thông báo trên điện thoại"
      footer={<Button onClick={onClose}>Đóng</Button>}
    >
      <Space orientation="vertical" className="w-full">
        {support === "needs_install" ? (
          <Alert
            type="info"
            showIcon
            title="Trên iPhone: thêm DW vào Màn hình chính"
            description="Trong Safari, bấm Chia sẻ rồi “Thêm vào MH chính”. Mở DW từ biểu tượng đó và bật thông báo tại đây."
          />
        ) : support === "unsupported" ? (
          <Typography.Text>
            Trình duyệt này không nhận được thông báo đẩy.
          </Typography.Text>
        ) : (
          <>
            <Typography.Text role="status">
              {on === null
                ? " "
                : on
                  ? "Thiết bị này đang nhận thông báo khi có việc mới, sắp quá hạn hoặc quá hạn."
                  : "Thiết bị này chưa nhận thông báo."}
            </Typography.Text>
            <Button
              type={on ? "default" : "primary"}
              loading={pending}
              disabled={on === null}
              onClick={() => void press()}
            >
              {on ? "Tắt thông báo" : "Bật thông báo"}
            </Button>
          </>
        )}
        {problem ? <Alert type="error" showIcon title={problem} /> : null}
      </Space>
    </Modal>
  );
}
