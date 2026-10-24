"use client";

import type { MouseEvent } from "react";
import Link from "next/link";
import { Card, Tag, theme, Typography } from "antd";
import type { AI_STATE } from "../_lib/labels";
import {
  inColumnOrder,
  type Lane,
  type LaneLayout,
} from "../_lib/process-graph";
import { AiStateTag } from "./tags";

/**
 * A lane's statuses as cards (2026-10-22, re-cut 2026-10-23). On a wide
 * screen they sit on the React Flow canvas as compact tiles
 * (`process-flow.tsx`, the only file allowed that library, 2026-10-24), below
 * `lg` in this list, in the same order (ui-quality §12). Each status is a
 * card in a real link to its settings (§3: a card that opens is wrapped in a
 * `Link`), so it opens in a new tab too, and Enter on it opens the drawer.
 * The list card and the tile's details say the same facts (`StatusFacts`).
 */

/** A status's AI state, once per state its model steps are in. */
export interface AiSummary {
  state: keyof typeof AI_STATE;
  /** How many of the status's model steps are in it. */
  count: number;
}

/** What a status card says, in words, and where it opens; the page composes it. */
export interface StatusCard {
  status: string;
  /** The item's id in the URL (`order.in_review`): the drawer it opens. */
  item: string;
  href: string;
  label: string;
  steps: { step_id: string; coverage: string }[];
  /** Whose turn a case in the status is. */
  holder: string;
  /** The same, as the server's code (`dw`, `sales`, …); null: nobody's, done. */
  holderKey: Lane["nodes"][number]["holder"];
  /** How many settings its steps read. */
  settings: number;
  ai: AiSummary[];
  /** Status labels it may move back to, comma separated; "" for none. */
  back: string;
  /** Status labels a final status is reached from; "" for none. */
  exits: string;
}

/** Opens in place on a plain click; a click asking for a new tab is the browser's. */
export function openHere(event: MouseEvent, open: () => void) {
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

/** One status card in its link: the phone list's. */
export function StatusLink({
  card,
  onOpen,
}: {
  card: StatusCard;
  onOpen: (item: string) => void;
}) {
  const { token } = theme.useToken();
  return (
    <Link
      href={card.href}
      scroll={false}
      data-node={card.item}
      data-status={card.status}
      className="block"
      style={{ color: token.colorText }}
      onClick={(event) => openHere(event, () => onOpen(card.item))}
    >
      <Card size="small" hoverable className="h-full">
        <div className="flex flex-col items-start gap-1">
          <Typography.Text strong>{card.label}</Typography.Text>
          <StepTags steps={card.steps} />
          <StatusFacts card={card} clamp />
        </div>
      </Card>
    </Link>
  );
}

/**
 * What a status card says beyond its name and steps: whose turn, how many
 * settings, its model steps' state, the ways back and where a final status is
 * reached from. `clamp`: two lines at most for the ways back and the exits.
 */
export function StatusFacts({
  card,
  clamp = false,
}: {
  card: StatusCard;
  clamp?: boolean;
}) {
  const long = clamp ? "line-clamp-2" : undefined;
  return (
    <>
      <span>Đến lượt: {card.holder}</span>
      <span>
        {card.settings ? `${card.settings} thiết lập` : "Không có thiết lập"}
      </span>
      {card.ai.length ? (
        <span className="flex flex-wrap gap-1">
          {card.ai.map((a) => (
            <AiStateTag key={a.state} state={a.state} count={a.count} />
          ))}
        </span>
      ) : null}
      {card.back ? (
        <span className={long}>Có thể quay lại: {card.back}</span>
      ) : null}
      {card.exits ? (
        <span className={long}>Có thể đóng từ: {card.exits}</span>
      ) : null}
    </>
  );
}

/**
 * Below `lg`: the same statuses, in the same order, one under another. A
 * plain list: the lane branches and loops, so nothing here is numbered or
 * drawn as the current one, and the ways back are written on each card.
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
