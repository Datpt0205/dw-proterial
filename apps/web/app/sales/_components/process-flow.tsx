"use client";

import "@xyflow/react/dist/style.css";
import { useCallback, useMemo, useState, type CSSProperties } from "react";
import {
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  getSmoothStepPath,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type EdgeProps,
  type EdgeTypes,
  type Node,
  type NodeChange,
  type NodeProps,
  type NodeTypes,
} from "@xyflow/react";
import { Tag, theme, Typography } from "antd";
import { EDGE_ACTION, EDGE_GUARD, MOVE_ACTOR } from "../_lib/labels";
import {
  inColumnOrder,
  type LaneLayout,
  type Move,
} from "../_lib/process-graph";
import { StatusLink, type StatusCard } from "./process-map";

/**
 * A lane of the DW1 process on a wide screen, drawn with React Flow
 * (`@xyflow/react`, Đạt's decision of 2026-10-23 recorded in CLAUDE.md "Web
 * UI": the one library besides antd, and this the one file allowed to import
 * it; `lib/__tests__/antd-only.test.ts` fails any other).
 *
 * The canvas only draws: what is a status, a move, a way back is
 * `process-graph.ts`'s placement of the API's lane, and every card is the
 * same `StatusLink` the phone list draws. Statuses sit on the rank columns;
 * a row is as tall as its tallest card, measured once React Flow has laid
 * them out. A forward move is an arrow to the right (one that skips a column
 * runs under the cards), a move back is a dashed arch, over the cards between
 * two of the first row and under them otherwise, and each carries its action
 * and its guards in words. Exits into a final status reached from many stay
 * words on that status, as on the phone.
 *
 * Nothing on the canvas is dragged, selected or connected. The card's link is
 * the focus stop (Tab, Enter opens the drawer, a middle click a new tab);
 * zoom is the controls, Ctrl + wheel or a pinch, so the wheel still scrolls
 * the page.
 */

const WIDTH = 216;
const MIN_HEIGHT = 136;
/** Room for a move's words between two columns. */
const GAP_X = 128;
/** Room for the arrows that run under a row, and their words. */
const GAP_Y = 96;
const PAD = 16;
/** Above or below the cards, for the arches of the moves back. */
const ARCH = 120;
/** Between two long arrows' tracks under the cards. */
const TRACK = 14;

/**
 * An arrow to the next column, one under the cards to a later column, or a
 * move back arching over the first row or under the cards.
 */
type Route = "forward" | "under" | "over" | "below";

interface StatusData extends Record<string, unknown> {
  card: StatusCard;
  onOpen: (item: string) => void;
}
interface MoveData extends Record<string, unknown> {
  route: Route;
  /** Which track an arrow under the cards runs on. */
  track: number;
  action: string;
  guards: string[];
}
type StatusNode = Node<StatusData, "status">;
type MoveEdge = Edge<MoveData, "move">;

/** The handles each route leaves from and arrives at. */
const HANDLES: Record<Route, [string, string]> = {
  forward: ["out", "in"],
  under: ["under-out", "under-in"],
  over: ["top-out", "top-in"],
  below: ["under-out", "under-in"],
};

const hidden = (place: CSSProperties): CSSProperties => ({
  ...place,
  opacity: 0,
  pointerEvents: "none",
});

/** The card, with a handle where each kind of arrow leaves and arrives. */
function StatusNodeView({ data }: NodeProps<StatusNode>) {
  return (
    <div style={{ width: WIDTH }}>
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        isConnectable={false}
        style={hidden({})}
      />
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        isConnectable={false}
        style={hidden({})}
      />
      <Handle
        id="top-in"
        type="target"
        position={Position.Top}
        isConnectable={false}
        style={hidden({ left: "35%" })}
      />
      <Handle
        id="top-out"
        type="source"
        position={Position.Top}
        isConnectable={false}
        style={hidden({ left: "65%" })}
      />
      <Handle
        id="under-in"
        type="target"
        position={Position.Bottom}
        isConnectable={false}
        style={hidden({ left: "35%" })}
      />
      <Handle
        id="under-out"
        type="source"
        position={Position.Bottom}
        isConnectable={false}
        style={hidden({ left: "65%" })}
      />
      <StatusLink card={data.card} onOpen={data.onOpen} drawn />
    </div>
  );
}

/**
 * Where React Flow places the handles before it has measured anything (and
 * where the tests read the arrows from): the same spots the handles above
 * are drawn at.
 */
function handlesFor(height: number): NonNullable<StatusNode["handles"]> {
  return [
    { id: "in", type: "target", position: Position.Left, x: 0, y: height / 2 },
    {
      id: "out",
      type: "source",
      position: Position.Right,
      x: WIDTH - 1,
      y: height / 2,
    },
    {
      id: "top-in",
      type: "target",
      position: Position.Top,
      x: WIDTH * 0.35,
      y: 0,
    },
    {
      id: "top-out",
      type: "source",
      position: Position.Top,
      x: WIDTH * 0.65,
      y: 0,
    },
    {
      id: "under-in",
      type: "target",
      position: Position.Bottom,
      x: WIDTH * 0.35,
      y: height - 1,
    },
    {
      id: "under-out",
      type: "source",
      position: Position.Bottom,
      x: WIDTH * 0.65,
      y: height - 1,
    },
  ];
}

/** A move: its path by route, its action and guards in words on it. */
function MoveEdgeView({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  markerEnd,
  data,
}: EdgeProps<MoveEdge>) {
  const { token } = theme.useToken();
  const route = data?.route ?? "forward";
  const back = route === "over" || route === "below";
  const [path, x, y] = back
    ? arch(sourceX, sourceY, targetX, targetY, route === "over" ? -1 : 1)
    : getSmoothStepPath({
        sourceX,
        sourceY,
        targetX,
        targetY,
        sourcePosition,
        targetPosition,
        borderRadius: 8,
        offset: route === "under" ? 24 + (data?.track ?? 0) * TRACK : 16,
      });
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: token.colorTextTertiary,
          strokeWidth: 1.5,
          strokeDasharray: back ? "6 4" : undefined,
        }}
      />
      <EdgeLabelRenderer>
        <div
          data-move={id}
          className="nodrag nopan flex flex-col items-center gap-1 text-center"
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${x}px, ${y}px)`,
            maxWidth: GAP_X - 8,
            padding: 2,
            background: token.colorBgContainer,
            borderRadius: token.borderRadiusSM,
            color: token.colorText,
            fontSize: token.fontSizeSM,
            lineHeight: token.lineHeightSM,
          }}
        >
          <span>{data?.action}</span>
          {data?.guards.map((guard) => (
            <Tag key={guard} className="me-0 whitespace-normal">
              {guard}
            </Tag>
          ))}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

/**
 * A move back: a cubic arch from one handle to the other, lifted `direction`
 * (-1 up, 1 down) further the further it reaches, so two arches of one row
 * keep their words apart. Its words sit at its middle. (React Flow's own
 * bezier lifts nothing between two handles at one height: a flat line.)
 */
function arch(
  sx: number,
  sy: number,
  tx: number,
  ty: number,
  direction: -1 | 1,
): [string, number, number] {
  const lift = Math.min(ARCH - 24, 48 + Math.abs(tx - sx) * 0.12);
  const c1 = sy + direction * lift;
  const c2 = ty + direction * lift;
  return [
    `M ${sx} ${sy} C ${sx} ${c1}, ${tx} ${c2}, ${tx} ${ty}`,
    (sx + tx) / 2,
    (sy + ty) / 2 + direction * 0.75 * lift,
  ];
}

const NODE_TYPES: NodeTypes = { status: StatusNodeView };
const EDGE_TYPES: EdgeTypes = { move: MoveEdgeView };

/** React Flow's own words for its controls, in the screen's language. */
const ARIA_LABELS = {
  "controls.ariaLabel": "Điều khiển sơ đồ",
  "controls.zoomIn.ariaLabel": "Phóng to",
  "controls.zoomOut.ariaLabel": "Thu nhỏ",
  "controls.fitView.ariaLabel": "Xem cả quy trình",
};

export function ProcessFlow({
  id,
  name,
  layout,
  cards,
  onOpen,
}: {
  /** Unique on the page: React Flow keys its markers by it. */
  id: string;
  /** The lane's name, for the canvas's accessible name. */
  name: string;
  layout: LaneLayout;
  cards: Record<string, StatusCard>;
  onOpen: (item: string) => void;
}) {
  const { token } = theme.useToken();
  // Each card's height once React Flow has measured it.
  const [heights, setHeights] = useState<Record<string, number>>({});
  const onNodesChange = useCallback((changes: NodeChange<StatusNode>[]) => {
    setHeights((before) => {
      let next = before;
      for (const change of changes)
        if (
          change.type === "dimensions" &&
          change.dimensions &&
          before[change.id] !== change.dimensions.height
        )
          next = { ...next, [change.id]: change.dimensions.height };
      return next;
    });
  }, []);

  const place = useMemo(
    () => Object.fromEntries(layout.nodes.map((n) => [n.status, n])),
    [layout],
  );
  // A row is as tall as its tallest card.
  const rowTop = useMemo(() => {
    const tops: number[] = [];
    let top = 0;
    for (let row = 0; row < layout.rows; row++) {
      tops.push(top);
      const tallest = Math.max(
        MIN_HEIGHT,
        ...layout.nodes
          .filter((n) => n.row === row)
          .map((n) => heights[n.status] ?? MIN_HEIGHT),
      );
      top += tallest + GAP_Y;
    }
    tops.push(top);
    return tops;
  }, [layout, heights]);

  // In drawing order, column by column, so Tab follows what is drawn.
  const nodes = useMemo<StatusNode[]>(
    () =>
      inColumnOrder(layout).map((n) => {
        const height = heights[n.status] ?? MIN_HEIGHT;
        return {
          id: n.status,
          type: "status",
          position: { x: n.column * (WIDTH + GAP_X), y: rowTop[n.row]! },
          data: { card: cards[n.status]!, onOpen },
          initialWidth: WIDTH,
          initialHeight: height,
          handles: handlesFor(height),
          draggable: false,
          selectable: false,
          connectable: false,
          focusable: false,
          // Not selectable or draggable, React Flow would let clicks through
          // to the canvas; the card's link takes them. A drag from a card does
          // not pan: the card is for opening.
          className: "nopan",
          style: { pointerEvents: "all" },
        };
      }),
    [layout, cards, onOpen, heights, rowTop],
  );

  // A move back between two cards of the first row arches over them.
  const firstRow = useCallback(
    (m: Move) => place[m.from]!.row === 0 && place[m.to]!.row === 0,
    [place],
  );
  const edges = useMemo<MoveEdge[]>(() => {
    const long = layout.forward.filter(
      (m) => place[m.to]!.column - place[m.from]!.column > 1,
    );
    const words = (move: Move, route: Route): MoveEdge => {
      const track = long.indexOf(move);
      const guards = move.guards.map((g) => EDGE_GUARD[g] ?? g);
      return {
        id: `${move.from}->${move.to}`,
        type: "move",
        source: move.from,
        target: move.to,
        sourceHandle: HANDLES[route][0],
        targetHandle: HANDLES[route][1],
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: token.colorTextTertiary,
        },
        data: {
          route,
          track: Math.max(0, track),
          action: EDGE_ACTION[move.action] ?? move.action,
          guards,
        },
        ariaLabel: [
          `${cards[move.from]?.label ?? move.from} → ${cards[move.to]?.label ?? move.to}`,
          `${EDGE_ACTION[move.action] ?? move.action} (${MOVE_ACTOR[move.actor] ?? move.actor})`,
          ...(guards.length ? [`điều kiện: ${guards.join(", ")}`] : []),
          ...(route === "over" || route === "below" ? ["quay lại"] : []),
        ].join("; "),
        selectable: false,
        focusable: false,
      };
    };
    return [
      ...layout.forward.map((m) =>
        words(m, long.includes(m) ? "under" : "forward"),
      ),
      ...layout.backward.map((m) => words(m, firstRow(m) ? "over" : "below")),
    ];
  }, [layout, place, cards, firstRow, token.colorTextTertiary]);

  const above = layout.backward.some(firstRow) ? ARCH : 0;
  const below =
    layout.backward.some((m) => !firstRow(m)) ||
    layout.forward.some((m) => place[m.to]!.column - place[m.from]!.column > 1)
      ? ARCH
      : 0;
  const height = Math.max(
    360,
    above + rowTop[layout.rows]! - GAP_Y + below + 2 * PAD,
  );

  return (
    <div className="space-y-2">
      <Typography.Paragraph className="mb-0!">
        Kéo nền sơ đồ để xem hết {layout.nodes.length} trạng thái; phóng to, thu
        nhỏ hoặc xem cả quy trình bằng các nút ở góc. Mũi tên nét đứt là đường
        quay lại.
      </Typography.Paragraph>
      <div
        style={{
          height,
          border: `1px solid ${token.colorBorderSecondary}`,
          borderRadius: token.borderRadiusLG,
          overflow: "hidden",
        }}
      >
        <ReactFlow<StatusNode, MoveEdge>
          id={id}
          aria-label={`Sơ đồ quy trình ${name}`}
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          edgeTypes={EDGE_TYPES}
          onNodesChange={onNodesChange}
          defaultViewport={{ x: PAD, y: PAD + above, zoom: 1 }}
          minZoom={0.4}
          maxZoom={1.5}
          nodesDraggable={false}
          nodesConnectable={false}
          nodesFocusable={false}
          edgesFocusable={false}
          elementsSelectable={false}
          zoomOnScroll={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
          disableKeyboardA11y
          ariaLabelConfig={ARIA_LABELS}
          style={
            {
              "--xy-edge-stroke": token.colorTextTertiary,
              "--xy-background-color": token.colorBgLayout,
              "--xy-controls-button-background-color": token.colorBgContainer,
              "--xy-controls-button-background-color-hover":
                token.controlItemBgHover,
              "--xy-controls-button-color": token.colorText,
              "--xy-controls-button-color-hover": token.colorText,
              "--xy-controls-button-border-color": token.colorBorderSecondary,
              "--xy-controls-box-shadow": token.boxShadowTertiary,
              "--xy-attribution-background-color": token.colorBgContainer,
            } as CSSProperties
          }
        >
          <Controls showInteractive={false} position="bottom-right" />
        </ReactFlow>
      </div>
    </div>
  );
}
