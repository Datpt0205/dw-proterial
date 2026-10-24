import type { SalesSchemas } from "@dw/api-client";

/**
 * Where the process page draws each status of a lane (2026-10-22). The
 * statuses and the moves between them are the API's (`GET
 * /sales/rules/process`, read from the domain's own move tables); this file
 * only places them, so a status or a move added on the server is drawn
 * without a change here. Nothing below names a status.
 *
 * - A **back move** (to a status already on the way from the start, found by
 *   walking the moves depth first) is written on its status ("Có thể quay
 *   lại: …"); on a wide screen it is also drawn, dashed, when "Hiện đường
 *   quay lại" is on (`process-geometry.ts`, 2026-10-24).
 * - A **many-to-one exit** (a move into a final status that more than one
 *   status reaches, like closing or declining a case) is written on the final
 *   status ("Có thể đóng từ: …"), and drawn only with the ways back.
 * - Every other move goes forward: a status's column is the longest run of
 *   forward moves from the start, and final statuses share the last column,
 *   so every arrow points right.
 * - The **main path** (2026-10-24, the canvas's one row) is the longest run
 *   of forward moves from the start that never enters a **detour**: a status
 *   with ways on, every one of them back or out (asking the customer to fix
 *   a PO, reviewing a change). On a tie the API's order of statuses decides.
 *   A detour has no forward move on, so it can only end a run; leaving it out
 *   keeps the row on the way a case goes when nothing needs redoing.
 */

export type Lane = SalesSchemas["ProcessLaneView"];
export type Move = SalesSchemas["ProcessEdgeView"];

export interface PlacedStatus {
  status: string;
  column: number;
  /** Position in its column, in the API's order. */
  row: number;
}

export interface LaneLayout {
  columns: number;
  rows: number;
  /** In the API's order. */
  nodes: PlacedStatus[];
  /** Drawn as arrows; each goes to a later column. */
  forward: Move[];
  /** The back moves, in the API's order; each goes to an earlier status. */
  backward: Move[];
  /** Per status, the earlier statuses it may move back to. */
  back: Record<string, string[]>;
  /** Per final status reached from more than one, where from. */
  exitsFrom: Record<string, string[]>;
  /** Those moves, in the API's order. */
  exits: Move[];
  /** Per status, every status it may move to. */
  next: Record<string, string[]>;
  /** The main path, from the start: the canvas's row. */
  main: string[];
}

export function layoutLane(lane: Lane): LaneLayout {
  const statuses = lane.nodes.map((n) => n.status);
  const known = new Set(statuses);
  const moves = lane.edges.filter(
    (e) => known.has(e.from) && known.has(e.to) && e.from !== e.to,
  );
  const next = group(
    statuses,
    moves,
    (m) => m.from,
    (m) => m.to,
  );
  const into = group(
    statuses,
    moves,
    (m) => m.to,
    (m) => m.from,
  );
  const final = new Set(statuses.filter((s) => next[s]!.length === 0));
  const exit = (m: Move) => final.has(m.to) && into[m.to]!.length > 1;

  // Depth first from the start (the API's first status), then from any
  // status the start does not reach: a move to a status still on the path
  // is a back move; what is left is acyclic, and the reverse of the order
  // statuses finish in is an order every forward move agrees with.
  const onPath = new Set<string>();
  const seen = new Set<string>();
  const finished: string[] = [];
  const backMoves = new Set<Move>();
  const visit = (status: string) => {
    seen.add(status);
    onPath.add(status);
    for (const m of moves) {
      if (m.from !== status || exit(m)) continue;
      if (onPath.has(m.to)) backMoves.add(m);
      else if (!seen.has(m.to)) visit(m.to);
    }
    onPath.delete(status);
    finished.push(status);
  };
  for (const status of statuses) if (!seen.has(status)) visit(status);

  const forward = moves.filter((m) => !exit(m) && !backMoves.has(m));
  const rank: Record<string, number> = {};
  for (const status of [...finished].reverse()) {
    rank[status] ??= 0;
    for (const m of forward)
      if (m.from === status)
        rank[m.to] = Math.max(rank[m.to] ?? 0, rank[status] + 1);
  }
  const last =
    Math.max(
      -1,
      ...statuses.filter((s) => !final.has(s)).map((s) => rank[s]!),
    ) + 1;
  const column = (s: string) => (final.has(s) ? last : rank[s]!);

  const perColumn: Record<number, number> = {};
  const nodes = statuses.map((status) => {
    const c = column(status);
    const row = perColumn[c] ?? 0;
    perColumn[c] = row + 1;
    return { status, column: c, row };
  });
  const back = group(
    statuses,
    moves.filter((m) => backMoves.has(m)),
    (m) => m.from,
    (m) => m.to,
  );
  const exitsFrom = Object.fromEntries(
    [...final].filter((s) => into[s]!.length > 1).map((s) => [s, into[s]!]),
  );
  return {
    columns: statuses.length ? last + 1 : 0,
    main: mainPath(statuses, forward, next),
    rows: Math.max(0, ...Object.values(perColumn)),
    nodes,
    forward,
    backward: moves.filter((m) => backMoves.has(m)),
    back,
    exitsFrom,
    exits: moves.filter(exit),
    next,
  };
}

/**
 * The longest run of forward moves from the first status through no detour
 * (a status whose every way on goes back or out); the API's order of
 * statuses breaks a tie. The forward moves are acyclic (`layoutLane`).
 */
function mainPath(
  statuses: string[],
  forward: Move[],
  next: Record<string, string[]>,
): string[] {
  const order = new Map(statuses.map((s, i) => [s, i]));
  const onward = (s: string) =>
    forward
      .filter((m) => m.from === s)
      .map((m) => m.to)
      .filter((t) => !(next[t]!.length && !forward.some((m) => m.from === t)))
      .sort((a, b) => order.get(a)! - order.get(b)!);
  const runs = new Map<string, number>();
  const run = (s: string): number => {
    if (!runs.has(s))
      runs.set(s, 1 + Math.max(0, ...onward(s).map((t) => run(t))));
    return runs.get(s)!;
  };
  const path: string[] = [];
  for (let at = statuses[0]; at !== undefined;) {
    path.push(at);
    const ways = onward(at);
    at = ways.find((t) => run(t) === Math.max(...ways.map(run)));
  }
  return path;
}

/** The statuses in drawing order: column by column, then down each. */
export function inColumnOrder(layout: LaneLayout): PlacedStatus[] {
  return [...layout.nodes].sort((a, b) => a.column - b.column || a.row - b.row);
}

function group(
  statuses: string[],
  moves: Move[],
  by: (m: Move) => string,
  value: (m: Move) => string,
): Record<string, string[]> {
  const out: Record<string, string[]> = Object.fromEntries(
    statuses.map((s) => [s, []]),
  );
  for (const m of moves) out[by(m)]!.push(value(m));
  return out;
}
