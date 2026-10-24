import { describe, expect, it } from "vitest";
import { EDGE_ACTION, EDGE_GUARD } from "../labels";
import { layoutLane, type Lane, type Move } from "../process-graph";
import {
  CARD_W,
  estimateLabel,
  laneGeometry,
  pathOf,
  pointsOf,
  type Box,
  type LaneGeometry,
} from "../process-geometry";
import { PROCESS } from "./process-fixture";

/**
 * The canvas's placement (re-cut 2026-10-24 for a calm, n8n-like canvas):
 * the main path in one row, every other status below it, and, for the lanes
 * the API serves, with or without the ways back: no label covers a tile or
 * another label, and no line crosses a tile or another move's words. Boxes
 * and lines come from the same function the canvas draws from, with the same
 * words.
 */
const LANES = PROCESS.lanes as Lane[];
const words = (move: Move) => ({
  action: EDGE_ACTION[move.action] ?? move.action,
  guards: move.guards.map((g) => EDGE_GUARD[g] ?? g),
});

const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
/** Strictly inside, a pixel in from each edge: touching an edge is meeting. */
const inside = ([px, py]: [number, number], b: Box) =>
  px > b.x + 1 && px < b.x + b.w - 1 && py > b.y + 1 && py < b.y + b.h - 1;

/**
 * Tile heights as the browser measured them at 1440 (2026-10-24): a tile
 * with an AI line, or a name on two lines, is taller than the least.
 */
const TILES: Record<string, number> = Object.fromEntries(
  LANES.flatMap((lane) => lane.nodes.map((n) => [n.status, 90])),
);
Object.assign(TILES, {
  received: 122,
  checked: 122,
  uploaded_to_bravo: 122,
  ycbg_recorded: 111,
  spec_discussion: 111,
});

/** Tiles well past their measured height. */
const TALL: Record<string, number> = {
  in_review: 220,
  uploaded_to_bravo: 260,
  design_replied: 240,
  pending_approval: 200,
  correction_requested: 180,
};

/** Every way a placement can be unreadable, as a list of what collides. */
function collisions(geometry: LaneGeometry): string[] {
  const found: string[] = [];
  const labels = geometry.moves.flatMap((m) =>
    m.label ? [[m.id, m.label] as const] : [],
  );
  const cards = Object.entries(geometry.cards);
  for (const [i, [id, box]] of labels.entries()) {
    for (const [card, at] of cards)
      if (overlap(box, at)) found.push(`${id} words over ${card}`);
    for (const [other, at] of labels.slice(i + 1))
      if (overlap(box, at)) found.push(`${id} words over ${other}'s`);
  }
  for (const [i, [a, at]] of cards.entries())
    for (const [b, bt] of cards.slice(i + 1))
      if (overlap(at, bt)) found.push(`${a} over ${b}`);
  for (const [id, box] of [...labels, ...cards])
    if (
      box.x < 0 ||
      box.y < 0 ||
      box.x + box.w > geometry.width ||
      box.y + box.h > geometry.height
    )
      found.push(`${id} off the canvas`);
  for (const m of geometry.moves) {
    const points = pointsOf(m.curve);
    for (const [card, at] of cards)
      if (points.some((p) => inside(p, at)))
        found.push(`${m.id} through ${card}`);
    // Another move's words, except those its own bus carries.
    for (const other of geometry.moves) {
      if (other === m || !other.label) continue;
      if (
        m.kind === "exit" &&
        other.kind === "exit" &&
        other.move.to === m.move.to
      )
        continue;
      if (points.some((p) => inside(p, other.label!)))
        found.push(`${m.id} through ${other.id}'s words`);
    }
  }
  return found;
}

describe.each(LANES.map((lane) => [lane.kind, lane] as const))(
  "the %s lane on the canvas",
  (_, lane) => {
    for (const showBack of [false, true])
      for (const [name, heights] of [
        ["at the tiles' least height", {}],
        ["at the tiles' measured heights", TILES],
        ["with taller tiles", TALL],
      ] as const)
        it(`keeps every label and line clear (${showBack ? "ways back on" : "default"}, ${name})`, () => {
          const geometry = laneGeometry(
            layoutLane(lane),
            words,
            heights,
            showBack,
          );
          expect(collisions(geometry)).toEqual([]);
        });

    it("puts the main path in one row, left to right, and every other status below it", () => {
      const layout = layoutLane(lane);
      const geometry = laneGeometry(layout, words, TILES);
      const row = layout.main.map((s) => geometry.cards[s]!);
      const middle = (b: Box) => b.y + b.h / 2;
      for (const [i, card] of row.entries()) {
        expect(middle(card)).toBe(middle(row[0]!));
        if (i) expect(card.x).toBeGreaterThan(row[i - 1]!.x + CARD_W);
      }
      const rowBottom = Math.max(...row.map((b) => b.y + b.h));
      for (const n of layout.nodes)
        if (!layout.main.includes(n.status)) {
          expect(geometry.rows[n.status], n.status).toBe(1);
          expect(geometry.cards[n.status]!.y, n.status).toBeGreaterThan(
            rowBottom,
          );
        }
    });

    it("draws the forward moves by default, and the ways back and exits only when asked", () => {
      const layout = layoutLane(lane);
      const plain = laneGeometry(layout, words);
      expect(plain.moves.map((m) => m.kind)).toEqual(
        layout.forward.map(() => "forward"),
      );
      expect(plain.moves.every((m) => m.label)).toBe(true);
      const all = laneGeometry(layout, words, {}, true);
      expect(all.moves.length).toBe(
        layout.forward.length + layout.backward.length + layout.exits.length,
      );
      // The exits into one final status share a bus: its words once per
      // action, at its end.
      const exits = all.moves.filter((m) => m.kind === "exit");
      expect(exits.length).toBeGreaterThan(1);
      expect(exits.filter((m) => m.label).length).toBe(
        new Set(exits.map((m) => `${m.move.to}:${m.move.action}`)).size,
      );
      // Ways back arch over the row; the row's own neighbours stay straight.
      const rowTop = Math.min(...layout.main.map((s) => all.cards[s]!.y));
      for (const m of all.moves)
        if (
          m.kind === "back" &&
          all.rows[m.move.from] === 0 &&
          all.rows[m.move.to] === 0
        )
          expect(m.label!.y + m.label!.h, m.id).toBeLessThan(rowTop);
    });
  },
);

describe("where the order lane's moves run", () => {
  const [orders] = LANES as [Lane];
  const layout = layoutLane(orders);
  const plain = laneGeometry(layout, words, TILES);
  const all = laneGeometry(layout, words, TILES, true);
  const move = (g: LaneGeometry, id: string) =>
    g.moves.find((m) => m.id === id)!;

  it("draws a move between neighbours of the row as one straight line, its words in the gap", () => {
    const prepare = move(plain, "in_review->prepared");
    expect(prepare.curve.segments.length).toBe(1);
    expect(prepare.curve.start[1]).toBe(prepare.curve.segments[0]![2][1]);
    expect(prepare.label!.x).toBeGreaterThan(plain.cards.in_review!.x + CARD_W);
    expect(prepare.label!.x + prepare.label!.w).toBeLessThan(
      plain.cards.prepared!.x,
    );
  });

  it("hangs a detour under where it starts, and the final status reached by exits past its last source", () => {
    expect(plain.cards.correction_requested!.x).toBe(plain.cards.in_review!.x);
    // Reviewing a change starts from three statuses of the row: under the
    // middle one.
    expect(plain.cards.change_review!.x).toBe(plain.cards.cross_checked!.x);
    expect(plain.cards.closed!.x).toBe(plain.cards.uploaded_to_bravo!.x);
  });

  it("arches a skip over the row, solid, and a way back over it, dashed and only when asked", () => {
    const skip = move(plain, "uploaded_to_bravo->confirmed");
    expect(skip.kind).toBe("forward");
    expect(skip.label!.y + skip.label!.h).toBeLessThan(
      plain.cards.cross_checked!.y,
    );
    expect(plain.moves.some((m) => m.id === "in_review->checked")).toBe(false);
    const back = move(all, "in_review->checked");
    expect(back.kind).toBe("back");
    // The longer way back arches above the shorter one it spans, and meets
    // their shared tile outside it, so the two never cross.
    const longer = move(all, "prepared->checked");
    expect(longer.label!.y).toBeLessThan(back.label!.y);
    const foot = (m: typeof back) => m.curve.segments.at(-1)![2][0];
    expect(foot(longer)).toBeLessThan(foot(back));
  });
});

describe("a label's estimated size", () => {
  it("grows a line for words that do not fit, and makes room for the lock", () => {
    const one = estimateLabel({ action: "Kiểm chéo", guards: [] }, 108);
    const two = estimateLabel(
      { action: "Yêu cầu khách sửa PO và gửi lại", guards: [] },
      108,
    );
    const locked = estimateLabel(
      {
        action: "Kiểm chéo",
        guards: ["Cần duyệt", "Người làm không tự duyệt"],
      },
      108,
    );
    expect(two.h).toBeGreaterThan(one.h);
    expect(two.w).toBe(108);
    expect(locked.w).toBeGreaterThan(one.w);
    // Guards add one lock, never a line each.
    expect(locked.h).toBe(
      estimateLabel({ action: "Kiểm chéo", guards: ["Cần duyệt"] }, 108).h,
    );
  });
});

describe("a line's path", () => {
  it("is the curve's own Béziers, from its start", () => {
    expect(
      pathOf({
        start: [0, 5],
        segments: [
          [
            [30, 5],
            [60, 5],
            [90, 5],
          ],
        ],
      }),
    ).toBe("M 0 5 C 30 5 60 5 90 5");
  });
});
