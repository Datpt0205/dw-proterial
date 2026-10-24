"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Alert, Button, Grid, Skeleton, Tabs, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { PageHeader, RegionState } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { salesApi } from "../../_lib/api";
import {
  CASE_KIND,
  label,
  NO_HOLDER,
  ORDER_STATE,
  QUOTE_STATE,
  STEP_COVERAGE,
  TIME_BUCKET,
} from "../../_lib/labels";
import {
  layoutLane,
  type Lane,
  type LaneLayout,
} from "../../_lib/process-graph";
import { valueLabel } from "../../_lib/rule-labels";
import type { RuleKey } from "../../_lib/rules";
import { useResource } from "../../_lib/use-resource";
import { salesCrumbs } from "../../_components/crumbs";
import { aiState } from "../../_lib/activity";
import {
  ProcessList,
  type AiSummary,
  type StatusCard,
} from "../../_components/process-map";
import {
  ProcessSettingsDrawer,
  type SettingsTarget,
} from "../../_components/process-settings-drawer";
import { SCOPE } from "../../_components/sales-frame";
import { ScopeGate } from "../../_components/scope-gate";

/**
 * The canvas, loaded only where it is drawn (on `lg` and up): a phone draws
 * the list and never downloads React Flow (~56 kB gzipped).
 */
const ProcessFlow = dynamic(
  () => import("../../_components/process-flow").then((m) => m.ProcessFlow),
  { ssr: false, loading: () => <Skeleton active paragraph={{ rows: 8 }} /> },
);

type View = SalesSchemas["ProcessSettingsView"];
type Kind = Lane["kind"];
type Step = SalesSchemas["ProcessStepView"];
type Setting = SalesSchemas["SettingView"];
type StepModel = SalesSchemas["StepModelView"];
type Actor = SalesSchemas["ActorView"];

/**
 * Quy trình DW1 (2026-10-22, slice 1): the order and quote lanes as their
 * statuses and the moves between them, each status with the surveyed steps
 * a case is at there, whose turn it is, and the rule fields those steps
 * read. Opening a status shows its settings per rule key; each key opens the
 * rules editor (`rule-editor.tsx`) limited to those fields, which still
 * proposes the whole version for a second person to approve on `/approvals`.
 *
 * Everything drawn comes from `GET /sales/rules/process`: the statuses and
 * moves from the domain's tables, the placements from `process_settings.py`.
 * The page names no status and no setting of its own, and for a caller
 * without `sales.price.read` the server leaves the price-bearing keys out,
 * so the page never asks for them. Who may open it is the same as
 * `/sales/rules`: a holder of `sales.rules.propose`.
 *
 * Slices 2 and 3 (2026-10-23): on a wide screen the lane is a React Flow
 * canvas (`process-flow.tsx`) with every move labelled and the ways back
 * drawn; each status says whether its model steps run ("AI bật · đạt"), and
 * its drawer adds what the model steps measured and did, the data the steps
 * read, and who acts on them. The model steps come only to a caller who may
 * read the order rules that switch them; for anyone else the server sends
 * none and the page draws none.
 */
export default function ProcessPage() {
  return (
    <ScopeGate scope={SCOPE.rulesPropose}>
      <Suspense>
        <Process />
      </Suspense>
    </ScopeGate>
  );
}

/**
 * The open item and its open editor, in the URL: a link reopens them and Back
 * closes the editor, then the item (ui-quality §11).
 */
function useOpenItem() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  // A parameter opened here was pushed, so closing it goes back; one that
  // came with a link is replaced.
  const pushed = useRef(new Set<string>());
  const href = useCallback(
    (changes: Record<string, string | null>) => {
      const query = new URLSearchParams(params.toString());
      for (const [name, value] of Object.entries(changes))
        if (value) query.set(name, value);
        else query.delete(name);
      return `${pathname}${query.size ? `?${query}` : ""}`;
    },
    [params, pathname],
  );
  const opening = (name: string, changes: Record<string, string | null>) => {
    pushed.current.add(name);
    router.push(href(changes), { scroll: false });
  };
  const closing = (name: string, changes: Record<string, string | null>) => {
    if (pushed.current.delete(name)) router.back();
    else router.replace(href(changes), { scroll: false });
  };
  return {
    node: params.get("node"),
    edit: params.get("edit"),
    lane: params.get("lane"),
    hrefOf: useCallback((id: string) => href({ node: id, edit: null }), [href]),
    open: (id: string) => opening("node", { node: id, edit: null }),
    close: () => closing("node", { node: null, edit: null }),
    openEdit: (key: string) => opening("edit", { edit: key }),
    closeEdit: () => closing("edit", { edit: null }),
    setLane: (kind: string) =>
      router.replace(href({ lane: kind }), { scroll: false }),
  };
}

const PROCESS = "process";
// A button whose words may run past a phone's width: it wraps, left aligned,
// instead of pushing the page sideways (ui-quality §12).
const WRAPPING = "h-auto! justify-start! whitespace-normal! py-2! text-start";

const statusLabel = (kind: Kind, status: string) =>
  label(kind === "order" ? ORDER_STATE : QUOTE_STATE, status);

/** Each setting once, in the order first met. */
function distinct(settings: Setting[]): Setting[] {
  const seen = new Set<string>();
  return settings.filter((s) => {
    const id = `${s.key}:${s.path}`;
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

/** Each model step once, in the order first met. */
function distinctModels(steps: Step[]): StepModel[] {
  const seen = new Map<string, StepModel>();
  for (const m of steps.flatMap((s) => s.models))
    if (!seen.has(m.step)) seen.set(m.step, m);
  return [...seen.values()];
}

/** The lists the steps read, each once, and whether any reads PO layouts. */
function joinedUses(steps: Step[]): Step["uses"] {
  return {
    lists: [...new Set(steps.flatMap((s) => s.uses.lists))],
    layouts: steps.some((s) => s.uses.layouts),
  };
}

/** Each role and permission set once, with every scope it holds here. */
function joinedActors(steps: Step[]): Actor[] {
  const found = new Map<string, Actor>();
  for (const actor of steps.flatMap((s) => s.actors)) {
    const id = `${actor.kind}:${actor.key}`;
    const before = found.get(id);
    found.set(
      id,
      before
        ? {
            ...before,
            scopes: [...new Set([...before.scopes, ...actor.scopes])],
          }
        : actor,
    );
  }
  return [...found.values()];
}

/** A status's AI state, one entry per state its model steps are in. */
function aiSummary(models: StepModel[]): AiSummary[] {
  const counts = new Map<AiSummary["state"], number>();
  for (const m of models) {
    const state = aiState(m);
    counts.set(state, (counts.get(state) ?? 0) + 1);
  }
  return [...counts].map(([state, count]) => ({ state, count }));
}

/** What an item of the URL (`order.in_review`, `quote.Q8`, `order`, `process`) opens. */
function resolve(
  view: View,
  layouts: Map<Kind, LaneLayout>,
  steps: Map<string, Step>,
  id: string,
): SettingsTarget | null {
  if (id === PROCESS)
    return {
      title: "Thiết lập chung của quy trình",
      steps: [],
      settings: view.process_settings,
    };
  const dot = id.indexOf(".");
  const kind = dot < 0 ? id : id.slice(0, dot);
  const rest = dot < 0 ? "" : id.slice(dot + 1);
  const lane = view.lanes.find((l) => l.kind === kind);
  if (!lane) return null;
  const lanes = CASE_KIND[lane.kind];
  if (!rest)
    return {
      title: `${lanes} · Thiết lập của cả luồng`,
      steps: [],
      settings: view.lane_settings[lane.kind] ?? [],
    };
  const node = lane.nodes.find((n) => n.status === rest);
  const stepIds = node
    ? node.steps
    : lane.stateless_steps.includes(rest)
      ? [rest]
      : null;
  if (!stepIds) return null;
  const own = stepIds
    .map((s) => steps.get(s))
    .filter((s): s is Step => Boolean(s));
  const layout = layouts.get(lane.kind)!;
  const words = (list: string[] | undefined) =>
    (list ?? []).map((s) => statusLabel(lane.kind, s));
  return {
    title: node
      ? `${lanes} · ${statusLabel(lane.kind, rest)}`
      : `${lanes} · ${valueLabel(rest)}`,
    holder: node
      ? node.holder
        ? label(TIME_BUCKET, node.holder)
        : NO_HOLDER
      : undefined,
    steps: own.map((s) => ({
      step_id: s.step_id,
      coverage: label(STEP_COVERAGE, s.coverage),
    })),
    // On to: every move but the ways back, listed on their own.
    next: node
      ? words(
          (layout.next[rest] ?? []).filter(
            (s) => !(layout.back[rest] ?? []).includes(s),
          ),
        )
      : [],
    back: node ? words(layout.back[rest]) : [],
    exitsFrom: node ? words(layout.exitsFrom[rest]) : [],
    settings: distinct(own.flatMap((s) => s.settings)),
    models: distinctModels(own),
    uses: joinedUses(own),
    actors: joinedActors(own),
  };
}

function Process() {
  const process = useResource(
    "sales/rules/process",
    useCallback(() => salesApi().rulesProcess(), []),
  );
  const rules = useResource(
    "sales/rules",
    useCallback(() => salesApi().rules(), []),
  );
  const item = useOpenItem();
  const screens = Grid.useBreakpoint();
  const view = process.data;

  const layouts = useMemo(
    () => new Map((view?.lanes ?? []).map((l) => [l.kind, layoutLane(l)])),
    [view],
  );
  const steps = useMemo(
    () => new Map((view?.steps ?? []).map((s) => [s.step_id, s])),
    [view],
  );
  const target = useMemo(
    () => (view && item.node ? resolve(view, layouts, steps, item.node) : null),
    [view, layouts, steps, item.node],
  );
  // The drawer stays mounted once opened, so it closes as a drawer and gives
  // focus back to what opened it (ui-quality §3).
  const [shown, setShown] = useState<{
    id: string;
    target: SettingsTarget;
  } | null>(null);
  if (target && item.node && shown?.target !== target)
    setShown({ id: item.node, target });
  const active =
    view?.lanes.find((l) => l.kind === item.node?.split(".")[0])?.kind ??
    view?.lanes.find((l) => l.kind === item.lane)?.kind ??
    view?.lanes[0]?.kind;
  useEffect(() => {
    document.title = [
      "Quy trình DW1",
      target ? target.title : active ? CASE_KIND[active] : null,
      "Sales",
    ]
      .filter(Boolean)
      .join(" · ");
  }, [target, active]);

  const header = (
    <PageHeader
      breadcrumb={salesCrumbs(
        { title: "Quy tắc", href: "/sales/rules" },
        "Quy trình DW1",
      )}
      title="Quy trình DW1"
      subtitle="Các trạng thái của hồ sơ đơn hàng và báo giá, bước khảo sát ở mỗi trạng thái, và quy tắc bước đó đọc. Mở một trạng thái để xem và đề xuất thay đổi các trường của bước; người khác duyệt trên trang Duyệt."
    />
  );
  if (process.error)
    return (
      <div className="space-y-4">
        {header}
        <LoadError error={process.error} onRetry={process.reload} />
      </div>
    );
  if (!view)
    return (
      <div className="space-y-4">
        {header}
        <Skeleton active paragraph={{ rows: 8 }} />
      </div>
    );
  if (!view.lanes.length)
    return (
      <div className="space-y-4">
        {header}
        <RegionState
          kind="empty"
          description="Máy chủ chưa trả về quy trình nào."
        />
      </div>
    );

  return (
    <div className="space-y-4">
      {header}
      <Button
        block
        className={WRAPPING}
        data-node={PROCESS}
        onClick={() => item.open(PROCESS)}
      >
        <span>
          Thiết lập chung của quy trình · {view.process_settings.length} thiết
          lập
        </span>
      </Button>
      <Tabs
        activeKey={active}
        onChange={item.setLane}
        items={view.lanes.map((lane) => ({
          key: lane.kind,
          label: CASE_KIND[lane.kind],
          children: (
            <LaneView
              lane={lane}
              layout={layouts.get(lane.kind)!}
              steps={steps}
              laneSettings={view.lane_settings[lane.kind] ?? []}
              wide={Boolean(screens.lg)}
              hrefOf={item.hrefOf}
              onOpen={item.open}
            />
          ),
        }))}
      />
      {item.node && !target ? (
        <Alert
          type="warning"
          showIcon
          title="Liên kết trỏ tới một bước không còn trong quy trình."
          action={<Button onClick={item.close}>Đóng</Button>}
        />
      ) : null}
      {shown ? (
        <ProcessSettingsDrawer
          target={shown.target}
          open={Boolean(target)}
          rules={rules}
          editing={target ? (item.edit as RuleKey | null) : null}
          onEdit={item.openEdit}
          onEditClose={item.closeEdit}
          onClose={item.close}
          afterClose={() =>
            document
              .querySelector<HTMLElement>(`[data-node="${shown.id}"]`)
              ?.focus()
          }
        />
      ) : null}
    </div>
  );
}

function LaneView({
  lane,
  layout,
  steps,
  laneSettings,
  wide,
  hrefOf,
  onOpen,
}: {
  lane: Lane;
  layout: LaneLayout;
  steps: Map<string, Step>;
  laneSettings: Setting[];
  wide: boolean;
  hrefOf: (id: string) => string;
  onOpen: (id: string) => void;
}) {
  const count = (ids: string[]) =>
    distinct(ids.flatMap((id) => steps.get(id)?.settings ?? [])).length;
  const cards = useMemo<Record<string, StatusCard>>(() => {
    const settingsOf = (ids: string[]) =>
      distinct(ids.flatMap((id) => steps.get(id)?.settings ?? [])).length;
    const words = (list: string[] | undefined) =>
      (list ?? []).map((s) => statusLabel(lane.kind, s)).join(", ");
    return Object.fromEntries(
      lane.nodes.map((node) => {
        const own = node.steps
          .map((id) => steps.get(id))
          .filter((s): s is Step => Boolean(s));
        const item = `${lane.kind}.${node.status}`;
        return [
          node.status,
          {
            status: node.status,
            item,
            href: hrefOf(item),
            label: statusLabel(lane.kind, node.status),
            steps: own.map((s) => ({
              step_id: s.step_id,
              coverage: label(STEP_COVERAGE, s.coverage),
            })),
            holder: node.holder ? label(TIME_BUCKET, node.holder) : NO_HOLDER,
            settings: settingsOf(node.steps),
            ai: aiSummary(distinctModels(own)),
            back: words(layout.back[node.status]),
            exits: words(layout.exitsFrom[node.status]),
          },
        ];
      }),
    );
  }, [lane, layout, steps, hrefOf]);
  return (
    <div className="space-y-4">
      {wide ? (
        <ProcessFlow
          id={`process-${lane.kind}`}
          name={CASE_KIND[lane.kind]}
          layout={layout}
          cards={cards}
          onOpen={onOpen}
        />
      ) : (
        <ProcessList layout={layout} cards={cards} onOpen={onOpen} />
      )}
      {lane.stateless_steps.length ? (
        <section className="space-y-2">
          <Typography.Title level={5} className="mb-0!">
            Bước không gắn với trạng thái nào
          </Typography.Title>
          <div className="flex flex-col gap-2">
            {lane.stateless_steps.map((id) => {
              const item = `${lane.kind}.${id}`;
              return (
                <Button
                  key={id}
                  block
                  className={WRAPPING}
                  data-node={item}
                  onClick={() => onOpen(item)}
                >
                  <span className="flex flex-col items-start">
                    <span>{valueLabel(id)}</span>
                    <span>
                      {label(STEP_COVERAGE, steps.get(id)?.coverage)} ·{" "}
                      {count([id])} thiết lập
                    </span>
                  </span>
                </Button>
              );
            })}
          </div>
        </section>
      ) : null}
      <Button
        block
        className={WRAPPING}
        data-node={lane.kind}
        onClick={() => onOpen(lane.kind)}
      >
        <span>
          Thiết lập của cả luồng {CASE_KIND[lane.kind]} · {laneSettings.length}{" "}
          thiết lập
        </span>
      </Button>
    </div>
  );
}
