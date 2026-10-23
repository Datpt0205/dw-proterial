import type { SalesSchemas } from "@dw/api-client";

/**
 * Where the process page draws each status of a lane (2026-10-22). The
 * statuses and the moves between them are the API's (`GET
 * /sales/rules/process`, read from the domain's own move tables); this file
 * only places them, so a status or a move added on the server is drawn
 * without a change here. Nothing below names a status.
 *
 * - A **back move** (to a status already on the way from the start, found by
 *   walking the moves depth first) is drawn as a dashed curve under the cards
 *   on a wide screen (`process-flow.tsx`, 2026-10-23); below `lg` the list
 *   writes it on its node ("Có thể quay lại: …").
 * - A **many-to-one exit** (a move into a final status that more than one
 *   status reaches, like closing or declining a case) is not drawn: the final
 *   status lists where it is reached from ("Có thể đóng từ: …").
 * - Every other move goes forward: a status's column is the longest run of
 *   forward moves from the start, and final statuses share the last column,
 *   so every arrow points right.
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
  /** Per status, every status it may move to. */
  next: Record<string, string[]>;
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
    rows: Math.max(0, ...Object.values(perColumn)),
    nodes,
    forward,
    backward: moves.filter((m) => backMoves.has(m)),
    back,
    exitsFrom,
    next,
  };
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
