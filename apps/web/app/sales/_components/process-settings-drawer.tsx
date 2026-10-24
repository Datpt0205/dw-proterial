"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Grid,
  Tooltip,
  Typography,
} from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime } from "../../../lib/dates";
import { formatShare } from "../../../lib/money";
import { aiState, modelStepLabel } from "../_lib/activity";
import { LIST_NAME, TAB_OF } from "../_lib/catalog";
import { usePeople } from "../_lib/people";
import {
  RULE_KEY,
  waitingNotice,
  waitingVersion,
  type RuleKey,
} from "../_lib/rules";
import { lockReason } from "../_lib/rule-labels";
import { parseLoc } from "../_lib/rule-schema";
import type { Resource } from "../_lib/use-resource";
import { StepTags } from "./process-map";
import { AiStateTag } from "./tags";
import {
  ProposeDrawer,
  useConfirmDiscard,
  type StepScope,
} from "./rule-editor";

type Setting = SalesSchemas["SettingView"];
type RulesView = SalesSchemas["RulesInForceView"];
type StepModel = SalesSchemas["StepModelView"];
type Uses = SalesSchemas["UsesView"];
type Actor = SalesSchemas["ActorView"];

/** Who may change who holds a role: the tenant's members page (`/admin`). */
const MEMBERS_WRITE = "platform.members.write";

/** What a status, a step, a lane or the whole process opens, in words. */
export interface SettingsTarget {
  /** "Đơn hàng · Chờ PIC tự kiểm". */
  title: string;
  /** Whose turn a case in the status is; absent where no status is open. */
  holder?: string;
  steps: { step_id: string; coverage: string }[];
  /** Status labels it may move on to, back to, and (a final one) be reached from. */
  next?: string[];
  back?: string[];
  exitsFrom?: string[];
  settings: Setting[];
  /** The model steps of its steps; empty when the server sent none. */
  models?: StepModel[];
  /** What its steps read besides rules; absent where no step is open. */
  uses?: Uses;
  /** Who performs or approves its steps' actions. */
  actors?: Actor[];
}

/**
 * One status's (or step's, lane's, the process's) settings, per rule key:
 * each key opens the rules editor limited to these fields, locked fields
 * drawn with why. A key is one proposal and one approval, so a status that
 * reads two keys is two separate approvals, and either applies only to the
 * cases checked after it is approved (rules are stamped per case).
 *
 * The editor open is in the URL (`edit`), so Back closes the editor before
 * the drawer. Back with unsent changes puts the editor back and asks first,
 * the same question its own close asks (ui-quality §9).
 */
export function ProcessSettingsDrawer({
  target,
  open,
  rules,
  editing,
  onEdit,
  onEditClose,
  onClose,
  afterClose,
}: {
  target: SettingsTarget;
  /** Kept mounted while closed, so it closes as a drawer and focus returns. */
  open: boolean;
  rules: Resource<RulesView>;
  /** The key whose editor the URL opens. */
  editing: RuleKey | null;
  onEdit: (key: RuleKey) => void;
  onEditClose: () => void;
  onClose: () => void;
  afterClose: () => void;
}) {
  const name = usePeople();
  const discard = useConfirmDiscard();
  // A bottom sheet on a phone (ui-quality §9); from the right from md up,
  // and while the breakpoint is not known yet.
  const phone = Grid.useBreakpoint().md === false;
  const byKey = new Map<RuleKey, Setting[]>();
  for (const s of target.settings)
    byKey.set(s.key, [...(byKey.get(s.key) ?? []), s]);
  const asked = editing && byKey.has(editing) ? editing : null;

  // The editor mounted: the URL's, or the one Back just took out of the URL
  // while it held unsent changes.
  const [held, setHeld] = useState<RuleKey | null>(asked);
  const touched = useRef(false);
  const leaving = useRef(false);
  useEffect(() => {
    if (asked) {
      leaving.current = false;
      setHeld(asked);
      return;
    }
    if (!held) return;
    if (touched.current && !leaving.current) {
      onEdit(held);
      discard(() => {
        leaving.current = true;
        onEditClose();
      });
      return;
    }
    touched.current = false;
    setHeld(null);
    // Only a change of the URL's key decides this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [asked]);
  const leave = () => {
    leaving.current = true;
    onEditClose();
  };

  const scope = (key: RuleKey): StepScope => {
    const settings = byKey.get(key) ?? [];
    return {
      label: target.title,
      only: settings.map((s) => parseLoc(s.path)),
      locked: settings.flatMap((s) =>
        s.lock ? [{ path: parseLoc(s.path), reason: lockReason(s.lock) }] : [],
      ),
    };
  };
  const line = (lead: string, list: string[] | undefined) =>
    list?.length ? (
      <Typography.Paragraph className="mb-1!">
        {lead}: {list.join(", ")}
      </Typography.Paragraph>
    ) : null;

  return (
    <Drawer
      open={open}
      onClose={onClose}
      afterOpenChange={(opened) => {
        if (!opened) afterClose();
      }}
      placement={phone ? "bottom" : "right"}
      size={phone ? "88vh" : "min(720px, 100vw)"}
      title={target.title}
    >
      <div className="space-y-4">
        <div>
          {target.steps.length ? (
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span>Bước khảo sát:</span>
              <StepTags steps={target.steps} />
            </div>
          ) : null}
          {target.holder ? line("Đến lượt", [target.holder]) : null}
          {line("Chuyển tiếp sang", target.next)}
          {line("Có thể quay lại", target.back)}
          {line("Có thể đóng từ", target.exitsFrom)}
        </div>
        {target.models?.length ? <ModelSection models={target.models} /> : null}
        <Alert
          type="info"
          showIcon
          title="Thay đổi chỉ áp dụng cho hồ sơ được kiểm sau khi phiên bản mới được duyệt."
          description="Hồ sơ đã kiểm giữ phiên bản quy tắc đã ghi trên hồ sơ. Mỗi quy tắc là một đề xuất và một lần duyệt riêng: sửa hai quy tắc dưới đây là hai đề xuất, được duyệt riêng, không cùng lúc."
        />
        {rules.error ? (
          <LoadError error={rules.error} onRetry={rules.reload} compact />
        ) : null}
        {byKey.size ? (
          [...byKey].map(([key, settings]) => {
            const locked = settings.filter((s) => s.lock).length;
            const waiting = rules.data
              ? waitingVersion(rules.data, key)
              : undefined;
            const notice = waiting
              ? waitingNotice(waiting, name(waiting.proposed_by))
              : null;
            return (
              <Card key={key} size="small" title={RULE_KEY[key]}>
                <Typography.Paragraph className="mb-2!">
                  {settings.length} trường ở đây
                  {locked ? `, ${locked} trường chỉ xem` : ""}.
                </Typography.Paragraph>
                {waiting && notice ? (
                  <Alert
                    className="mb-2"
                    type="warning"
                    showIcon
                    title={notice.title}
                    description={notice.description}
                    action={
                      waiting.approval_id ? (
                        <Link href={`/approvals/${waiting.approval_id}`}>
                          Mở yêu cầu duyệt
                        </Link>
                      ) : null
                    }
                  />
                ) : null}
                {/* The editor starts from the versions `/rules` lists. */}
                <Tooltip
                  title={
                    rules.error
                      ? "Chưa tải được các phiên bản của quy tắc: bấm Thử lại ở trên."
                      : undefined
                  }
                >
                  <Button
                    onClick={() => onEdit(key)}
                    loading={rules.loading}
                    disabled={!rules.data}
                    aria-label={`Xem và đề xuất thay đổi: ${RULE_KEY[key]}`}
                  >
                    Xem và đề xuất thay đổi
                  </Button>
                </Tooltip>
              </Card>
            );
          })
        ) : (
          <Empty
            description={
              target.steps.length
                ? "Bước ở đây không đọc quy tắc nào trang này cho sửa."
                : "Không có thiết lập nào ở đây."
            }
          />
        )}
        {target.uses ? <UsesSection uses={target.uses} /> : null}
        {target.actors && target.steps.length ? (
          <ActorsSection actors={target.actors} />
        ) : null}
      </div>
      {open && held && rules.data ? (
        <ProposeDrawer
          ruleKey={held}
          view={rules.data}
          scope={scope(held)}
          touched={touched}
          onClose={leave}
          onProposed={() => {
            leave();
            rules.reload();
          }}
          onHeld={rules.reload}
        />
      ) : null}
    </Drawer>
  );
}

/**
 * "AI ở bước này": each model step's switch, its bar, its latest
 * measurement on the model and prompt it runs on now, whether the model is
 * used, and how much DW1 carried over the last week. Read-only: a version
 * that turns a step on is proposed on /sales/rules and refused unless the
 * latest measurement passes. Drawn only when the server sent model steps,
 * which it does only to someone who may read the order rules.
 */
function ModelSection({ models }: { models: StepModel[] }) {
  // Below sm the label goes above its value: beside it, a prompt id such as
  // sales.description_attributes@1.0.0 broke inside its version at 390 px.
  const screens = Grid.useBreakpoint();
  return (
    <Card size="small" title="AI ở bước này">
      <Typography.Paragraph>
        Chỉ xem. Một bước chỉ bật được khi lần đo gần nhất trên mô hình và lời
        nhắc đang dùng đạt điểm; khi đổi mô hình, FPT đo lại trước khi bật.
      </Typography.Paragraph>
      <div className="space-y-4">
        {models.map((m) => (
          <section key={m.step} aria-label={modelStepLabel(m.step)}>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <Typography.Text strong>{modelStepLabel(m.step)}</Typography.Text>
              <AiStateTag state={aiState(m)} />
            </div>
            <Descriptions
              size="small"
              column={1}
              layout={screens.sm ? "horizontal" : "vertical"}
              items={[
                {
                  key: "switch",
                  label: "Công tắc",
                  children: m.enabled ? "Bật" : "Tắt",
                },
                // Two numbers on two scales, kept apart so neither reads as
                // the other's target (browser look, 2026-10-24): the bar is
                // measured on the golden set, the share on real work.
                {
                  key: "bar",
                  label: "Điểm đạt đo trên bộ thử",
                  children: (
                    <span className="flex flex-col">
                      <span>{formatShare(m.bar)}</span>
                      <Typography.Text type="secondary">
                        Chỉ số đo: {m.metric}
                      </Typography.Text>
                    </span>
                  ),
                },
                {
                  key: "live",
                  label: `Thực tế ${m.live_share.window_days} ngày`,
                  children: (
                    <span className="flex flex-col">
                      <span>
                        {m.live_share.share === null
                          ? "chưa có dữ liệu"
                          : `DW1 tự xử lý ${formatShare(m.live_share.share)} số mục (${m.live_share.automatic}/${m.live_share.handled})`}
                      </span>
                      <Typography.Text type="secondary">
                        Đếm trên việc thật, không cùng thước với điểm đạt.
                      </Typography.Text>
                    </span>
                  ),
                },
                {
                  key: "latest",
                  label: "Lần đo gần nhất",
                  children: m.latest ? (
                    <span className="flex flex-col">
                      <span>
                        {formatShare(m.latest.value)} ·{" "}
                        {m.latest.passed ? "đạt" : "chưa đạt"}
                      </span>
                      <Typography.Text type="secondary">
                        {m.latest.model} · {m.latest.prompt} ·{" "}
                        {formatDateTime(m.latest.measured_at)}
                      </Typography.Text>
                    </span>
                  ) : (
                    "Chưa đo"
                  ),
                },
                {
                  key: "effective",
                  label: "Hiệu lực",
                  children: m.effective
                    ? "Đang dùng mô hình"
                    : m.enabled
                      ? "Chưa dùng mô hình: lần đo chưa đạt, người làm bước này"
                      : "Tắt: người làm bước này",
                },
                {
                  key: "running",
                  label: "Đang chạy trên",
                  children: `${m.model ?? "Chưa xác định được mô hình"} · ${m.prompt}`,
                },
              ]}
            />
          </section>
        ))}
      </div>
    </Card>
  );
}

/** "Dữ liệu bước này dùng": the master-data lists and the PO layouts. */
function UsesSection({ uses }: { uses: Uses }) {
  const none = !uses.lists.length && !uses.layouts;
  return (
    <Card size="small" title="Dữ liệu bước này dùng">
      {none ? (
        <Typography.Text>
          Bước ở đây không đọc danh mục hay mẫu PO nào.
        </Typography.Text>
      ) : (
        <ul className="m-0 flex list-none flex-col gap-1 p-0">
          {uses.lists.map((list) => (
            <li key={list}>
              <Link href={`/sales/master-data?tab=${TAB_OF[list]}`}>
                {LIST_NAME[list] ?? list}
              </Link>
            </li>
          ))}
          {uses.layouts ? (
            <li>
              <Link href="/sales/layouts">Mẫu PO</Link>
            </li>
          ) : null}
        </ul>
      )}
    </Card>
  );
}

const ACTOR_KIND: Record<Actor["kind"], string> = {
  role: "Vai trò",
  permission_set: "Bộ quyền",
};

/** "Ai làm, ai duyệt": the roles and permission sets holding the steps' scopes. */
function ActorsSection({ actors }: { actors: Actor[] }) {
  const { hasScope } = useAuth();
  return (
    <Card size="small" title="Ai làm, ai duyệt">
      {actors.length ? (
        <ul className="m-0 flex list-none flex-col gap-2 p-0">
          {actors.map((a) => (
            <li key={`${a.kind}:${a.key}`} className="flex flex-col">
              <span>
                {ACTOR_KIND[a.kind]}: {a.name}
              </span>
              <Typography.Text type="secondary">
                Quyền: {a.scopes.join(", ")}
              </Typography.Text>
            </li>
          ))}
        </ul>
      ) : (
        <Typography.Text>
          Chưa vai trò hay bộ quyền nào giữ quyền của bước này.
        </Typography.Text>
      )}
      {hasScope(MEMBERS_WRITE) ? (
        <Typography.Paragraph className="mt-2 mb-0!">
          <Link href="/admin">
            Đổi người giữ vai trò ở trang Vai trò và quyền
          </Link>
        </Typography.Paragraph>
      ) : null}
    </Card>
  );
}
