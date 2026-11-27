"use client";

import { Card, Descriptions, Skeleton, Space, Tag, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { InfoTip } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { BRAVO_TARGET } from "../_lib/labels";
import { GuardedButton } from "./guarded-button";

export type BravoTarget = keyof typeof BRAVO_TARGET;

const COLOR: Record<BravoTarget, string> = { uat: "blue", production: "red" };

export function isBravoTarget(value: unknown): value is BravoTarget {
  return typeof value === "string" && value in BRAVO_TARGET;
}

/**
 * Which Bravo a write reads and writes (ticket 85): "Bravo UAT" in blue,
 * "Bravo thật" in red, on every screen that writes.
 */
export function BravoTargetTag({ target }: { target: BravoTarget }) {
  return (
    <Tag color={COLOR[target]} className="m-0!">
      {BRAVO_TARGET[target]}
    </Tag>
  );
}

export const NO_RULES_SCOPE =
  "Bạn không có quyền đề xuất quy tắc (cần quyền đề xuất quy tắc Sales).";
export const TARGET_UNREAD =
  "Chưa đọc được Bravo đang dùng: tải lại trước khi đổi.";

/** Whether the gateway holds the logins of one Bravo, in words. */
function configured(has: boolean): string {
  return has
    ? "Đã có tài khoản"
    : "Chưa có tài khoản: mọi lần đọc và ghi bị từ chối";
}

/**
 * The target switch on the rules page (ticket 85): which Bravo DW1 reads and
 * writes now, and the gateway's own answer whether it holds the logins of
 * each. Switching is a version of "DW1 tự ghi vào Bravo", proposed and
 * decided like every rule; a version naming Bravo thật needs the UAT run
 * that proved the gateway. Nothing here decides: the server refuses. Until
 * the page has read which Bravo is in use, the switch waits (ticket 85
 * review: a switch proposed blind).
 */
export function BravoTargetCard({
  targets,
  loading = false,
  error = null,
  onRetry,
  mayPropose,
  onSwitch,
}: {
  targets: SalesSchemas["BravoTargetsView"] | null;
  loading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  mayPropose: boolean;
  onSwitch: () => void;
}) {
  const unread = error != null || targets === null;
  return (
    <Card
      size="small"
      title="Bravo DW1 đọc và ghi"
      extra={
        <InfoTip label="Đổi Bravo">
          Đổi Bravo là một phiên bản của quy tắc “DW1 tự ghi vào Bravo”, đề xuất
          và duyệt như mọi phiên bản. Chọn Bravo thật phải ghi lần chạy trên UAT
          đã ghi đúng từ đầu đến cuối. Sau khi đổi, đề xuất đọc từ Bravo cũ bị
          từ chối khi ghi: cần đề xuất lại.
        </InfoTip>
      }
    >
      <Space orientation="vertical" className="w-full">
        {error != null ? (
          <LoadError error={error} onRetry={onRetry} compact />
        ) : loading || targets === null ? (
          <Skeleton active title={false} paragraph={{ rows: 2 }} />
        ) : targets.connected && targets.current ? (
          <Space size={4}>
            <Typography.Text>Đang dùng:</Typography.Text>
            <BravoTargetTag target={targets.current} />
          </Space>
        ) : (
          <Typography.Text role="note">
            Chưa hỏi được gateway Bravo: DW1 chưa đọc, chưa ghi Bravo nào.
          </Typography.Text>
        )}
        {error == null && targets?.connected ? (
          <Descriptions
            size="small"
            column={1}
            items={[
              {
                key: "uat",
                label: BRAVO_TARGET.uat,
                children: configured(targets.uat),
              },
              {
                key: "production",
                label: BRAVO_TARGET.production,
                children: configured(targets.production),
              },
            ]}
          />
        ) : null}
        <GuardedButton
          reason={!mayPropose ? NO_RULES_SCOPE : unread ? TARGET_UNREAD : null}
          onClick={onSwitch}
          aria-label="Đề xuất đổi Bravo DW1 đọc và ghi"
        >
          Đổi Bravo…
        </GuardedButton>
      </Space>
    </Card>
  );
}
