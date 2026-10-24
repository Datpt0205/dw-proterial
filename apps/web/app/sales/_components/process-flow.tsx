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
import Link from "next/link";
import {
  FlagOutlined,
  LockOutlined,
  RobotOutlined,
  UserOutlined,
} from "@ant-design/icons";
import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MarkerType,
  MiniMap,
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
import {
  Button,
  Card,
  Popover,
  Switch,
  Tag,
  theme,
  Tooltip,
  Typography,
} from "antd";
import {
  EDGE_ACTION,
  EDGE_GUARD,
  MOVE_ACTOR,
  NO_HOLDER,
  TIME_BUCKET,
} from "../_lib/labels";
import type { LaneLayout, Move } from "../_lib/process-graph";
import {
  CARD_W,
  laneGeometry,
  LOCK,
  pathOf,
  PILL_PAD,
  type Box,
  type Curve,
  type MoveKind,
  type MoveWords,
} from "../_lib/process-geometry";
import {
  openHere,
  StatusFacts,
  StepTags,
  type StatusCard,
} from "./process-map";
import { AiStateTag } from "./tags";

/**
 * A lane of the DW1 process on a wide screen, drawn with React Flow
 * (`@xyflow/react`, Đạt's decision of 2026-10-23 recorded in CLAUDE.md "Web
 * UI": the one library besides antd, and this the one file allowed to import
 * it; `lib/__tests__/antd-only.test.ts` fails any other). The page loads this
 * file lazily (`next/dynamic`), so a phone, which draws the list, never
 * downloads it.
 *
 * The canvas only draws: what is a status, a move, a way back and the main
 * path is `process-graph.ts`'s reading of the API's lane, and where each
 * tile, line and label sits is `process-geometry.ts` (the main path in one
 * row, every other status below it, skips arched over the row, labels that
 * never cover a tile or each other and lines that cross neither). Each
 * tile's measured height feeds the geometry again.
 *
 * The look is n8n's canvas (Đạt, 2026-10-24, made calm the same day): a
 * dotted background, a minimap, each status a compact tile (an icon for
 * whose turn it is, its name, its step codes, one line of AI state), moves
 * as curves with arrowheads and only their action in a small pill; a guarded
 * move's pill carries one lock whose tooltip lists the guards. The ways back
 * and the exits are drawn, dashed, only when "Hiện đường quay lại" is on
 * (`?back=1`, so a link keeps it); off, the tiles' details say them. What the
 * list card writes besides (whose turn, settings, the ways back, where a
 * final status is reached from) is the tile's details: a popover on hover
 * and on keyboard focus (ui-quality §3: hover is a bonus), and the drawer on
 * a click or Enter. The row opens at a readable zoom from its start and pans
 * where it is wider than the frame; "Xem cả quy trình" fits all of it.
 *
 * Nothing on the canvas is dragged, selected or connected. The tile's link is
 * the focus stop (Tab, Enter opens the drawer, a middle click a new tab);
 * zoom is the controls, Ctrl + wheel or a pinch, so the wheel still scrolls
 * the page.
 */

const PAD = 16;
/**
 * The least zoom the lane opens at: below it, tiles' words stop being
 * legible, so a wider row opens at it, from its start, and pans.
 */
const MIN_FIT_ZOOM = 0.85;
/** The minimap's size; the strip under the lane holds it and the controls. */
const MINIMAP = { width: 160, height: 80 } as const;
/** React Flow's own margin round a panel (its stylesheet's `.react-flow__panel`). */
const PANEL_MARGIN = 15;
const FOOTER = MINIMAP.height + 2 * PANEL_MARGIN;
/** The tile's details: wide enough for a status's ways back on few lines. */
const DETAILS_W = 300;

interface StatusData extends Record<string, unknown> {
  card: StatusCard;
  onOpen: (item: string) => void;
  /** Whether a drawn line enters the tile's left side, and leaves its right. */
  entered: boolean;
  left: boolean;
}
interface MoveData extends Record<string, unknown> {
  kind: MoveKind;
  curve: Curve;
  label: Box | null;
  action: string;
  guards: string[];
}
type StatusNode = Node<StatusData, "status">;
type MoveEdge = Edge<MoveData, "move">;

/** Whose turn a case in the status is, as the tile draws it. */
type Turn = "dw" | "person" | "done";
const turnOf = (holder: StatusCard["holderKey"]): Turn =>
  holder === null ? "done" : holder === "dw" ? "dw" : "person";
const TURN_ICON = {
  dw: RobotOutlined,
  person: UserOutlined,
  done: FlagOutlined,
} as const;
/** The icons' meaning, said once above the canvas. */
const TURN_LEGEND: Record<Turn, string> = {
  dw: TIME_BUCKET.dw,
  person: "Đến lượt người làm",
  done: NO_HOLDER,
};

/** An icon's look per turn: the theme's colours, never colour alone. */
function useTurnLook(): Record<Turn, CSSProperties> {
  const { token } = theme.useToken();
  return {
    dw: { color: token.colorPrimary, background: token.colorPrimaryBg },
    person: { color: token.colorText, background: token.colorFillTertiary },
    done: {
      color: token.colorTextSecondary,
      background: token.colorFillQuaternary,
    },
  };
}

/**
 * A status as an n8n-like tile, in the real link to its drawer. The icon says
 * whose turn it is (its meaning is the legend's words, so the icon is hidden
 * from a screen reader); the details open on hover and focus, and close on
 * Esc, on leaving, and when the tile opens its drawer, so they never float
 * over it. While open they describe the link (`aria-describedby`).
 */
function StatusTile({
  card,
  onOpen,
}: {
  card: StatusCard;
  onOpen: (item: string) => void;
}) {
  const { token } = theme.useToken();
  const look = useTurnLook();
  const [details, setDetails] = useState(false);
  const turn = turnOf(card.holderKey);
  const Icon = TURN_ICON[turn];
  return (
    <Popover
      open={details}
      onOpenChange={setDetails}
      trigger={["hover", "focus"]}
      placement="bottom"
      title={card.label}
      content={
        <div
          data-details={card.item}
          className="flex flex-col items-start gap-1"
          style={{ maxWidth: DETAILS_W }}
        >
          <StepTags steps={card.steps} />
          <StatusFacts card={card} />
          <span>Bấm hoặc nhấn Enter để mở thiết lập.</span>
        </div>
      }
    >
      <Link
        href={card.href}
        scroll={false}
        data-node={card.item}
        data-status={card.status}
        data-turn={turn}
        className="block"
        style={{ color: token.colorText }}
        onClick={(event) => {
          setDetails(false);
          openHere(event, () => onOpen(card.item));
        }}
      >
        <Card
          size="small"
          hoverable
          style={turn === "dw" ? { borderColor: token.colorPrimaryBorder } : {}}
        >
          {/* The name comes first in the link's name; the icon row is drawn
              above it. */}
          <span className="flex flex-col items-start gap-2">
            <Typography.Text strong className="order-2">
              {card.label}
            </Typography.Text>
            <span className="order-1 flex w-full items-start justify-between gap-2">
              <span
                aria-hidden
                className="flex shrink-0 items-center justify-center"
                style={{
                  ...look[turn],
                  width: token.controlHeightLG,
                  height: token.controlHeightLG,
                  borderRadius: token.borderRadiusLG,
                  fontSize: token.fontSizeHeading3,
                }}
              >
                <Icon />
              </span>
              {card.steps.length ? (
                <span className="flex flex-wrap justify-end gap-1">
                  {card.steps.map((s) => (
                    <Tag key={s.step_id} className="me-0">
                      {s.step_id}
                    </Tag>
                  ))}
                </span>
              ) : null}
            </span>
            {card.ai.length ? (
              <span className="order-3 flex flex-wrap gap-1">
                {card.ai.map((a) => (
                  <AiStateTag key={a.state} state={a.state} short />
                ))}
              </span>
            ) : null}
          </span>
        </Card>
      </Link>
    </Popover>
  );
}

/**
 * The tile, with a visible handle on each side a drawn line meets there (a
 * line meeting its top or bottom has none, as in n8n). Every tile has both
 * handles, since React Flow draws no edge without them; an unused one is
 * hidden (`data-shown`), and every line is the geometry's own curve.
 */
function StatusNodeView({ data }: NodeProps<StatusNode>) {
  const { token } = theme.useToken();
  // Above the tile, which comes after it and would paint over it.
  const handle = (shown: boolean): CSSProperties => ({
    zIndex: 1,
    width: token.sizeSM,
    height: token.sizeSM,
    background: token.colorBgContainer,
    border: `${token.lineWidthBold}px solid ${token.colorTextTertiary}`,
    pointerEvents: "none",
    visibility: shown ? "visible" : "hidden",
  });
  return (
    <div style={{ width: CARD_W }}>
      <Handle
        id="in"
        type="target"
        position={Position.Left}
        isConnectable={false}
        data-shown={data.entered}
        style={handle(data.entered)}
      />
      <Handle
        id="out"
        type="source"
        position={Position.Right}
        isConnectable={false}
        data-shown={data.left}
        style={handle(data.left)}
      />
      <StatusTile card={data.card} onOpen={data.onOpen} />
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

/**
 * A guarded move's one lock: its accessible name and its tooltip list the
 * guards in words; the drawer says the whole move.
 */
function GuardLock({ guards }: { guards: string[] }) {
  return (
    <Tooltip
      trigger={["hover", "focus"]}
      title={
        <span className="flex flex-col">
          <span>Điều kiện:</span>
          {guards.map((guard) => (
            <span key={guard}>• {guard}</span>
          ))}
        </span>
      }
    >
      <Button
        type="text"
        size="small"
        icon={<LockOutlined />}
        aria-label={`Điều kiện: ${guards.join("; ")}`}
        className="nodrag nopan shrink-0"
        style={{ width: LOCK.size, minWidth: LOCK.size, pointerEvents: "all" }}
      />
    </Tooltip>
  );
}

/**
 * A move: the geometry's curve, dashed for a way back or an exit, and its
 * action in a pill inside the box placed for it, with the lock of a guarded
 * move.
 */
function MoveEdgeView({ id, markerEnd, data }: EdgeProps<MoveEdge>) {
  const { token } = theme.useToken();
  if (!data) return null;
  const { label } = data;
  return (
    <>
      <BaseEdge
        id={id}
        path={pathOf(data.curve)}
        markerEnd={markerEnd}
        style={{
          stroke: token.colorTextTertiary,
          strokeWidth: 1.5,
          strokeDasharray: data.kind === "forward" ? undefined : "6 4",
        }}
      />
      {label ? (
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
              className="flex items-center text-center"
              style={{
                maxWidth: "100%",
                gap: LOCK.gap,
                padding: `${PILL_PAD.y}px ${PILL_PAD.x}px`,
                background: token.colorBgContainer,
                border: `${token.lineWidth}px solid ${token.colorBorderSecondary}`,
                borderRadius: token.borderRadiusLG,
                color: token.colorText,
                fontSize: token.fontSizeSM,
                lineHeight: token.lineHeightSM,
              }}
            >
              <span style={{ textWrap: "balance" }}>{data.action}</span>
              {data.guards.length ? <GuardLock guards={data.guards} /> : null}
            </div>
          </div>
        </EdgeLabelRenderer>
      ) : null}
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
  "minimap.ariaLabel": "Bản đồ thu nhỏ của quy trình",
};

/** Where the canvas looks: its pan and its zoom. */
interface View {
  x: number;
  y: number;
  zoom: number;
}

/**
 * The lane in view, and the controls. The frame is as tall as the lane at the
 * zoom it opens at, plus a strip under it for the controls and the minimap
 * (`ProcessFlow`), so no tile or label is ever under a panel. The lane opens
 * at `start` (the whole row when it fits at a readable zoom, else its start
 * at `MIN_FIT_ZOOM`, to pan from), set again whenever the lane or the frame
 * changes size; "Xem cả quy trình" shows `whole`, all of it at whatever zoom
 * that takes. React Flow's own fit frames the tiles alone, which left words
 * under the controls (quote lane, 2026-10-24).
 */
function LaneViewport({ start, whole }: { start: View; whole: View }) {
  const { setViewport } = useReactFlow();
  const ready = useStore((state) => state.panZoom !== null);
  const { x, y, zoom } = start;
  useEffect(() => {
    if (ready) void setViewport({ x, y, zoom });
  }, [ready, setViewport, x, y, zoom]);
  return (
    <Controls
      showInteractive={false}
      position="bottom-left"
      orientation="horizontal"
      onFitView={() => void setViewport(whole)}
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

/** What the tiles' icons mean, in words. */
function TurnLegend() {
  const look = useTurnLook();
  return (
    <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
      {(Object.keys(TURN_ICON) as Turn[]).map((turn) => {
        const Icon = TURN_ICON[turn];
        return (
          <span key={turn} className="flex items-center gap-1">
            <Icon aria-hidden style={{ color: look[turn].color }} />
            {TURN_LEGEND[turn]}
          </span>
        );
      })}
    </span>
  );
}

export function ProcessFlow({
  id,
  name,
  layout,
  cards,
  onOpen,
  showBack,
  onShowBack,
}: {
  /** Unique on the page: React Flow keys its markers by it. */
  id: string;
  /** The lane's name, for the canvas's accessible name. */
  name: string;
  layout: LaneLayout;
  cards: Record<string, StatusCard>;
  onOpen: (item: string) => void;
  /** Whether the ways back and the exits are drawn (the page's `?back=1`). */
  showBack: boolean;
  onShowBack: (show: boolean) => void;
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
        showBack,
      ),
    [layout, sizes, showBack],
  );

  // The canvas is as tall as the lane at the zoom it opens at.
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
  const across = frameWidth ? (frameWidth - 2 * PAD) / geometry.width : 1;
  const zoom = Math.min(1, Math.max(MIN_FIT_ZOOM, across));
  const frameHeight = Math.ceil(geometry.height * zoom) + PAD + FOOTER;
  const centred = (z: number) =>
    Math.max(PAD, (frameWidth - geometry.width * z) / 2);
  const wholeZoom = Math.min(
    1,
    across,
    (frameHeight - PAD - FOOTER) / geometry.height,
  );

  // The row left to right, then the statuses below it, so Tab follows what
  // is drawn.
  const nodes = useMemo<StatusNode[]>(() => {
    const side = (route: string) => route === "next" || route === "rail";
    const entered = new Set(
      geometry.moves.filter((m) => side(m.route)).map((m) => m.move.to),
    );
    const left = new Set(
      geometry.moves.filter((m) => side(m.route)).map((m) => m.move.from),
    );
    return Object.entries(geometry.cards)
      .sort(
        ([a, p], [b, q]) => geometry.rows[a]! - geometry.rows[b]! || p.x - q.x,
      )
      .map(([status, box]) => ({
        id: status,
        type: "status",
        position: { x: box.x, y: box.y },
        data: {
          card: cards[status]!,
          onOpen,
          entered: entered.has(status),
          left: left.has(status),
        },
        initialWidth: CARD_W,
        initialHeight: box.h,
        measured: sizes[status],
        handles: handlesFor(box.h),
        draggable: false,
        selectable: false,
        connectable: false,
        focusable: false,
        // Not selectable or draggable, React Flow would let clicks through
        // to the canvas; the tile's link takes them. A drag from a tile does
        // not pan: the tile is for opening.
        className: "nopan",
        style: { pointerEvents: "all" },
      }));
  }, [cards, onOpen, geometry, sizes]);

  const edges = useMemo<MoveEdge[]>(
    () =>
      geometry.moves.map(({ id: moveId, move, kind, curve, label }) => {
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
          data: { kind, curve, label, ...words },
          ariaLabel: [
            `${cards[move.from]?.label ?? move.from} → ${cards[move.to]?.label ?? move.to}`,
            `${words.action} (${MOVE_ACTOR[move.actor] ?? move.actor})`,
            ...(words.guards.length
              ? [`điều kiện: ${words.guards.join(", ")}`]
              : []),
            ...(kind === "back" ? ["quay lại"] : []),
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
        Đường chính của hồ sơ đọc từ trái sang phải; các trạng thái rẽ nhánh nằm
        ở hàng dưới. Kéo để xem tiếp, hoặc bấm “Xem cả quy trình” ở góc dưới.
        Đưa chuột hoặc dùng Tab tới một trạng thái để xem đến lượt ai, số thiết
        lập và đường quay lại; bấm hoặc nhấn Enter để mở thiết lập. Biểu tượng
        khóa trên một bước chuyển là điều kiện của bước đó.
      </Typography.Paragraph>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <TurnLegend />
        <label className="flex items-center gap-2">
          <Switch checked={showBack} onChange={onShowBack} />
          <span>Hiện đường quay lại</span>
          {showBack ? <span>(nét đứt: quay lại và đóng hồ sơ)</span> : null}
        </label>
      </div>
      <div
        ref={frame}
        style={{
          height: frameHeight,
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
          minZoom={0.3}
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
          attributionPosition="bottom-center"
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
              "--xy-minimap-background-color": token.colorBgContainer,
              "--xy-minimap-mask-background-color": token.colorFillTertiary,
              "--xy-minimap-mask-stroke-color": token.colorBorder,
              "--xy-minimap-node-background-color": token.colorBorder,
              "--xy-minimap-node-stroke-color": token.colorBorder,
              "--xy-attribution-background-color": token.colorBgContainer,
            } as CSSProperties
          }
        >
          <Background
            variant={BackgroundVariant.Dots}
            gap={token.sizeLG}
            size={token.lineWidthBold}
            color={token.colorBorder}
          />
          <MiniMap
            position="bottom-right"
            pannable
            nodeBorderRadius={token.borderRadiusSM}
            style={{
              width: MINIMAP.width,
              height: MINIMAP.height,
              borderRadius: token.borderRadius,
              border: `1px solid ${token.colorBorderSecondary}`,
            }}
          />
          <LaneViewport
            start={{
              x: across >= MIN_FIT_ZOOM ? centred(zoom) : PAD,
              y: PAD,
              zoom,
            }}
            whole={{
              x: centred(wholeZoom),
              // In the middle of the frame above the controls' strip.
              y: Math.max(
                PAD,
                (frameHeight - FOOTER - geometry.height * wholeZoom) / 2,
              ),
              zoom: wholeZoom,
            }}
          />
        </ReactFlow>
      </div>
    </div>
  );
}
