"use client";

import { useCallback, useEffect, useState } from "react";
import { Alert, App, Button, Flex, Table, Typography } from "antd";
import { WarningOutlined } from "@ant-design/icons";
import type { StalledEvent } from "@dw/contracts";
import { PageHeader, RegionState } from "@dw/ui";
import { apiClient } from "../../../lib/session";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime } from "../../../lib/dates";
import { errorMessage as errorText } from "../../../lib/error-message";

/**
 * Background work that stopped (2026-10-29): an event the worker tried until
 * it gave up waits here, and the tenant's administrator runs it again once the
 * cause is fixed. The worker tells them by notice when one stops. Only the kind
 * of error is shown: its text can carry what the failing statement held.
 */
export default function BackgroundFailuresPage() {
  const { hasScope } = useAuth();

  if (!hasScope("platform.tenant.settings.write")) {
    return (
      <RegionState
        kind="forbidden"
        description="Cần quyền quản trị công ty để xem trang này."
      />
    );
  }
  return <StalledList />;
}

function StalledList() {
  const { message } = App.useApp();
  const [events, setEvents] = useState<StalledEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<string | null>(null);

  const load = useCallback(() => {
    apiClient()
      .listBackgroundFailures()
      .then(setEvents)
      .catch((e: unknown) => setError(errorText(e)));
  }, []);

  useEffect(load, [load]);

  const retry = async (event: StalledEvent) => {
    setRetrying(event.id);
    setError(null);
    try {
      await apiClient().retryBackgroundFailure(event.id);
      message.success(
        "Đã đưa việc này vào hàng đợi; worker sẽ chạy lại trong giây lát.",
      );
      load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setRetrying(null);
    }
  };

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        icon={<WarningOutlined />}
        title="Việc nền lỗi"
        subtitle="Việc chạy nền mà worker đã thử nhiều lần, cách nhau tăng dần, vẫn không xong, nên đã dừng để chờ người. Khắc phục nguyên nhân trước (ví dụ dịch vụ đọc tệp đang tắt), rồi bấm Chạy lại. Mỗi lần chạy lại đều ghi vào nhật ký kiểm toán."
      />
      <Flex vertical gap="middle">
        {error && <Alert type="error" showIcon title={error} />}
        <Table<StalledEvent>
          rowKey="id"
          loading={events === null}
          dataSource={events ?? []}
          pagination={false}
          scroll={{ x: "max-content" }}
          locale={{ emptyText: "Không có việc nền nào đang dừng." }}
          columns={[
            {
              title: "Việc nền",
              dataIndex: "event_type",
              render: (value: string) => (
                <Typography.Text code>{value}</Typography.Text>
              ),
            },
            {
              title: "Phát sinh lúc (giờ Việt Nam)",
              dataIndex: "occurred_at",
              render: (value: string) => formatDateTime(value),
            },
            { title: "Số lần thử", dataIndex: "attempts", align: "right" },
            { title: "Loại lỗi", dataIndex: "error_kind" },
            {
              title: "",
              key: "retry",
              fixed: "right",
              render: (_: unknown, event: StalledEvent) => (
                <Button
                  loading={retrying === event.id}
                  disabled={retrying !== null && retrying !== event.id}
                  onClick={() => void retry(event)}
                  aria-label={`Chạy lại ${event.event_type}`}
                >
                  Chạy lại
                </Button>
              ),
            },
          ]}
        />
      </Flex>
    </div>
  );
}
