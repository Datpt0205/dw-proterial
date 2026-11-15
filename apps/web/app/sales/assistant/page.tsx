"use client";

import { useCallback } from "react";
import Link from "next/link";
import { Badge, Card, Empty, Flex, List, Skeleton, Typography } from "antd";
import { PageHeader } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { useResource } from "../_lib/use-resource";
import {
  AssistantConversation,
  caseHref,
} from "../_components/assistant-conversation";
import { salesCrumbs } from "../_components/crumbs";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";

/** Questions to start from; a follow-up ("PO đó…") reads as the PO just asked. */
const EXAMPLES = [
  "Tôi còn việc gì?",
  "Có việc nào quá hạn không?",
  "PO NRV-PO-26-0457 tới đâu rồi?",
];

/** What the general conversation answers (ADR 0007, ticket 46), said before anyone asks. */
const CATALOG =
  "Hỏi việc đang chờ bạn, việc quá hạn, hoặc tìm một PO, một yêu cầu báo giá. Câu trả lời không có số tiền.";

/**
 * Hỏi đáp DW1 (dw_sales ADR 0007; the contract's DW01 criterion 6): the
 * person's one general conversation, and the cases they talked about most
 * recently (ticket 46). A case's own questions are asked on the case's page,
 * where its conversation is; a case named here is answered with a link to it.
 */
export default function AssistantPage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <Assistant />
    </ScopeGate>
  );
}

function Assistant() {
  const recent = useResource(
    "assistant-cases",
    useCallback(() => salesApi().assistantCases(), []),
  );

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title="Hỏi đáp DW1"
        breadcrumb={salesCrumbs("Hỏi đáp DW1")}
        subtitle={CATALOG}
        help="DW1 trả lời từ dữ liệu đang có trong hệ thống, trong phạm vi hồ sơ bạn được xem. Câu hỏi về một hồ sơ được hỏi ngay trên trang của hồ sơ đó."
      />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_300px]">
        <Card size="small" title="Trò chuyện chung">
          <AssistantConversation
            onCase={null}
            examples={EXAMPLES}
            onAnswered={recent.reload}
          />
        </Card>
        <Card size="small" title="Hồ sơ đã hỏi gần đây">
          {recent.error ? (
            <LoadError error={recent.error} onRetry={recent.reload} compact />
          ) : recent.loading ? (
            <Skeleton active paragraph={{ rows: 3 }} />
          ) : (
            <List
              size="small"
              dataSource={recent.data ?? []}
              locale={{
                emptyText: (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="Chưa hỏi hồ sơ nào. Mở một hồ sơ để hỏi về nó."
                  />
                ),
              }}
              renderItem={(c) => (
                <List.Item>
                  <Link href={caseHref(c.case)}>
                    <Flex vertical>
                      <Badge dot={c.unread} offset={[6, 0]}>
                        <Typography.Text strong={c.unread}>
                          {c.case.label}
                        </Typography.Text>
                      </Badge>
                      <Typography.Text type="secondary">
                        {c.unread ? "Có trả lời chưa xem · " : ""}
                        {formatDateTime(c.last_turn_at)}
                      </Typography.Text>
                    </Flex>
                  </Link>
                </List.Item>
              )}
            />
          )}
        </Card>
      </div>
    </div>
  );
}
