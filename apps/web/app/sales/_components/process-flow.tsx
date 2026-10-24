"use client";

import "@xyflow/react/dist/style.css";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  useReactFlow,
  useStore,
  type Dimensions,
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
import {
  CARD_W,
  laneGeometry,
  type Box,
  type MoveWords,
} from "../_lib/process-geometry";
import { StatusLink, type StatusCard } from "./process-map";

/**
 * A lane of the DW1 process on a wide screen, drawn with React Flow
 * (`@xyflow/react`, Đạt's decision of 2026-10-23 recorded in CLAUDE.md "Web
 * UI": the one library besides antd, and this the one file allowed to import
 * it; `lib/__tests__/antd-only.test.ts` fails any other). The page loads this
 * file lazily (`next/dynamic`), so a phone, which draws the list, never
 * downloads it.
 *
 * The canvas only draws: what is a status, a move, a way back is
 * `process-graph.ts`'s placement of the API's lane, and where each card,
 * line and label sits is `process-geometry.ts` (bands of at most five
 * columns, moves between neighbours through the gap, the rest on lanes over
 * and under each band, labels that never cover a card or each other). Every
 * card is the same `StatusLink` the phone list draws; its measured height
 * feeds the geometry again. The whole lane is in view on load and whenever
 * the geometry or the frame changes size (`LaneViewport`). Exits into a final status reached from many stay
 * words on that status, as on the phone.
 *
 * Nothing on the canvas is dragged, selected or connected. The card's link is
 * the focus stop (Tab, Enter opens the drawer, a middle click a new tab);
 * zoom is the controls, Ctrl + wheel or a pinch, so the wheel still scrolls
 * the page.
 */

const PAD = 16;
/** The least zoom the fit goes to: below it, cards' words stop being legible. */
const MIN_FIT_ZOOM = 0.6;

interface StatusData extends Record<string, unknown> {
  card: StatusCard;
  onOpen: (item: string) => void;
}
interface MoveData extends Record<string, unknown> {
  back: boolean;
  points: [number, number][];
  label: Box;
  action: string;
  guards: string[];
}
type StatusNode = Node<StatusData, "status">;
type MoveEdge = Edge<MoveData, "move">;

const hidden: CSSProperties = { opacity: 0, pointerEvents: "none" };

/** The card, with a handle on each side; the geometry routes every line. */
function StatusNodeView({ data }: NodeProps<StatusNode>) {
  return (
    <div style={{ width: CARD_W }}>
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        isConnectable={false}
        style={hidden}
      />
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        isConnectable={false}
        style={hidden}
      />
      <StatusLink card={data.card} onOpen={data.onOpen} drawn />
    </div>
  );
}

/** Where React Flow places the handles before it has measured anything. */
function handlesFor(height: number): NonNullable<StatusNode["handles"]> {
  return [
    { id: "in", type: "target", position: Position.Left, x: 0, y: height / 2 },
    {
      id: "out",
      type: "source",
      position: Position.Right,
      x: CARD_W - 1,
      y: height / 2,
    },
  ];
}

/** A move: the geometry's polyline, and its words in the box placed for them. */
function MoveEdgeView({ id, markerEnd, data }: EdgeProps<MoveEdge>) {
  const { token } = theme.useToken();
  if (!data) return null;
  const path = data.points
    .map(([x, y], i) => `${i ? "L" : "M"} ${x} ${y}`)
    .join(" ");
  const { label } = data;
  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: token.colorTextTertiary,
          strokeWidth: 1.5,
          strokeDasharray: data.back ? "6 4" : undefined,
        }}
      />
      <EdgeLabelRenderer>
        <div
          className="nodrag nopan flex items-center justify-center"
          style={{
            position: "absolute",
            transform: `translate(${label.x}px, ${label.y}px)`,
            width: label.w,
            height: label.h,
            pointerEvents: "none",
          }}
        >
          <div
            data-move={id}
            className="flex flex-col items-center gap-1 text-center"
            style={{
              width: "100%",
              padding: 4,
              background: token.colorBgContainer,
              borderRadius: token.borderRadiusSM,
              color: token.colorText,
              fontSize: token.fontSizeSM,
              lineHeight: token.lineHeightSM,
            }}
          >
            <span>{data.action}</span>
            {data.guards.map((guard) => (
              <Tag key={guard} className="me-0 whitespace-normal">
                {guard}
              </Tag>
            ))}
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
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

/**
 * The whole lane in view, and the controls that bring it back. The frame is
 * as tall as the lane at the zoom its width allows (`ProcessFlow`), so that
 * zoom, centred across and `PAD` from the top, shows every card, move and
 * label. React Flow's own fit frames the cards alone, which left a stack of
 * words under the last row and the controls over a card (quote lane,
 * 2026-10-24). Set again whenever the lane or the frame changes size, and by
 * "Xem cả quy trình".
 */
function LaneViewport({ x, zoom }: { x: number; zoom: number }) {
  const { setViewport } = useReactFlow();
  const ready = useStore((state) => state.panZoom !== null);
  const show = useCallback(() => {
    void setViewport({ x, y: PAD, zoom });
  }, [setViewport, x, zoom]);
  useEffect(() => {
    if (ready) show();
  }, [ready, show]);
  return (
    <Controls
      showInteractive={false}
      position="bottom-right"
      onFitView={show}
    />
  );
}

/** A move's words as the canvas writes them, and as the geometry sizes them. */
function wordsOf(move: Move): MoveWords {
  return {
    action: EDGE_ACTION[move.action] ?? move.action,
    guards: move.guards.map((g) => EDGE_GUARD[g] ?? g),
  };
}

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
  // Each card's size once React Flow has measured it. The nodes are
  // controlled, so the size goes back on each node as `measured`: a node
  // rebuilt without it reads to React Flow as never measured, and it then
  // held every fitView until a measurement that never came, because the
  // card's size had not changed (2026-10-24).
  const [sizes, setSizes] = useState<Record<string, Dimensions>>({});
  const onNodesChange = useCallback((changes: NodeChange<StatusNode>[]) => {
    setSizes((before) => {
      let next = before;
      for (const change of changes)
        if (
          change.type === "dimensions" &&
          change.dimensions &&
          (before[change.id]?.width !== change.dimensions.width ||
            before[change.id]?.height !== change.dimensions.height)
        )
          next = { ...next, [change.id]: change.dimensions };
      return next;
    });
  }, []);

  const geometry = useMemo(
    () =>
      laneGeometry(
        layout,
        wordsOf,
        Object.fromEntries(
          Object.entries(sizes).map(([id, size]) => [id, size.height]),
        ),
      ),
    [layout, sizes],
  );

  // The canvas is as tall as the fitted lane at the frame's width.
  const frame = useRef<HTMLDivElement>(null);
  const [frameWidth, setFrameWidth] = useState(0);
  useLayoutEffect(() => {
    const element = frame.current;
    if (!element) return;
    const read = () => setFrameWidth(element.clientWidth);
    read();
    const observer = new ResizeObserver(read);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const zoom = frameWidth
    ? Math.min(
        1,
        Math.max(MIN_FIT_ZOOM, (frameWidth - 2 * PAD) / geometry.width),
      )
    : 1;

  // In drawing order, column by column, so Tab follows what is drawn.
  const nodes = useMemo<StatusNode[]>(
    () =>
      inColumnOrder(layout).map((n) => {
        const box = geometry.cards[n.status]!;
        return {
          id: n.status,
          type: "status",
          position: { x: box.x, y: box.y },
          data: { card: cards[n.status]!, onOpen },
          initialWidth: CARD_W,
          initialHeight: box.h,
          measured: sizes[n.status],
          handles: handlesFor(box.h),
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
    [layout, cards, onOpen, geometry, sizes],
  );

  const edges = useMemo<MoveEdge[]>(
    () =>
      geometry.moves.map(({ id: moveId, move, back, points, label }) => {
        const words = wordsOf(move);
        return {
          id: moveId,
          type: "move",
          source: move.from,
          target: move.to,
          sourceHandle: "out",
          targetHandle: "in",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: token.colorTextTertiary,
          },
          data: { back, points, label, ...words },
          ariaLabel: [
            `${cards[move.from]?.label ?? move.from} → ${cards[move.to]?.label ?? move.to}`,
            `${words.action} (${MOVE_ACTOR[move.actor] ?? move.actor})`,
            ...(words.guards.length
              ? [`điều kiện: ${words.guards.join(", ")}`]
              : []),
            ...(back ? ["quay lại"] : []),
          ].join("; "),
          selectable: false,
          focusable: false,
        };
      }),
    [geometry, cards, token.colorTextTertiary],
  );

  return (
    <div className="space-y-2">
      <Typography.Paragraph className="mb-0!">
        Cả {layout.nodes.length} trạng thái vừa khung, đọc từ trái sang phải,
        hết hàng thì xuống hàng dưới; phóng to, thu nhỏ hoặc xem cả quy trình
        bằng các nút ở góc. Mũi tên nét đứt là đường quay lại.
      </Typography.Paragraph>
      <div
        ref={frame}
        style={{
          height: Math.ceil(geometry.height * zoom) + 2 * PAD,
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
          <LaneViewport
            x={Math.max(0, (frameWidth - geometry.width * zoom) / 2)}
            zoom={zoom}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
