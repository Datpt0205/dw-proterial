import type { LaneLayout, Move } from "./process-graph";

/**
 * Where each tile, line and label of a lane sits on the wide-screen canvas
 * (`process-flow.tsx`), computed from `layoutLane` and nothing else: no
 * status is named, so a status or move the API adds is placed too.
 *
 * Re-cut 2026-10-24 for a calm canvas like n8n's (Đạt: the bands, channels
 * and guard tags of the first cut read as busy):
 *
 * - **One row.** The main path (`layoutLane`'s `main`) runs left to right in
 *   one row, never wrapped; the canvas pans where it is wider than the
 *   screen. A move between neighbours of the row is a straight line through
 *   the gap, its words in the middle.
 * - **Below it,** every other status, at the mean column of the row's
 *   statuses that move on to it (a detour sits under where it starts), or
 *   one column past the last status that reaches it (a final status reached
 *   only by exits); a taken column moves it right. Columns line up, so the
 *   gaps between them stay free in both rows. A move from the row down to
 *   one runs from the bottom of its tile to the top of the other, in the
 *   corridor between the rows.
 * - **Over it,** as arches, the moves between statuses of the row that are
 *   not neighbours: a forward one solid, a way back dashed. Arches whose
 *   spans or words meet are stacked, the longer above, so none crosses
 *   another's words.
 * - **Ways back and exits** are drawn only when asked (`showBack`): a way
 *   back from the row below rises through the corridor, and the exits into
 *   a final status run down the gap after their tile onto a rail under the
 *   rows, one bus per final status, its words once per action at the end.
 *
 * Every line is a chain of cubic Béziers (`Curve`), drawn as such and
 * sampled by the test, which checks for the served order and quote lanes
 * that no label covers a tile or another label and no line crosses a tile
 * or another move's words. Label sizes are estimated from their words at the
 * theme's small font (`estimateLabel`), conservatively, in the pill the
 * canvas draws them in (`PILL_PAD`, with the lock of a guarded move); the
 * canvas draws each pill inside the box placed here.
 */

export const CARD_W = 168;
/**
 * Below the shortest tile as measured (90 px at 1440, 2026-10-24), so a
 * measured height always wins and every line meets its tile where it is
 * drawn.
 */
export const CARD_MIN_H = 88;
/** Between two columns. */
const GAP = 160;
const PITCH = CARD_W + GAP;
/** Left of the first column and right of the last. */
const OUTER = 40;
/** How far into the gap after its tile a line to the rail runs down. */
const INSET = 10;
/** A label in a gap keeps this clear of a line run down beside it. */
const CLEAR = 6;
/** Words between neighbours of the row, in the gap. */
export const LABEL_MAX_W = GAP - 2 * (INSET + CLEAR);
/** Words on an arch, between the rows or on the rail, which have the room. */
export const WIDE_LABEL_MAX_W = 168;
const LABEL_GAP = 6;
/** The lowest arch's words, over the row's tallest tile. */
const ARCH_BASE = 16;
const TOP_PAD = 12;
const CORRIDOR_PAD = 8;
const CORRIDOR_MIN = 56;
const RAIL_PAD = 16;
const BOTTOM_PAD = 12;
const TRUNK = 6;
/** The outermost lines meeting a tile's top or bottom, in from its corners. */
const PORT_MARGIN = 16;
/** How far a pill may slide off its line's crossing, as parts of its width. */
const SLIDES = [0, -0.1, 0.1, -0.2, 0.2, -0.3, 0.3, -0.36, 0.36, -0.42, 0.42];
/** Where along its arch a pill may sit, the top first. */
const ARCH_SPOTS = [0.5, 0.42, 0.58, 0.34, 0.66, 0.26, 0.74];
/** The radius of the rail's bends. */
const CORNER = 10;

// The theme's small text (fontSizeSM 12, lineHeightSM ≈ 1.67): an average
// Vietnamese character measured about 5.5 px at 1440 (2026-10-24); 7 keeps
// the estimate on the safe side, so the drawn words fit the box placed for
// them.
const CHAR_W = 7;
const LINE_H = 20;
/** A move's words sit in a pill: this padding inside a 1 px border. */
export const PILL_PAD = { x: 6, y: 2 } as const;
const PILL_BORDER = 1;
/** A guarded move's lock: a small antd button after its words. */
export const LOCK = { size: 24, gap: 4 } as const;

export type Point = [number, number];
/** A line: from `start`, cubic Béziers, each [control, control, end]. */
export interface Curve {
  start: Point;
  segments: [Point, Point, Point][];
}

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

/** Forward, back to an earlier status, or out into a final one. */
export type MoveKind = "forward" | "back" | "exit";

export interface RoutedMove {
  id: string;
  move: Move;
  kind: MoveKind;
  /**
   * How it runs: between neighbours of the row, arched over it, down to or
   * up from the row below, or on the rail. `next` and `rail` leave a tile's
   * right side and enter one's left; the others meet tops and bottoms.
   */
  route: Route;
  curve: Curve;
  /** Its words; null on an exit whose bus carries them on another move. */
  label: Box | null;
}

export interface LaneGeometry {
  cards: Record<string, Box>;
  /** 0: the main path's row; 1: below it. */
  rows: Record<string, 0 | 1>;
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

/**
 * The box a move's pill takes: its action on as few lines as `maxWidth`
 * allows, then the lock when the move has guards.
 */
export function estimateLabel(words: MoveWords, maxWidth: number): Box {
  const lock = words.guards.length ? LOCK.size + LOCK.gap : 0;
  const chrome = 2 * (PILL_PAD.x + PILL_BORDER);
  const w = Math.min(
    maxWidth,
    Math.ceil(words.action.length * CHAR_W + lock + chrome),
  );
  const text = lines(words.action, w - lock - chrome) * LINE_H;
  const h = 2 * (PILL_PAD.y + PILL_BORDER) + Math.max(text, lock && LOCK.size);
  return { x: 0, y: 0, w, h };
}

const lerp = (a: Point, b: Point, t: number): Point => [
  a[0] + (b[0] - a[0]) * t,
  a[1] + (b[1] - a[1]) * t,
];

/** A straight run as a Bézier segment. */
const straight = (a: Point, b: Point): [Point, Point, Point] => [
  lerp(a, b, 1 / 3),
  lerp(a, b, 2 / 3),
  b,
];

/** From `a` to `b`, leaving and arriving upright: never above or below both. */
function uprightCurve(a: Point, b: Point): Curve {
  const mid = (a[1] + b[1]) / 2;
  return {
    start: a,
    segments: [[[a[0], mid], [b[0], mid], b]],
  };
}

/**
 * Horizontal and vertical runs with each bend rounded (a quadratic arc of at
 * most `radius`, less where a run is shorter than two radii).
 */
function rounded(points: Point[], radius: number = CORNER): Curve {
  const [first, ...rest] = points;
  const length = (a: Point, b: Point) =>
    Math.abs(b[0] - a[0]) + Math.abs(b[1] - a[1]);
  const segments: [Point, Point, Point][] = [];
  let at: Point = first!;
  for (let i = 1; i < points.length - 1; i++) {
    const before = points[i - 1]!;
    const corner = points[i]!;
    const after = points[i + 1]!;
    const r = Math.min(
      radius,
      length(before, corner) / 2,
      length(corner, after) / 2,
    );
    const into = lerp(corner, before, r / length(before, corner) || 0);
    const out = lerp(corner, after, r / length(corner, after) || 0);
    segments.push(straight(at, into));
    // The quadratic (into, corner, out) as a cubic.
    segments.push([lerp(into, corner, 2 / 3), lerp(out, corner, 2 / 3), out]);
    at = out;
  }
  if (rest.length) segments.push(straight(at, points.at(-1)!));
  return { start: first!, segments };
}

const overlap = (a: Box, b: Box) =>
  a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
/** Inside a box, a pixel in from each edge: touching an edge is meeting it. */
const strictlyIn = ([px, py]: Point, b: Box) =>
  px > b.x + 1 && px < b.x + b.w - 1 && py > b.y + 1 && py < b.y + b.h - 1;

function bezier(
  p0: Point,
  [p1, p2, p3]: [Point, Point, Point],
  t: number,
): Point {
  const u = 1 - t;
  const a = u * u * u;
  const b = 3 * u * u * t;
  const c = 3 * u * t * t;
  const d = t * t * t;
  return [
    a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1],
  ];
}

/** The SVG path of a line. */
export function pathOf(curve: Curve): string {
  const n = (p: Point) => `${round(p[0])} ${round(p[1])}`;
  return [
    `M ${n(curve.start)}`,
    ...curve.segments.map(([a, b, c]) => `C ${n(a)} ${n(b)} ${n(c)}`),
  ].join(" ");
}
const round = (v: number) => Math.round(v * 100) / 100;

/** Points along a line, `per` to a segment, its ends included. */
export function pointsOf(curve: Curve, per = 32): Point[] {
  const out: Point[] = [curve.start];
  let from = curve.start;
  for (const segment of curve.segments) {
    for (let i = 1; i <= per; i++) out.push(bezier(from, segment, i / per));
    from = segment[2];
  }
  return out;
}

/** Where an upright curve crosses the height `y`. */
function crossing(curve: Curve, y: number): number {
  const [segment] = curve.segments;
  const down = segment![2][1] > curve.start[1];
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 40; i++) {
    const t = (lo + hi) / 2;
    const at = bezier(curve.start, segment!, t)[1];
    if (at < y === down) lo = t;
    else hi = t;
  }
  return bezier(curve.start, segment!, (lo + hi) / 2)[0];
}

export type Route = "next" | "over" | "down" | "up" | "rail";

interface Meeting {
  key: string;
  /** The middle of the tile at the line's other end. */
  other: number;
  back: boolean;
}

interface Drawn {
  id: string;
  move: Move;
  kind: MoveKind;
  route: Route;
  /** Its words' size; null on an exit after the first of its action and bus. */
  size: Box | null;
  /** Its words at the gap's width: between the rows, where wide ones find no room. */
  narrow: Box;
}

export function laneGeometry(
  layout: LaneLayout,
  words: (move: Move) => MoveWords,
  heights: Record<string, number> = {},
  showBack = false,
): LaneGeometry {
  const place = Object.fromEntries(layout.nodes.map((n) => [n.status, n]));
  const height = (s: string) => Math.max(CARD_MIN_H, heights[s] ?? CARD_MIN_H);

  // Columns: the row, then below it.
  const column: Record<string, number> = {};
  const rows: Record<string, 0 | 1> = {};
  layout.main.forEach((s, i) => {
    column[s] = i;
    rows[s] = 0;
  });
  const below = new Set<number>();
  const settle = (s: string, wanted: number) => {
    let c = Math.max(0, wanted);
    while (below.has(c)) c++;
    below.add(c);
    column[s] = c;
    rows[s] = 1;
  };
  const off = layout.nodes.map((n) => n.status).filter((s) => !(s in rows));
  for (const s of off) {
    const from = layout.forward
      .filter((m) => m.to === s && rows[m.from] === 0)
      .map((m) => column[m.from]!);
    if (from.length)
      settle(s, Math.round(from.reduce((a, b) => a + b, 0) / from.length));
  }
  for (const s of off) {
    if (s in rows) continue;
    const from = [...layout.forward, ...layout.backward, ...layout.exits]
      .filter((m) => m.to === s && m.from in column)
      .map((m) => column[m.from]!);
    settle(s, from.length ? Math.max(...from) + 1 : place[s]!.column);
  }
  const x = (s: string) => OUTER + column[s]! * PITCH;
  const centerX = (s: string) => x(s) + CARD_W / 2;

  // What is drawn, and how.
  const routeOf = (m: Move, kind: MoveKind): Route => {
    const [a, b] = [rows[m.from], rows[m.to]];
    if (kind !== "exit" && a === 0 && b === 0)
      return kind === "forward" && column[m.to] === column[m.from]! + 1
        ? "next"
        : "over";
    if (kind === "forward" && a === 0 && b === 1) return "down";
    if (kind === "back" && a === 1 && b === 0) return "up";
    return "rail";
  };
  const wanted: [Move, MoveKind][] = [
    ...layout.forward.map((m): [Move, MoveKind] => [m, "forward"]),
    ...(showBack
      ? [
          ...layout.backward.map((m): [Move, MoveKind] => [m, "back"]),
          ...layout.exits.map((m): [Move, MoveKind] => [m, "exit"]),
        ]
      : []),
  ];
  const worded = new Set<string>();
  const drawn: Drawn[] = wanted.map(([move, kind]) => {
    const route = routeOf(move, kind);
    const bus = `${move.to}:${move.action}`;
    const first = kind !== "exit" || !worded.has(bus);
    if (kind === "exit") worded.add(bus);
    return {
      id: `${move.from}->${move.to}`,
      move,
      kind,
      route,
      size: first
        ? estimateLabel(
            words(move),
            route === "next" ? LABEL_MAX_W : WIDE_LABEL_MAX_W,
          )
        : null,
      narrow: estimateLabel(words(move), LABEL_MAX_W),
    };
  });
  const sizeOf = (d: Drawn) => d.size ?? { x: 0, y: 0, w: 0, h: 0 };
  const along = (route: Route) => drawn.filter((d) => d.route === route);

  // Where a line meets a tile's top or bottom, spread across it so lines
  // meeting one tile do not cross there. Between the rows, in the order of
  // the tiles at their other ends (a way back first, left of the move it
  // undoes). On a top of the row, arches: those to the left on the left,
  // and on each side the one reaching farther outside the nearer.
  const ports = new Map<string, number>();
  const sides = new Map<string, Meeting[]>();
  const meet = (
    s: string,
    side: "top" | "bottom",
    key: string,
    other: string,
    back: boolean,
  ) => {
    const id = `${s}:${side}`;
    sides.set(id, [
      ...(sides.get(id) ?? []),
      { key, other: centerX(other), back },
    ]);
  };
  for (const d of drawn) {
    const { from, to } = d.move;
    const back = d.kind !== "forward";
    if (d.route === "over") {
      meet(from, "top", `${d.id}:from`, to, back);
      meet(to, "top", `${d.id}:to`, from, back);
    } else if (d.route === "down") {
      meet(from, "bottom", `${d.id}:from`, to, back);
      meet(to, "top", `${d.id}:to`, from, back);
    } else if (d.route === "up") {
      meet(from, "top", `${d.id}:from`, to, back);
      meet(to, "bottom", `${d.id}:to`, from, back);
    }
  }
  for (const [id, entries] of sides) {
    const s = id.slice(0, id.lastIndexOf(":"));
    const arches = rows[s] === 0 && id.endsWith(":top");
    const here = centerX(s);
    entries
      .sort((a, b) =>
        arches
          ? Number(a.other > here) - Number(b.other > here) || b.other - a.other
          : a.other - b.other || Number(b.back) - Number(a.back),
      )
      .forEach((e, i) =>
        ports.set(
          e.key,
          x(s) +
            (entries.length === 1
              ? CARD_W / 2
              : PORT_MARGIN +
                ((CARD_W - 2 * PORT_MARGIN) * i) / (entries.length - 1)),
        ),
      );
  }
  const port = (d: Drawn, end: "from" | "to") => ports.get(`${d.id}:${end}`)!;

  // Arches: the shorter first; each a level above every placed arch whose
  // span or words it meets.
  const arches = along("over").map((d) => {
    const [a, b] = [port(d, "from"), port(d, "to")];
    const mid = (a + b) / 2;
    const w = sizeOf(d).w;
    return {
      d,
      lo: Math.min(a, b, mid - w / 2) - LABEL_GAP,
      hi: Math.max(a, b, mid + w / 2) + LABEL_GAP,
      level: 0,
    };
  });
  const placed: typeof arches = [];
  for (const arch of [...arches].sort((p, q) => p.hi - p.lo - (q.hi - q.lo))) {
    const under = placed.filter((o) => o.lo < arch.hi && arch.lo < o.hi);
    arch.level = under.length ? 1 + Math.max(...under.map((o) => o.level)) : 0;
    placed.push(arch);
  }
  const levels = Math.max(0, ...arches.map((a) => a.level + 1));
  const levelH = Array.from({ length: levels }, (_, k) =>
    Math.max(...arches.filter((a) => a.level === k).map((a) => sizeOf(a.d).h)),
  );
  // Each level's words: centred this far above the row's top.
  const levelRise: number[] = [];
  let rise = ARCH_BASE;
  for (let k = 0; k < levels; k++) {
    levelRise.push(rise + levelH[k]! / 2);
    rise += levelH[k]! + LABEL_GAP;
  }
  const above = TOP_PAD + (levels ? rise - LABEL_GAP : 0);

  // The rows and the corridor between them. A line between the rows is
  // upright at both ends, so it never reaches into a tile; its words sit on
  // a track of the corridor, where they cover no other words and no other
  // line crosses them (moves down from the top track, ways back from the
  // bottom one). A corridor with no such place for every move's words gets
  // one track more.
  const inRow = (r: 0 | 1) => Object.keys(rows).filter((s) => rows[s] === r);
  const rowH = (r: 0 | 1) => Math.max(0, ...inRow(r).map(height));
  const top0 = above;
  const y0 = top0 + rowH(0) / 2;
  const corridorTop = top0 + rowH(0);
  const hasBelow = inRow(1).length > 0;
  const between = [...along("down"), ...along("up")];
  const trackH = Math.max(
    0,
    ...between.flatMap((d) => [sizeOf(d).h, d.narrow.h]),
  );
  const drop = (s: string) => x(s) + CARD_W + INSET;
  const riseAt = (s: string) => x(s) - INSET;
  // The rail's lines that run up or down through the corridor.
  const upright = along("rail").flatMap((d) => [
    ...(rows[d.move.from] === 0 ? [drop(d.move.from)] : []),
    ...(rows[d.move.to] === 0 ? [riseAt(d.move.to)] : []),
  ]);
  const ends = (d: Drawn, cards: Record<string, Box>): [Point, Point] => {
    const from = cards[d.move.from]!;
    const to = cards[d.move.to]!;
    return d.route === "down"
      ? [
          [port(d, "from"), from.y + from.h],
          [port(d, "to"), to.y],
        ]
      : [
          [port(d, "from"), from.y],
          [port(d, "to"), to.y + to.h],
        ];
  };
  const stack = (tracks: number) => {
    const corridor = hasBelow
      ? Math.max(
          CORRIDOR_MIN,
          2 * CORRIDOR_PAD + tracks * trackH + (tracks - 1) * LABEL_GAP,
        )
      : 0;
    const y1 = corridorTop + corridor + rowH(1) / 2;
    const cards: Record<string, Box> = {};
    for (const s of Object.keys(rows)) {
      const middle = rows[s] === 0 ? y0 : y1;
      cards[s] = {
        x: x(s),
        y: middle - height(s) / 2,
        w: CARD_W,
        h: height(s),
      };
    }
    const curves = new Map(
      between.map((d) => [d, uprightCurve(...ends(d, cards))] as const),
    );
    const trackY = (k: number) =>
      corridorTop + CORRIDOR_PAD + k * (trackH + LABEL_GAP) + trackH / 2;
    const labels = new Map<Drawn, Box>();
    const free = (d: Drawn, box: Box) =>
      [...labels.values()].every((o) => !overlap(o, box)) &&
      between.every(
        (o) =>
          o === d || !pointsOf(curves.get(o)!).some((p) => strictlyIn(p, box)),
      ) &&
      [...labels.values()].every(
        (o) => !pointsOf(curves.get(d)!).some((p) => strictlyIn(p, o)),
      ) &&
      upright.every((u) => u <= box.x + 1 || u >= box.x + box.w - 1);
    let fits = true;
    for (const d of between) {
      const order = Array.from({ length: tracks }, (_, k) =>
        d.route === "down" ? k : tracks - 1 - k,
      );
      const size = sizeOf(d);
      // On its track, centred on its line, or slid sideways while the
      // pill still covers the line; wide where that finds room, else at
      // the gap's width.
      const spot = [size, d.narrow]
        .flatMap((words) =>
          order.flatMap((k) =>
            SLIDES.map((slide): Box => {
              const y = trackY(k);
              const middle = crossing(curves.get(d)!, y) + slide * words.w;
              return { ...words, x: middle - words.w / 2, y: y - words.h / 2 };
            }),
          ),
        )
        .find((box) => free(d, box));
      if (!spot) fits = false;
      labels.set(
        d,
        spot ?? {
          ...size,
          x: crossing(curves.get(d)!, trackY(order[0]!)) - size.w / 2,
          y: trackY(order[0]!) - size.h / 2,
        },
      );
    }
    return { y1, cards, curves, labels, fits };
  };
  let layers = stack(1);
  for (let tracks = 2; !layers.fits && tracks <= between.length; tracks++)
    layers = stack(tracks);
  const { y1, cards } = layers;
  const cy = (s: string) => (rows[s] === 0 ? y0 : y1);

  const routed = new Map<Drawn, RoutedMove>();
  const route = (d: Drawn, curve: Curve, center: Point | null) => {
    const size = d.size;
    routed.set(d, {
      id: d.id,
      move: d.move,
      kind: d.kind,
      route: d.route,
      curve,
      label:
        size && center
          ? { ...size, x: center[0] - size.w / 2, y: center[1] - size.h / 2 }
          : null,
    });
  };

  for (const d of along("next")) {
    const a: Point = [x(d.move.from) + CARD_W, y0];
    const b: Point = [x(d.move.to), y0];
    route(d, { start: a, segments: [straight(a, b)] }, lerp(a, b, 0.5));
  }
  // Each arch, then its words: at its top, or along it, clear of every
  // other arch and the words already placed.
  const archCurves = new Map(
    arches.map((arch) => {
      const { d } = arch;
      const a: Point = [port(d, "from"), cards[d.move.from]!.y];
      const b: Point = [port(d, "to"), cards[d.move.to]!.y];
      const peak = top0 - levelRise[arch.level]!;
      // A cubic with both controls at one height peaks, at its middle, at
      // (a + b) / 8 + 3/4 of that height.
      const control = (peak - (a[1] + b[1]) / 8) / 0.75;
      const curve: Curve = {
        start: a,
        segments: [[[a[0], control], [b[0], control], b]],
      };
      return [arch, curve] as const;
    }),
  );
  const archLabels: Box[] = [];
  for (const arch of [...arches].sort((p, q) => p.level - q.level)) {
    const curve = archCurves.get(arch)!;
    const size = sizeOf(arch.d);
    const boxAt = (t: number): Box => {
      const [cx, cy] = bezier(curve.start, curve.segments[0]!, t);
      return { ...size, x: cx - size.w / 2, y: cy - size.h / 2 };
    };
    const box =
      ARCH_SPOTS.map(boxAt).find(
        (box) =>
          archLabels.every((o) => !overlap(o, box)) &&
          [...archCurves].every(
            ([other, c]) =>
              other === arch || !pointsOf(c).some((p) => strictlyIn(p, box)),
          ) &&
          box.y + box.h <= top0 - ARCH_BASE / 2,
      ) ?? boxAt(0.5);
    archLabels.push(box);
    route(arch.d, curve, [box.x + box.w / 2, box.y + box.h / 2]);
  }
  for (const d of between) {
    route(d, layers.curves.get(d)!, null);
    // As placed: wide, or at the gap's width.
    routed.get(d)!.label = layers.labels.get(d)!;
  }

  // The rail: one bus per final status its exits go to, one lane per other
  // move; lanes stacked under the rows, no two items of a lane meeting.
  const railTop = hasBelow ? y1 + rowH(1) / 2 : y0 + rowH(0) / 2;
  const items = new Map<string, Drawn[]>();
  for (const d of along("rail")) {
    const key = d.kind === "exit" ? `exit:${d.move.to}` : d.id;
    items.set(key, [...(items.get(key) ?? []), d]);
  }
  const lanes: [number, number][][] = [];
  const railItems = [...items.values()].map((members) => {
    const target = members[0]!.move.to;
    const xs = [...members.map((d) => drop(d.move.from)), riseAt(target)];
    const worded = members.filter((d) => d.size);
    const words = worded.reduce((sum, d) => sum + sizeOf(d).w + LABEL_GAP, 0);
    const lo = Math.min(...xs, riseAt(target) - words) - TRUNK;
    const hi = Math.max(...xs) + TRUNK;
    let lane = lanes.findIndex((taken) =>
      taken.every(([a, b]) => hi <= a || lo >= b),
    );
    if (lane < 0) lane = lanes.push([]) - 1;
    lanes[lane]!.push([lo, hi]);
    return { members, worded, target, lane };
  });
  const laneY: number[] = [];
  let railBottom = railTop;
  if (lanes.length) {
    let at = railTop + RAIL_PAD;
    for (let lane = 0; lane < lanes.length; lane++) {
      const tallest = Math.max(
        LINE_H,
        ...railItems
          .filter((i) => i.lane === lane)
          .flatMap((i) => i.worded.map((d) => sizeOf(d).h)),
      );
      laneY.push(at + tallest / 2);
      at += tallest + LABEL_GAP;
    }
    railBottom = at - LABEL_GAP;
  }
  for (const item of railItems) {
    const y = laneY[item.lane]!;
    const end = riseAt(item.target);
    for (const d of item.members) {
      const { from, to } = d.move;
      route(
        d,
        rounded([
          [x(from) + CARD_W, cy(from)],
          [drop(from), cy(from)],
          [drop(from), y],
          [end, y],
          [end, cy(to)],
          [x(to), cy(to)],
        ]),
        null,
      );
    }
    // Words at the end of the bus, right to left; a lone move's in the
    // middle of its run.
    if (item.members.length === 1 && item.members[0]!.kind !== "exit") {
      const d = item.members[0]!;
      const r = routed.get(d)!;
      const middle = (drop(d.move.from) + end) / 2;
      r.label = d.size && {
        ...d.size,
        x: middle - d.size.w / 2,
        y: y - d.size.h / 2,
      };
      continue;
    }
    let right = end - CLEAR;
    for (const d of item.worded) {
      const size = sizeOf(d);
      routed.get(d)!.label = { ...size, x: right - size.w, y: y - size.h / 2 };
      right -= size.w + LABEL_GAP;
    }
  }

  const moves = drawn.map((d) => routed.get(d)!);
  const boxes = [
    ...Object.values(cards),
    ...moves.flatMap((m) => (m.label ? [m.label] : [])),
  ];
  return {
    cards,
    rows,
    moves,
    width: Math.max(...boxes.map((b) => b.x + b.w), 0) + OUTER,
    height:
      Math.max(
        railBottom,
        ...boxes.map((b) => b.y + b.h),
        hasBelow ? y1 + rowH(1) / 2 : y0 + rowH(0) / 2,
      ) + BOTTOM_PAD,
  };
}
