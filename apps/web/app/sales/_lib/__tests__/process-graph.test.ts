import { describe, expect, it } from "vitest";
import { inColumnOrder, layoutLane, type Lane } from "../process-graph";
import { PROCESS } from "./process-fixture";

const [ORDERS, QUOTES] = PROCESS.lanes as [Lane, Lane];

const columnOf = (lane: Lane) =>
  Object.fromEntries(layoutLane(lane).nodes.map((n) => [n.status, n.column]));

describe("placing a lane's statuses from the served moves (2026-10-22)", () => {
  it("ranks the order lane by the longest run of forward moves, final statuses last", () => {
    expect(columnOf(ORDERS)).toEqual({
      received: 0,
      checked: 1,
      in_review: 2,
      correction_requested: 3,
      prepared: 3,
      uploaded_to_bravo: 4,
      cross_checked: 5,
      confirmed: 6,
      change_review: 7,
      closed: 8,
    });
  });

  it("draws every forward move pointing right, and no other", () => {
    for (const lane of [ORDERS, QUOTES]) {
      const layout = layoutLane(lane);
      const column = columnOf(lane);
      for (const m of layout.forward)
        expect(column[m.to]!, `${m.from}->${m.to}`).toBeGreaterThan(
          column[m.from]!,
        );
      // Every served move is drawn, written as a way back, or as an exit.
      const written =
        layout.forward.length +
        Object.values(layout.back).flat().length +
        Object.values(layout.exitsFrom).flat().length;
      expect(written).toBe(lane.edges.length);
    }
  });

  it("writes the ways back and the many-to-one exits as words, not arrows", () => {
    const orders = layoutLane(ORDERS);
    expect(orders.back.correction_requested).toEqual(["checked", "in_review"]);
    expect(orders.back.change_review).toEqual(["uploaded_to_bravo"]);
    expect(orders.exitsFrom.closed).toEqual([
      "received",
      "checked",
      "in_review",
      "correction_requested",
      "prepared",
    ]);
    const quotes = layoutLane(QUOTES);
    expect(Object.keys(quotes.exitsFrom)).toEqual(["declined"]);
    // A final status reached from one status is an arrow.
    expect(quotes.forward).toContainEqual(
      expect.objectContaining({ from: "sent", to: "master_list_recorded" }),
    );
    expect(quotes.back.returned).toEqual(["priced"]);
  });

  it("places a status the API adds, with its moves, without a change here", () => {
    const lane: Lane = {
      ...ORDERS,
      nodes: [
        ...ORDERS.nodes,
        { status: "on_hold", steps: [], holder: "sales" },
      ],
      edges: [
        ...ORDERS.edges,
        {
          from: "in_review",
          to: "on_hold",
          action: "edit",
          actor: "sales",
          guards: [],
        },
        {
          from: "on_hold",
          to: "in_review",
          action: "edit",
          actor: "sales",
          guards: [],
        },
      ],
    };
    const layout = layoutLane(lane);
    expect(columnOf(lane).on_hold).toBe(3);
    expect(layout.back.on_hold).toEqual(["in_review"]);
    expect(inColumnOrder(layout).map((n) => n.status)).toContain("on_hold");
  });

  it("drops a move to itself and a move naming a status the lane lacks", () => {
    const layout = layoutLane({
      ...ORDERS,
      edges: [
        ...ORDERS.edges,
        {
          from: "received",
          to: "received",
          action: "edit",
          actor: "sales",
          guards: [],
        },
        {
          from: "received",
          to: "nowhere",
          action: "edit",
          actor: "sales",
          guards: [],
        },
      ],
    });
    expect(layout.next.received).toEqual(["checked", "closed"]);
  });
});

describe("the main path: the canvas's one row (2026-10-24)", () => {
  const move = (from: string, to: string) => ({
    from,
    to,
    action: "edit" as const,
    actor: "sales" as const,
    guards: [],
  });
  const lane = (statuses: string[], edges: [string, string][]): Lane => ({
    ...ORDERS,
    nodes: statuses.map((status) => ({ status, steps: [], holder: "sales" })),
    edges: edges.map(([from, to]) => move(from, to)),
  });

  it("is the longest run of forward moves from the start that enters no detour", () => {
    // Asking the customer to fix a PO, and reviewing a change, only lead
    // back: the row ends where a confirmed order rests.
    expect(layoutLane(ORDERS).main).toEqual([
      "received",
      "checked",
      "in_review",
      "prepared",
      "uploaded_to_bravo",
      "cross_checked",
      "confirmed",
    ]);
    expect(layoutLane(QUOTES).main).toEqual([
      "received",
      "ycbg_drafted",
      "ycbg_recorded",
      "sent_to_design",
      "design_replied",
      "priced",
      "pending_approval",
      "approved",
      "sent",
      "master_list_recorded",
    ]);
  });

  it("leaves out a detour even where it makes the longer run", () => {
    // b -> d is a detour (its only way on goes back), listed before c:
    // without the rule the tie would go to d, and the row run a, b, d.
    const layout = layoutLane(
      lane(
        ["a", "b", "d", "c"],
        [
          ["a", "b"],
          ["b", "c"],
          ["b", "d"],
          ["d", "a"],
        ],
      ),
    );
    expect(layout.main).toEqual(["a", "b", "c"]);
    // Two runs of one length: the API's order of statuses decides.
    const tie = layoutLane(
      lane(
        ["a", "x", "y", "z", "end"],
        [
          ["a", "y"],
          ["a", "x"],
          ["x", "z"],
          ["y", "z"],
          ["z", "end"],
        ],
      ),
    );
    expect(tie.main).toEqual(["a", "x", "z", "end"]);
  });

  it("is the first status alone when nothing leads on from it", () => {
    expect(layoutLane(lane(["a"], [])).main).toEqual(["a"]);
    expect(layoutLane(lane([], [])).main).toEqual([]);
  });
});
