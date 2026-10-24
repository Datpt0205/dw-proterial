import { describe, expect, it } from "vitest";
import { EDGE_ACTION, EDGE_GUARD } from "../labels";
import { layoutLane, type Lane, type Move } from "../process-graph";
import {
  CARD_W,
  estimateLabel,
  laneGeometry,
  MAX_BAND_COLUMNS,
  type Box,
} from "../process-geometry";
import { PROCESS } from "./process-fixture";

/**
 * The canvas's placement (browser look, 2026-10-24): at 1440 the whole lane
 * fits at a readable zoom, and no move's words cover a card or another move's
 * words, for the lanes the API serves. Boxes come from the same function the
 * canvas draws from, with the same words.
 */
const LANES = PROCESS.lanes as Lane[];
const words = (move: Move) => ({
  action: EDGE_ACTION[move.action] ?? move.action,
  guards: move.guards.map((g) => EDGE_GUARD[g] ?? g),
});

const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** Card heights as React Flow measures them: some cards grow with content. */
const TALL: Record<string, number> = {
  in_review: 220,
  uploaded_to_bravo: 260,
  design_replied: 240,
  pending_approval: 200,
};

describe.each(LANES.map((lane) => [lane.kind, lane] as const))(
  "the %s lane on the canvas",
  (_, lane) => {
    for (const [name, heights] of [
      ["at the cards' least height", {}],
      ["with taller measured cards", TALL],
    ] as const) {
      it(`no label covers a card or another label (${name})`, () => {
        const layout = layoutLane(lane);
        const geometry = laneGeometry(layout, words, heights);
        const labels = geometry.moves.map((m) => [m.id, m.label] as const);
        const cards = Object.entries(geometry.cards);
        expect(labels.length).toBe(
          layout.forward.length + layout.backward.length,
        );
        for (const [i, [id, box]] of labels.entries()) {
          for (const [card, at] of cards)
            expect(overlap(box, at), `${id} over card ${card}`).toBe(false);
          for (const [other, at] of labels.slice(i + 1))
            expect(overlap(box, at), `${id} over ${other}`).toBe(false);
        }
        // No two cards overlap either, and nothing leaves the canvas.
        for (const [i, [a, at]] of cards.entries())
          for (const [b, bt] of cards.slice(i + 1))
            expect(overlap(at, bt), `${a} over ${b}`).toBe(false);
        for (const [id, box] of [...labels, ...cards]) {
          expect(box.x, id).toBeGreaterThanOrEqual(0);
          expect(box.x + box.w, id).toBeLessThanOrEqual(geometry.width);
          expect(box.y, id).toBeGreaterThanOrEqual(0);
          expect(box.y + box.h, id).toBeLessThanOrEqual(geometry.height);
        }
      });
    }

    it("fits 1440 px at a zoom of at least 0.85, wrapping the columns into bands", () => {
      const layout = layoutLane(lane);
      const geometry = laneGeometry(layout, words);
      // The page's content beside the shell's gutters at 1440.
      expect(1360 / geometry.width).toBeGreaterThanOrEqual(0.85);
      const bands = new Set(
        Object.values(geometry.cards).map((card) => card.y),
      );
      expect(layout.columns).toBeGreaterThan(MAX_BAND_COLUMNS);
      expect(bands.size).toBeGreaterThan(1);
    });

    it("draws each move as horizontal and vertical runs, from a card's right to another's left, never through a card", () => {
      const geometry = laneGeometry(layoutLane(lane), words, TALL);
      for (const m of geometry.moves) {
        const from = geometry.cards[m.move.from]!;
        const to = geometry.cards[m.move.to]!;
        expect(m.points[0]![0], m.id).toBe(from.x + from.w);
        expect(m.points.at(-1)![0], m.id).toBe(to.x);
        for (let i = 1; i < m.points.length; i++) {
          const [x1, y1] = m.points[i - 1]!;
          const [x2, y2] = m.points[i]!;
          expect(x1 === x2 || y1 === y2, `${m.id} segment ${i}`).toBe(true);
          // A segment never runs across a card (it may touch its ends' edges).
          const seg: Box = {
            x: Math.min(x1, x2) + 0.5,
            y: Math.min(y1, y2) + 0.5,
            w: Math.max(0, Math.abs(x2 - x1) - 1),
            h: Math.max(0, Math.abs(y2 - y1) - 1),
          };
          for (const [card, at] of Object.entries(geometry.cards))
            expect(
              overlap({ ...seg, w: seg.w || 0.1, h: seg.h || 0.1 }, at),
              `${m.id} segment ${i} through ${card}`,
            ).toBe(false);
        }
      }
    });
  },
);

describe("where the order lane's moves run", () => {
  const [orders] = LANES as [Lane];
  const geometry = laneGeometry(layoutLane(orders), words);
  const move = (id: string) => geometry.moves.find((m) => m.id === id)!;

  it("runs a move back over its band, a move skipping columns under it", () => {
    const back = move("in_review->checked");
    const band = geometry.cards.in_review!.y;
    expect(back.back).toBe(true);
    expect(Math.min(...back.points.map(([, y]) => y))).toBeLessThan(band);
    const skip = move("cross_checked->change_review");
    const card = geometry.cards.cross_checked!;
    expect(Math.max(...skip.points.map(([, y]) => y))).toBeGreaterThan(
      card.y + card.h,
    );
  });

  it("keeps the words of 'Chờ PIC tự kiểm' → 'PIC đã tự kiểm' in the gap before its card, beside nothing else's", () => {
    const prepare = move("in_review->prepared");
    const card = geometry.cards.prepared!;
    expect(prepare.label.x + prepare.label.w).toBeLessThanOrEqual(card.x);
    expect(prepare.label.x).toBeGreaterThanOrEqual(
      geometry.cards.in_review!.x + CARD_W,
    );
    // Its words sit level with its own card, not with the card above it.
    const middle = prepare.label.y + prepare.label.h / 2;
    expect(middle).toBeGreaterThan(card.y);
    expect(middle).toBeLessThan(card.y + card.h);
  });
});

describe("a label's estimated size", () => {
  it("grows a line for words that do not fit, and a tag per guard", () => {
    const one = estimateLabel({ action: "Kiểm chéo", guards: [] }, 84);
    const two = estimateLabel(
      { action: "Yêu cầu khách sửa PO và gửi lại", guards: [] },
      84,
    );
    const tagged = estimateLabel(
      { action: "Kiểm chéo", guards: ["Không còn cờ chặn"] },
      84,
    );
    expect(two.h).toBeGreaterThan(one.h);
    expect(tagged.h).toBeGreaterThan(one.h);
  });
});
