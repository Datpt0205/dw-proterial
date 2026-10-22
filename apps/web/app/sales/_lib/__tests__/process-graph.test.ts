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
    expect(quotes.forward).toContainEqual({
      from: "sent",
      to: "master_list_recorded",
    });
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
        { from: "in_review", to: "on_hold" },
        { from: "on_hold", to: "in_review" },
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
        { from: "received", to: "received" },
        { from: "received", to: "nowhere" },
      ],
    });
    expect(layout.next.received).toEqual(["checked", "closed"]);
  });
});
