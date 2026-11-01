"use client";

import Link from "next/link";
import { Button, Card, Empty, Table } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { PurchaseCase } from "@dw/api-client";
import { PageHeader } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { LoadMore } from "../../../components/load-more";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { useAuth } from "../../../lib/auth/auth-context";
import { useCachedPages } from "../../../lib/use-cached-pages";
import { casePage } from "../_lib/cases";
import { money } from "../_lib/format";
import { SCOPE } from "../_lib/scopes";
import { purchasingCrumbs, ScopeGate } from "../_components/frame";
import { CaseStatusTag } from "../_components/tags";

/**
 * Every purchase case, newest first, as the server pages it; a requester
 * sees only their own (the server narrows the query, not this page).
 */
export default function RequestsPage() {
  return (
    <ScopeGate scope={[SCOPE.read, SCOPE.readOwn]}>
      <Requests />
    </ScopeGate>
  );
}

function amountOf(c: PurchaseCase): string {
  if (c.selection) return money(c.selection.total, c.selection.currency);
  if (c.check?.amount) return money(c.check.amount, c.check.currency);
  return c.check ? "Chưa rõ" : "Chưa đối chiếu";
}

function Requests() {
  const { hasScope } = useAuth();
  const list = useCachedPages("purchasing/requests", casePage);
  const own = !hasScope(SCOPE.read);
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={purchasingCrumbs("Hồ sơ mua hàng")}
        title={own ? "Yêu cầu của tôi" : "Hồ sơ mua hàng"}
        subtitle={
          own
            ? "Các yêu cầu bạn đã viết, mới nhất trước."
            : "Mọi yêu cầu mua hàng DW2 đã nhận, mới nhất trước."
        }
        actions={
          hasScope(SCOPE.create) ? (
            <Link href="/purchasing/new">
              <Button type="primary" icon={<PlusOutlined aria-hidden />}>
                Tôi cần mua…
              </Button>
            </Link>
          ) : undefined
        }
      />
      <Card size="small">
        {list.error && !list.items.length ? (
          <LoadError error={list.error} onRetry={list.reload} />
        ) : (
          <Table<PurchaseCase>
            rowKey="case_id"
            size="small"
            sticky
            loading={list.loading}
            dataSource={list.items}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: list.loading ? (
                " "
              ) : (
                <Empty description="Chưa có yêu cầu mua hàng nào.">
                  {hasScope(SCOPE.create) ? (
                    <Link href="/purchasing/new">Viết yêu cầu đầu tiên</Link>
                  ) : null}
                </Empty>
              ),
            }}
            columns={[
              {
                title: "Số yêu cầu",
                key: "pr",
                render: (_, c) => (
                  <Link href={`/purchasing/requests/${c.case_id}`}>
                    {c.request.pr_no}
                  </Link>
                ),
              },
              {
                title: "Bộ phận",
                key: "d",
                render: (_, c) => c.request.department,
              },
              {
                title: "Người yêu cầu",
                key: "r",
                render: (_, c) => c.request.requester,
              },
              {
                title: "Trạng thái",
                key: "s",
                render: (_, c) => <CaseStatusTag status={c.status} />,
              },
              {
                title: "Số tiền",
                key: "a",
                align: "right",
                render: (_, c) => amountOf(c),
              },
              {
                title: `Nhận lúc (${TIME_ZONE_LABEL})`,
                key: "t",
                render: (_, c) =>
                  formatDateTime(c.received_at, { zoneLabel: false }),
              },
            ]}
            footer={() => (
              <LoadMore
                hasMore={list.hasMore}
                loading={list.loadingMore}
                onLoadMore={list.loadMore}
                shown={list.items.length}
                noun="yêu cầu"
              />
            )}
          />
        )}
      </Card>
    </div>
  );
}
