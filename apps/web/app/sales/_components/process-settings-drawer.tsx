"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Alert, Button, Card, Drawer, Empty, Tooltip, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
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
import {
  ProposeDrawer,
  useConfirmDiscard,
  type StepScope,
} from "./rule-editor";

type Setting = SalesSchemas["SettingView"];
type RulesView = SalesSchemas["RulesInForceView"];

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
      size="min(720px, 100vw)"
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
