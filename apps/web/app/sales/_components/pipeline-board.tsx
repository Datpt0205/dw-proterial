"use client";

import { useCallback, useMemo } from "react";
import Link from "next/link";
import {
  Card,
  Flex,
  Input,
  Segmented,
  Skeleton,
  theme,
  Typography,
} from "antd";
import { RobotOutlined, UserOutlined } from "@ant-design/icons";
import type { SalesSchemas } from "@dw/api-client";
import { RegionState, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import {
  formatAge,
  formatDate,
  formatDateTime,
  TIME_ZONE_LABEL,
} from "../../../lib/dates";
import { matches } from "../../../lib/search";
import { useNow } from "../../../lib/use-now";
import { salesApi } from "../_lib/api";
import { useCustomerName } from "../_lib/customers";
import {
  ACTION,
  label,
  ORDER_STATE,
  QUOTE_STATE,
  TIME_BUCKET,
} from "../_lib/labels";
import { usePeople } from "../_lib/people";
import { useResource } from "../_lib/use-resource";
import { useListView } from "../_lib/use-status-filter";

type Board = SalesSchemas["PipelineView"];
type Column = SalesSchemas["PipelineColumn"];
type CaseCard = SalesSchemas["PipelineCard"];
type Kind = Column["kind"];

const LANES: { kind: Kind; title: string; procedure: string }[] = [
  { kind: "order", title: "Đơn hàng", procedure: "WIV-03-012" },
  { kind: "quote", title: "Báo giá", procedure: "WIV-03-023" },
];
const VIEWS = ["all", "mine"] as const;
const SORTS = ["age"] as const;
/** A column's width: a card's, or a header's when the column is empty. */
const WIDE = 228;
const NARROW = 132;

const stateLabel = (kind: Kind, status: string) =>
  label(kind === "order" ? ORDER_STATE : QUOTE_STATE, status);

const caseHref = (card: CaseCard) =>
  `/sales/${card.kind === "order" ? "orders" : "quotes"}/${card.case_id}`;

/**
 * The pipeline: every case of the workspace as a card in its status's column,
 * the columns in the order a case moves (the API's), a lane per procedure.
 *
 * What differs per person is read, not decided here: each card's
 * `my_action` is the viewer's next step on it from their own work list, so
 * the same board highlights the cross-checks for a checker and the approvals
 * for an approver, and "Việc của tôi" keeps only those. The step's own page
 * still decides whether the press is allowed.
 */
export function PipelineBoard() {
  const board = useResource<Board>(
    "sales/pipeline",
    useCallback(() => salesApi().pipeline(), []),
  );
  const view = useListView(VIEWS, "all", SORTS, "age");
  const customer = useCustomerName();
  const data = board.data;

  const shown = useMemo(() => {
    const cards = data?.cards ?? [];
    return cards.filter(
      (c) =>
        (view.tab === "all" || c.my_action !== null) &&
        matches(view.query, [
          c.reference,
          c.customer_code,
          customer(c.customer_code),
        ]),
    );
  }, [data, view.tab, view.query, customer]);
  const mine = (data?.cards ?? []).filter((c) => c.my_action !== null).length;

  if (board.loading && !data)
    return <Skeleton active paragraph={{ rows: 6 }} />;
  if (board.error && !data)
    return <LoadError error={board.error} onRetry={board.reload} />;
  if (!data) return null;

  return (
    <div className="space-y-3">
      <Flex wrap gap={8} align="center" justify="space-between">
        <Segmented
          aria-label="Hồ sơ hiển thị"
          value={view.tab}
          onChange={(next) => view.setTab(next as (typeof VIEWS)[number])}
          options={[
            { value: "all", label: `Tất cả (${data.cards.length})` },
            { value: "mine", label: `Việc của tôi (${mine})` },
          ]}
        />
        <Input.Search
          allowClear
          aria-label="Tìm theo số PO, RFQ hoặc khách"
          placeholder="Tìm số PO, RFQ, khách"
          defaultValue={view.query}
          onSearch={view.setQuery}
          className="w-full sm:w-72"
        />
      </Flex>
      {view.tab === "mine" && mine === 0 && (
        <RegionState
          kind="empty"
          compact
          title="Không có hồ sơ nào đang chờ bạn"
          description="Hồ sơ nào đến lượt bạn sẽ hiện ở đây và được tô sáng trong Tất cả."
        />
      )}
      {LANES.map((lane) => (
        <Lane
          key={lane.kind}
          title={lane.title}
          procedure={lane.procedure}
          columns={data.columns.filter((c) => c.kind === lane.kind)}
          cards={shown.filter((c) => c.kind === lane.kind)}
        />
      ))}
    </div>
  );
}

function Lane({
  title,
  procedure,
  columns,
  cards,
}: {
  title: string;
  procedure: string;
  columns: Column[];
  cards: CaseCard[];
}) {
  const open = columns.reduce((n, c) => n + (c.holder ? c.cases : 0), 0);
  return (
    <section aria-label={title}>
      <Flex gap={8} align="baseline" className="mb-1.5">
        <Typography.Title level={5} className="!m-0">
          {title}
        </Typography.Title>
        <Typography.Text type="secondary">
          {procedure} · {open} hồ sơ đang mở
        </Typography.Text>
      </Flex>
      <div className="overflow-x-auto pb-2">
        <div className="flex gap-2">
          {columns.map((column) => (
            <ColumnView
              key={column.status}
              column={column}
              cards={cards.filter((c) => c.status === column.status)}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

function ColumnView({ column, cards }: { column: Column; cards: CaseCard[] }) {
  const { token } = theme.useToken();
  const name = stateLabel(column.kind, column.status);
  const width = cards.length ? WIDE : NARROW;
  const small = { fontSize: token.fontSizeSM };
  return (
    <div
      role="group"
      aria-label={`${name}: ${column.cases} hồ sơ`}
      className="flex shrink-0 flex-col gap-1.5 p-1.5"
      style={{
        width,
        background: token.colorFillTertiary,
        borderRadius: token.borderRadiusLG,
      }}
    >
      <div className="px-1">
        <Flex justify="space-between" gap={4} align="baseline">
          <Typography.Text strong>{name}</Typography.Text>
          <Typography.Text type="secondary" style={small}>
            {column.cases}
          </Typography.Text>
        </Flex>
        <Typography.Text type="secondary" className="block" style={small}>
          {column.holder ? label(TIME_BUCKET, column.holder) : "Đã xong"}
          {column.steps.length ? ` · ${column.steps.join(", ")}` : ""}
        </Typography.Text>
      </div>
      {cards.map((card) => (
        <CaseCardView key={card.case_id} card={card} />
      ))}
      {column.hidden > 0 && (
        <Typography.Text type="secondary" className="px-1" style={small}>
          và {column.hidden} hồ sơ xong trước đó
        </Typography.Text>
      )}
    </div>
  );
}

function CaseCardView({ card }: { card: CaseCard }) {
  const { token } = theme.useToken();
  const now = useNow();
  const customer = useCustomerName();
  const person = usePeople();
  const holder = card.assigned_to ? person(card.assigned_to) : "Chưa giao";
  const isMine = card.my_action !== null;
  const small = { fontSize: token.fontSizeSM };
  return (
    <Card
      size="small"
      styles={{ body: { padding: 8 } }}
      style={
        isMine
          ? {
              borderColor: token.colorPrimary,
              boxShadow: `inset 3px 0 0 ${token.colorPrimary}`,
            }
          : undefined
      }
    >
      <Flex vertical gap={3}>
        <Link
          href={caseHref(card)}
          style={{ fontWeight: token.fontWeightStrong }}
        >
          {card.kind === "order"
            ? `PO ${card.reference}`
            : `RFQ ${card.reference}`}
        </Link>
        <Typography.Text style={small}>
          {customer(card.customer_code) || card.customer_code}
        </Typography.Text>
        <Typography.Text type="secondary" style={small}>
          {card.assigned_to ? (
            <UserOutlined aria-hidden />
          ) : (
            <RobotOutlined aria-hidden />
          )}{" "}
          {holder}
        </Typography.Text>
        <Typography.Text type="secondary" style={small}>
          Ở bước này {formatAge(card.status_since, now)}, từ{" "}
          {formatDateTime(card.status_since, { zoneLabel: false })}
        </Typography.Text>
        <Flex wrap gap={4}>
          {isMine && (
            <StatusTag tone="pri">
              Việc của bạn: {label(ACTION, card.my_action)}
            </StatusTag>
          )}
          {card.blocking_findings > 0 && (
            <StatusTag tone="err">{card.blocking_findings} cờ chặn</StatusTag>
          )}
          {card.open_findings > card.blocking_findings && (
            <StatusTag tone="warn">
              {card.open_findings - card.blocking_findings} cờ cần xem
            </StatusTag>
          )}
          {card.awaits_cross_check && card.status === "uploaded_to_bravo" && (
            <StatusTag tone="gold">Chờ kiểm chéo</StatusTag>
          )}
          {card.overdue ? (
            <StatusTag tone="err" tip={TIME_ZONE_LABEL}>
              Quá hạn {formatDate(card.due)}
            </StatusTag>
          ) : card.due ? (
            <StatusTag tone="gray">Hạn {formatDate(card.due)}</StatusTag>
          ) : null}
        </Flex>
      </Flex>
    </Card>
  );
}
