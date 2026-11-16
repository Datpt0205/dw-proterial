"use client";

import Link from "next/link";
import { Flex, List, Typography } from "antd";
import { StatusTag } from "@dw/ui";
import {
  demonstrationChanges,
  scoreLine,
  securityLine,
  type Demonstration,
  type PromptVersion,
  type PromptsView,
} from "../_lib/prompts";

const UUID = /^[0-9a-f-]{36}$/i;

/**
 * A proposed prompt version beside the one in force (ticket 43): its replay
 * on the decided lines, then the decided lines it adds and drops, each with
 * the customer and the order it came from. The instructions are the
 * platform's prompt in both, so these lines are the whole change. Drawn on
 * `/sales/rules/prompts` and under the approval on `/approvals`, where the
 * head decides it.
 */
export function PromptChanges({
  view,
  version,
}: {
  view: PromptsView;
  version: PromptVersion;
}) {
  const changes = demonstrationChanges(
    view.demonstrations,
    version.demonstrations,
  );
  return (
    <Flex vertical gap="small">
      {version.replay ? (
        <Typography.Text>
          {scoreLine(version.replay)} · {securityLine(version.replay)}
        </Typography.Text>
      ) : null}
      <Typography.Text>
        So với bản đang dùng{" "}
        <Typography.Text code>{view.in_force}</Typography.Text>: lời hướng dẫn
        giữ nguyên ({view.prompt}), chỉ đổi các dòng mẫu.
      </Typography.Text>
      <Lines
        title={`Thêm ${changes.added.length} dòng mẫu`}
        tone="ok"
        tag="Thêm"
        lines={changes.added}
      />
      {changes.removed.length > 0 ? (
        <Lines
          title={`Bỏ ${changes.removed.length} dòng mẫu`}
          tone="err"
          tag="Bỏ"
          lines={changes.removed}
        />
      ) : null}
      {changes.kept.length > 0 ? (
        <Typography.Text>
          Giữ {changes.kept.length} dòng mẫu như bản đang dùng.
        </Typography.Text>
      ) : null}
    </Flex>
  );
}

function Lines({
  title,
  tone,
  tag,
  lines,
}: {
  title: string;
  tone?: "ok" | "err";
  tag?: string;
  lines: readonly Demonstration[];
}) {
  return (
    <List<Demonstration>
      size="small"
      header={<Typography.Text strong>{title}</Typography.Text>}
      dataSource={[...lines]}
      locale={{ emptyText: "Không có." }}
      renderItem={(d) => (
        <List.Item>
          <Flex vertical gap={2}>
            <span className="flex flex-wrap items-center gap-2">
              {tag && tone ? <StatusTag tone={tone}>{tag}</StatusTag> : null}
              <Typography.Text>{d.description}</Typography.Text>
              <span aria-hidden>→</span>
              <Typography.Text code>{d.prv_code}</Typography.Text>
            </span>
            <Source line={d} />
          </Flex>
        </List.Item>
      )}
    />
  );
}

/** Which decided line it came from: the customer, and the order to open. */
function Source({ line }: { line: Demonstration }) {
  if (!line.case_id && !line.customer_code) return null;
  return (
    <Typography.Text>
      Người đã quyết
      {line.customer_code ? ` · khách ${line.customer_code}` : ""}
      {line.case_id && UUID.test(line.case_id) ? (
        <>
          {" · "}
          <Link href={`/sales/orders/${line.case_id}`} target="_blank">
            Mở đơn
          </Link>
        </>
      ) : null}
    </Typography.Text>
  );
}

/** The decided lines a version shows, as they are: a version no longer waiting. */
export function PromptLines({ version }: { version: PromptVersion }) {
  return (
    <Lines
      title={`${version.demonstrations.length} dòng mẫu`}
      lines={version.demonstrations}
    />
  );
}
