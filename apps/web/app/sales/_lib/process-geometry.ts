import type { LaneLayout, Move } from "./process-graph";

/**
 * Where each card, arrow and label of a lane sits on the wide-screen canvas
 * (`process-flow.tsx`), computed from `layoutLane`'s ranks and nothing else:
 * no status is named, so a status or move the API adds is placed too.
 *
 * Fixed after the browser look of 2026-10-24 (half the order lane fitted at
 * 1440, and arches crossed card labels so "Có cờ" read as leading to "PIC đã
 * tự kiểm"):
 *
 * - **Bands.** The rank columns wrap into bands of at most
 *   `MAX_BAND_COLUMNS`, read left to right, top to bottom like text, so a
 *   lane fits the width of a laptop at a readable zoom.
 * - **Gaps and trunks.** Cards never sit in the gap between two columns.
 *   Each card leaves on one vertical trunk at the near side of the gap to its
 *   right and is entered on one at the far side of the gap to its left; the
 *   middle of the gap holds the words of the moves between neighbours.
 * - **Channels.** A move that is not between neighbours runs on a lane of a
 *   channel between bands: forward under its band, back (dashed) over it.
 *   Lanes are given so no two moves of one channel share a line or their
 *   words, and a move's words slide along its own line away from the trunks
 *   of other moves that cross that lane.
 *
 * So no label covers a card or another label, by construction; the test
 * computes the boxes from this function for the served order and quote lanes.
 * Label sizes are estimated from their words at the theme's small font
 * (`estimateLabel`), conservatively; the canvas draws each label at the size
 * placed here.
 */

export const CARD_W = 184;
export const CARD_MIN_H = 136;
/** Columns per band: five fit 1440 px at a zoom near 1. */
export const MAX_BAND_COLUMNS = 5;
/** Between two columns of a band. */
const GAP = 136;
/** Before a band's first column and after its last: trunks only. */
const OUTER_GAP = 40;
/** Each side of a gap, kept for trunks. */
const STRIP = 24;
/** Between two trunks of one strip, and a trunk from its gap's edge. */
const TRUNK = 6;
const TRUNK_INSET = 8;
const ROW_GAP = 32;
/** Between a band and a channel, and inside a channel above and below. */
const CHANNEL_PAD = 12;
const LANE_GAP = 8;
/** Words of a move between neighbours: the middle of the gap. */
export const NEIGHBOUR_LABEL_W = GAP - 2 * STRIP - 4;
/** Words of a move on a channel lane. */
export const LANE_LABEL_W = 168;
const LABEL_GAP = 4;

// The theme's small text (fontSizeSM 12, lineHeightSM ≈ 1.67): an average
// Vietnamese character is about 6.5 px; 7.5 keeps the estimate on the safe
// side, so the drawn words fit the box placed for them.
const CHAR_W = 7.5;
const LINE_H = 20;
/** A guard tag: its border and padding around the same small text. */
const TAG_PAD_X = 16;
const TAG_EXTRA_H = 2;
const LABEL_PAD = 4;

export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface MoveWords {
  action: string;
  guards: string[];
}

export interface RoutedMove {
  id: string;
  move: Move;
  back: boolean;
  /** An orthogonal polyline, from the source card's right to the target's left. */
  points: [number, number][];
  label: Box;
}

export interface LaneGeometry {
  cards: Record<string, Box>;
  moves: RoutedMove[];
  width: number;
  height: number;
}

/** Lines a text takes when wrapped at `width`, word by word. */
function lines(text: string, width: number): number {
  const perLine = Math.max(1, Math.floor(width / CHAR_W));
  let count = 1;
  let used = 0;
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const size = word.length;
    if (used === 0) {
      count += Math.floor(Math.max(0, size - 1) / perLine);
      used = size % perLine || perLine;
    } else if (used + 1 + size <= perLine) used += 1 + size;
    else {
      count += 1 + Math.floor(Math.max(0, size - 1) / perLine);
      used = size % perLine || perLine;
    }
  }
  return count;
}

/** The box a move's words take at `width`: the action, then one tag a guard. */
export function estimateLabel(words: MoveWords, width: number): Box {
  const inner = width - 2 * LABEL_PAD;
  let h = 2 * LABEL_PAD + lines(words.action, inner) * LINE_H;
  for (const guard of words.guards)
    h += LABEL_GAP + lines(guard, inner - TAG_PAD_X) * LINE_H + TAG_EXTRA_H;
  return { x: 0, y: 0, w: width, h };
}

interface ChannelItem {
  routed: RoutedMove;
  /** The source's and the target's trunk. */
  from: number;
  to: number;
  /** Where each trunk leaves the channel: -1 through its top, 1 its bottom. */
  fromSide: -1 | 1;
  toSide: -1 | 1;
  lane: number;
  laneY: number;
}

export function laneGeometry(
  layout: LaneLayout,
  words: (move: Move) => MoveWords,
  heights: Record<string, number> = {},
): LaneGeometry {
  const columns = Math.max(1, layout.columns);
  const bands = Math.ceil(columns / MAX_BAND_COLUMNS);
  const perBand = Math.ceil(columns / bands);
  const place = Object.fromEntries(layout.nodes.map((n) => [n.status, n]));
  const bandOf = (status: string) =>
    Math.floor(place[status]!.column / perBand);
  const slotOf = (status: string) => place[status]!.column % perBand;
  const height = (status: string) =>
    Math.max(CARD_MIN_H, heights[status] ?? CARD_MIN_H);

  const columnX = (slot: number) => OUTER_GAP + slot * (CARD_W + GAP);
  /** The gap right of a slot: [start, end]. */
  const gapRight = (slot: number): [number, number] => {
    const start = columnX(slot) + CARD_W;
    return [start, start + (slot === perBand - 1 ? OUTER_GAP : GAP)];
  };
  const gapLeft = (slot: number): [number, number] =>
    slot === 0 ? [0, OUTER_GAP] : gapRight(slot - 1);
  const width = columnX(perBand - 1) + CARD_W + OUTER_GAP;
  // A card's trunks: by its row, so two cards of a column never share one.
  const outTrunk = (s: string) =>
    gapRight(slotOf(s))[0] + TRUNK_INSET + TRUNK * place[s]!.row;
  const inTrunk = (s: string) =>
    gapLeft(slotOf(s))[1] - TRUNK_INSET - TRUNK * place[s]!.row;

  // Rows of each band, in band-local y.
  const rowTops: number[][] = [];
  const rowHeights: number[][] = [];
  for (let band = 0; band < bands; band++) {
    const members = layout.nodes.filter((n) => bandOf(n.status) === band);
    const rows = Math.max(1, ...members.map((n) => n.row + 1));
    const tops: number[] = [];
    const sizes: number[] = [];
    let top = 0;
    for (let row = 0; row < rows; row++) {
      const size = Math.max(
        CARD_MIN_H,
        ...members.filter((n) => n.row === row).map((n) => height(n.status)),
      );
      tops.push(top);
      sizes.push(size);
      top += size + ROW_GAP;
    }
    rowTops.push(tops);
    rowHeights.push(sizes);
  }
  const localCenter = (s: string) =>
    rowTops[bandOf(s)]![place[s]!.row]! + height(s) / 2;

  const moves: { move: Move; back: boolean }[] = [
    ...layout.forward.map((move) => ({ move, back: false })),
    ...layout.backward.map((move) => ({ move, back: true })),
  ];
  const neighbours = ({ move, back }: { move: Move; back: boolean }) =>
    !back &&
    bandOf(move.from) === bandOf(move.to) &&
    slotOf(move.to) - slotOf(move.from) === 1;

  // Words between neighbours: stacked down the middle of their gap, each as
  // near its target's middle as the ones above it allow (band-local y).
  const neighbourLabels = new Map<Move, Box>();
  const bandFloor: number[] = rowTops.map(
    (tops, band) => tops.at(-1)! + rowHeights[band]!.at(-1)!,
  );
  const byGap = new Map<string, Move[]>();
  for (const m of moves.filter(neighbours)) {
    const key = `${bandOf(m.move.from)}:${slotOf(m.move.from)}`;
    byGap.set(key, [...(byGap.get(key) ?? []), m.move]);
  }
  for (const [key, inGap] of byGap) {
    const [band, slot] = key.split(":").map(Number) as [number, number];
    const left = gapRight(slot)[0] + STRIP + 2;
    let floor = 0;
    for (const move of [...inGap].sort(
      (a, b) => localCenter(a.to) - localCenter(b.to),
    )) {
      const size = estimateLabel(words(move), NEIGHBOUR_LABEL_W);
      const y = Math.max(localCenter(move.to) - size.h / 2, floor);
      neighbourLabels.set(move, { ...size, x: left, y });
      floor = y + size.h + LABEL_GAP;
    }
    bandFloor[band] = Math.max(bandFloor[band]!, floor - LABEL_GAP);
  }

  // Channel c sits above band c (c = bands: under the last band). A move
  // back runs over its band; any other move not between neighbours, under.
  const channels: ChannelItem[][] = Array.from({ length: bands + 1 }, () => []);
  for (const m of moves) {
    if (neighbours(m)) continue;
    const channel = m.back ? bandOf(m.move.from) : bandOf(m.move.from) + 1;
    const below = (s: string): -1 | 1 => (bandOf(s) < channel ? -1 : 1);
    channels[channel]!.push({
      routed: {
        id: `${m.move.from}->${m.move.to}`,
        move: m.move,
        back: m.back,
        points: [],
        label: estimateLabel(words(m.move), LANE_LABEL_W),
      },
      from: outTrunk(m.move.from),
      to: inTrunk(m.move.to),
      fromSide: below(m.move.from),
      toSide: below(m.move.to),
      lane: 0,
      laneY: 0,
    });
  }

  // Lanes: no two items of a lane share an x, by line or by words at its
  // middle; then the lanes stacked, each as tall as its tallest words.
  const span = (item: ChannelItem): [number, number] => {
    const middle = (item.from + item.to) / 2;
    return [
      Math.min(item.from, item.to, middle - item.routed.label.w / 2) - TRUNK,
      Math.max(item.from, item.to, middle + item.routed.label.w / 2) + TRUNK,
    ];
  };
  const channelHeights: number[] = [];
  for (const items of channels) {
    const taken: [number, number][][] = [];
    for (const item of [...items].sort(
      (a, b) => span(a)[1] - span(a)[0] - (span(b)[1] - span(b)[0]),
    )) {
      const [lo, hi] = span(item);
      let lane = taken.findIndex((ranges) =>
        ranges.every(([a, b]) => hi <= a || lo >= b),
      );
      if (lane < 0) lane = taken.push([]) - 1;
      taken[lane]!.push([lo, hi]);
      item.lane = lane;
    }
    // Lane 0 holds the shortest moves: it goes nearest the band most of
    // the channel's trunks leave towards, so fewer lines cross other words.
    const down = items.filter((i) => i.fromSide + i.toSide > 0).length;
    const order = taken.map((_, lane) => lane);
    if (down > items.length - down) order.reverse();
    let top = CHANNEL_PAD;
    for (const lane of order) {
      const tallest = Math.max(
        ...items.filter((i) => i.lane === lane).map((i) => i.routed.label.h),
      );
      for (const i of items) if (i.lane === lane) i.laneY = top + tallest / 2;
      top += tallest + LANE_GAP;
    }
    channelHeights.push(taken.length ? top - LANE_GAP + CHANNEL_PAD : 0);
  }

  // Absolute y: channel 0, band 0, channel 1, band 1, ...
  const channelTop: number[] = [];
  const bandTop: number[] = [];
  let y = 0;
  for (let band = 0; band <= bands; band++) {
    channelTop.push(y);
    y += channelHeights[band]!;
    if (band === bands) break;
    y += CHANNEL_PAD;
    bandTop.push(y);
    y += bandFloor[band]! + CHANNEL_PAD;
  }
  const totalHeight = y;

  const cards: Record<string, Box> = {};
  for (const n of layout.nodes)
    cards[n.status] = {
      x: columnX(slotOf(n.status)),
      y: bandTop[bandOf(n.status)]! + rowTops[bandOf(n.status)]![n.row]!,
      w: CARD_W,
      h: height(n.status),
    };
  const center = (s: string) => cards[s]!.y + cards[s]!.h / 2;
  const exit = (s: string): [number, number] => [
    cards[s]!.x + CARD_W,
    center(s),
  ];
  const entry = (s: string): [number, number] => [cards[s]!.x, center(s)];

  const routed: RoutedMove[] = [];
  for (const m of moves.filter(neighbours)) {
    const [sx, sy] = exit(m.move.from);
    const [tx, ty] = entry(m.move.to);
    const trunk = outTrunk(m.move.from);
    const label = neighbourLabels.get(m.move)!;
    routed.push({
      id: `${m.move.from}->${m.move.to}`,
      move: m.move,
      back: false,
      points:
        sy === ty
          ? [
              [sx, sy],
              [tx, ty],
            ]
          : [
              [sx, sy],
              [trunk, sy],
              [trunk, ty],
              [tx, ty],
            ],
      label: {
        ...label,
        y: bandTop[bandOf(m.move.from)]! + label.y,
      },
    });
  }

  channels.forEach((items, channel) => {
    const top = channelTop[channel]!;
    for (const item of items) item.laneY += top;
    const placed: ChannelItem[] = [];
    for (const item of items) {
      const { move } = item.routed;
      const [sx, sy] = exit(move.from);
      const [tx, ty] = entry(move.to);
      const lane = item.laneY;
      // The trunks of other items that cross this lane's words.
      const crossing = items
        .filter((o) => o !== item)
        .flatMap((o) =>
          (
            [
              [o.from, o.fromSide],
              [o.to, o.toSide],
            ] as const
          ).filter(([, side]) =>
            side < 0
              ? o.laneY > lane - item.routed.label.h / 2
              : o.laneY < lane + item.routed.label.h / 2,
          ),
        )
        .map(([x]) => x);
      const sameLane = placed
        .filter((o) => o.lane === item.lane)
        .map((o) => o.routed.label);
      const w = item.routed.label.w;
      const middle = Math.min(
        width - w / 2,
        Math.max(
          w / 2,
          slide(
            Math.min(item.from, item.to),
            Math.max(item.from, item.to),
            w,
            crossing,
            sameLane,
          ),
        ),
      );
      item.routed.label = {
        ...item.routed.label,
        x: middle - w / 2,
        y: lane - item.routed.label.h / 2,
      };
      item.routed.points = [
        [sx, sy],
        [item.from, sy],
        [item.from, lane],
        [item.to, lane],
        [item.to, ty],
        [tx, ty],
      ];
      routed.push(item.routed);
      placed.push(item);
    }
  });

  return { cards, moves: routed, width, height: totalHeight };
}

/**
 * Where on its own line, from `a` to `b`, a label `w` wide is centred: as
 * near the middle as it can be without covering a crossing trunk or another
 * label of its lane; at the middle when the line is shorter than the words or
 * nothing is free.
 */
function slide(
  a: number,
  b: number,
  w: number,
  crossing: number[],
  others: Box[],
): number {
  const middle = (a + b) / 2;
  const lo = a + w / 2;
  const hi = b - w / 2;
  if (lo > hi) return middle;
  const blocked: [number, number][] = [
    ...crossing.map((x): [number, number] => [x - w / 2 - 4, x + w / 2 + 4]),
    ...others.map((o): [number, number] => [
      o.x - w / 2 - LABEL_GAP,
      o.x + o.w + w / 2 + LABEL_GAP,
    ]),
  ];
  const free = (c: number) => blocked.every(([s, e]) => c <= s || c >= e);
  const candidates = [
    middle,
    ...blocked.flatMap(([s, e]) => [s, e]),
    lo,
    hi,
  ].filter((c) => c >= lo && c <= hi && free(c));
  if (!candidates.length) return middle;
  return candidates.reduce((best, c) =>
    Math.abs(c - middle) < Math.abs(best - middle) ? c : best,
  );
}
