"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BellOutlined, CheckOutlined } from "@ant-design/icons";
import { Badge, Button, Empty, List, Popover, Typography } from "antd";
import type { AppNotification, Inbox } from "@dw/contracts";
import { formatDateTime } from "../lib/dates";
import { apiClient } from "../lib/session";

// How often the badge checks for something new while the app is open.
const POLL_MS = 60_000;

/** An app-relative path only; the database already refuses anything else,
 * and this refuses it again before navigating. */
function internalPath(link: string | null): string | null {
  return link && link.startsWith("/") && !link.startsWith("//") ? link : null;
}

/** The bell in the navbar: the unread count, and the latest notifications. */
export function NotificationBell() {
  const router = useRouter();
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback((signal?: AbortSignal) => {
    apiClient()
      .listNotifications(signal)
      .then(setInbox)
      .catch(() => {
        // A failed poll leaves the last inbox shown; the next one retries.
      });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    const timer = window.setInterval(() => load(), POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [load]);

  const follow = async (item: AppNotification) => {
    setOpen(false);
    if (item.read_at === null) {
      await apiClient()
        .markNotificationRead(item.id)
        .catch(() => undefined);
      load();
    }
    const path = internalPath(item.link);
    if (path) router.push(path);
  };

  const readAll = async () => {
    await apiClient()
      .markAllNotificationsRead()
      .catch(() => undefined);
    load();
  };

  const unread = inbox?.unread ?? 0;
  const items = inbox?.items ?? [];

  return (
    <Popover
      open={open}
      onOpenChange={setOpen}
      trigger="click"
      placement="bottomRight"
      arrow={false}
      title={
        <div className="flex items-center justify-between gap-3">
          <span>Thông báo</span>
          {unread > 0 ? (
            <Button
              type="link"
              size="small"
              icon={<CheckOutlined aria-hidden />}
              onClick={() => void readAll()}
            >
              Đánh dấu đã đọc
            </Button>
          ) : null}
        </div>
      }
      content={
        <div className="max-h-96 w-80 max-w-[85vw] overflow-y-auto">
          {items.length === 0 ? (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="Không có thông báo mới"
            />
          ) : (
            <List
              dataSource={items}
              rowKey="id"
              renderItem={(item) => (
                <List.Item className="!px-0">
                  <Button
                    type="text"
                    block
                    className="h-auto whitespace-normal py-2 text-start"
                    onClick={() => void follow(item)}
                  >
                    <span className="flex w-full flex-col items-start gap-0.5">
                      <Typography.Text strong={item.read_at === null}>
                        {item.title}
                      </Typography.Text>
                      {item.body ? (
                        <Typography.Text type="secondary">
                          {item.body}
                        </Typography.Text>
                      ) : null}
                      <Typography.Text type="secondary">
                        {formatDateTime(item.created_at)}
                      </Typography.Text>
                    </span>
                  </Button>
                </List.Item>
              )}
            />
          )}
        </div>
      }
    >
      <Button
        type="text"
        shape="circle"
        aria-label={unread ? `Thông báo, ${unread} chưa đọc` : "Thông báo"}
        icon={
          <Badge count={unread} size="small" overflowCount={99}>
            <BellOutlined aria-hidden />
          </Badge>
        }
      />
    </Popover>
  );
}
