"use client";

import {
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
} from "react";
import Link from "next/link";
import { Card, Tag, theme, Typography } from "antd";
import {
  inColumnOrder,
  type LaneLayout,
  type PlacedStatus,
} from "../_lib/process-graph";

/**
 * A lane of the DW1 process, drawn from `process-graph.ts`'s placement: on a
 * wide screen a grid of statuses with the forward moves as arrows, below
 * `lg` a list in the same order (ui-quality §12). Each status is a card in a
 * real link to its settings (§3: a card that opens is wrapped in a `Link`),
 * so it opens in a new tab too; the arrows are decoration (`aria-hidden`),
 * because every move is also written in words on the card or in its drawer.
 */

/** What a status card says, in words, and where it opens; the page composes it. */
export interface StatusCard {
  status: string;
  /** The item's id in the URL (`order.in_review`): the drawer it opens. */
  item: string;
  href: string;
  label: string;
  /** One line each. */
  facts: ReactNode;
}

// The grid's geometry. A row is as tall as its tallest card; the arrows are
// drawn from where the cards are measured to be (from these numbers until
// they are, and where nothing is laid out at all).
const WIDTH = 168;
const MIN_HEIGHT = 120;
const GAP_X = 40;
const GAP_Y = 16;
/** Between two long arrows' tracks under the grid. */
const TRACK = 10;

const left = (column: number) => column * (WIDTH + GAP_X);

interface Box {
  top: number;
  height: number;
}

/** Each card's top and height in the grid, by status; null until laid out. */
function useBoxes(layout: LaneLayout) {
  const grid = useRef<HTMLDivElement>(null);
  const [boxes, setBoxes] = useState<Record<string, Box> | null>(null);
  useLayoutEffect(() => {
    const element = grid.current;
    if (!element) return;
    const measure = () => {
      const next: Record<string, Box> = {};
      for (const card of element.querySelectorAll<HTMLElement>("[data-status]"))
        next[card.dataset.status!] = {
          top: card.offsetTop,
          height: card.offsetHeight,
        };
      const laidOut = Object.values(next).some((b) => b.height > 0);
      setBoxes((before) =>
        !laidOut
          ? null
          : before && JSON.stringify(before) === JSON.stringify(next)
            ? before
            : next,
      );
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [layout]);
  return { grid, boxes };
}

/** Opens in place on a plain click; a click asking for a new tab is the browser's. */
function openHere(event: MouseEvent, open: () => void) {
  if (
    event.button !== 0 ||
    event.metaKey ||
    event.ctrlKey ||
    event.shiftKey ||
    event.altKey
  )
    return;
  event.preventDefault();
  open();
}

function StatusLink({
  card,
  onOpen,
  place,
}: {
  card: StatusCard;
  onOpen: (item: string) => void;
  /** Its cell in the grid; absent in the list. */
  place?: PlacedStatus;
}) {
  const { token } = theme.useToken();
  return (
    <Link
      href={card.href}
      scroll={false}
      data-node={card.item}
      data-status={card.status}
      className="block"
      style={{
        color: token.colorText,
        ...(place
          ? { gridColumn: place.column + 1, gridRow: place.row + 1 }
          : {}),
      }}
      onClick={(event) => openHere(event, () => onOpen(card.item))}
    >
      <Card size="small" hoverable className="h-full">
        <div className="flex flex-col items-start gap-1">
          <Typography.Text strong>{card.label}</Typography.Text>
          {card.facts}
        </div>
      </Card>
    </Link>
  );
}

export function ProcessMap({
  layout,
  cards,
  onOpen,
}: {
  layout: LaneLayout;
  cards: Record<string, StatusCard>;
  onOpen: (item: string) => void;
}) {
  const { token } = theme.useToken();
  const marker = useId();
  const { grid, boxes } = useBoxes(layout);
  const scroller = useRef<HTMLDivElement>(null);
  const [cut, setCut] = useState(false);
  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element) return;
    const check = () => setCut(element.scrollWidth > element.clientWidth + 1);
    check();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(check);
    observer.observe(element);
    return () => observer.disconnect();
  }, [layout]);

  const place = Object.fromEntries(layout.nodes.map((n) => [n.status, n]));
  const width = layout.columns * WIDTH + (layout.columns - 1) * GAP_X;
  const box = (status: string): Box =>
    boxes?.[status] ?? {
      top: place[status]!.row * (MIN_HEIGHT + GAP_Y),
      height: MIN_HEIGHT,
    };
  const height = Math.max(
    0,
    ...layout.nodes.map((n) => box(n.status).top + box(n.status).height),
  );
  // An arrow that skips a column would cross a card: it runs under the grid.
  const long = layout.forward.filter(
    (m) => place[m.to]!.column - place[m.from]!.column > 1,
  );
  const below = long.length ? GAP_Y + long.length * TRACK : 0;
  const path = (from: string, to: string) => {
    const a = box(from);
    const b = box(to);
    const x1 = left(place[from]!.column) + WIDTH;
    const y1 = a.top + a.height / 2;
    const x2 = left(place[to]!.column);
    const y2 = b.top + b.height / 2;
    const track = long.findIndex((m) => m.from === from && m.to === to);
    if (track < 0) {
      const bend = GAP_X / 2;
      return `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
    }
    const y = height + GAP_Y + track * TRACK;
    const out = x1 + GAP_X / 3;
    const back = x2 - GAP_X / 3;
    return `M ${x1} ${y1} L ${out} ${y1} L ${out} ${y} L ${back} ${y} L ${back} ${y2} L ${x2} ${y2}`;
  };
  return (
    <div className="space-y-2">
      {cut ? (
        <Typography.Paragraph className="mb-0!">
          Quy trình rộng hơn khung: kéo ngang trong khung để xem hết{" "}
          {layout.nodes.length} trạng thái.
        </Typography.Paragraph>
      ) : null}
      <div ref={scroller} className="overflow-x-auto pb-2">
        <div
          className="relative"
          style={{ width, minHeight: height + below, paddingBottom: below }}
        >
          <svg
            aria-hidden
            focusable="false"
            className="pointer-events-none absolute inset-0"
            width={width}
            height={height + below}
          >
            <defs>
              <marker
                id={marker}
                viewBox="0 0 10 10"
                refX="9"
                refY="5"
                markerWidth="7"
                markerHeight="7"
                orient="auto-start-reverse"
              >
                <path
                  d="M 0 0 L 10 5 L 0 10 z"
                  fill={token.colorTextTertiary}
                />
              </marker>
            </defs>
            {layout.forward.map((m) => (
              <path
                key={`${m.from}->${m.to}`}
                data-move={`${m.from}->${m.to}`}
                d={path(m.from, m.to)}
                fill="none"
                stroke={token.colorTextTertiary}
                strokeWidth={1.5}
                markerEnd={`url(#${marker})`}
              />
            ))}
          </svg>
          <div
            ref={grid}
            className="relative grid"
            style={{
              gridTemplateColumns: `repeat(${layout.columns}, ${WIDTH}px)`,
              gridAutoRows: `minmax(${MIN_HEIGHT}px, auto)`,
              columnGap: GAP_X,
              rowGap: GAP_Y,
            }}
          >
            {/* In drawing order, so Tab follows what is drawn. */}
            {inColumnOrder(layout).map((n) => (
              <StatusLink
                key={n.status}
                card={cards[n.status]!}
                onOpen={onOpen}
                place={n}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Below `lg`: the same statuses, in the same order, one under another. A
 * plain list: the lane branches and loops, so nothing here is numbered or
 * drawn as the current one.
 */
export function ProcessList({
  layout,
  cards,
  onOpen,
}: {
  layout: LaneLayout;
  cards: Record<string, StatusCard>;
  onOpen: (item: string) => void;
}) {
  return (
    <ul className="m-0 flex list-none flex-col gap-2 p-0">
      {inColumnOrder(layout).map((n) => (
        <li key={n.status}>
          <StatusLink card={cards[n.status]!} onOpen={onOpen} />
        </li>
      ))}
    </ul>
  );
}

/** The step ids a status stands for, each with how far DW1 takes it. */
export function StepTags({
  steps,
}: {
  steps: { step_id: string; coverage: string }[];
}) {
  if (!steps.length) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {steps.map((s) => (
        <Tag key={s.step_id} className="me-0 whitespace-normal">
          {s.step_id} · {s.coverage}
        </Tag>
      ))}
    </span>
  );
}
