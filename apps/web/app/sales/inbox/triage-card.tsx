"use client";

import { useState } from "react";
import Link from "next/link";
import { Flex, Select, Space, Typography } from "antd";
import type { SalesSchemas } from "@dw/api-client";
import { StatusTag } from "@dw/ui";
import { useAuth } from "../../../lib/auth/auth-context";
import { formatDateTime } from "../../../lib/dates";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import {
  INTENT_KIND,
  intentKindLabel,
  label,
  SALES_ROLE,
} from "../_lib/labels";
import { messageRef } from "../_lib/messages";
import { usePeople } from "../_lib/people";
import type { Skill, SkillVersion } from "../_lib/skills";
import { useAction } from "../_lib/use-action";
import { GuardedButton } from "../_components/guarded-button";
import { ProposeSkill } from "../_components/propose-skill";
import { SCOPE } from "../_components/sales-frame";

/** Who may teach DW1 a mail kind: whoever proposes rules (ticket 34). */
export const NO_TEACH = `Chỉ ${label(SALES_ROLE, "sales_head")} hoặc ${label(SALES_ROLE, "sales_rules_editor")} dạy được DW1 loại thư.`;

type Message = SalesSchemas["InboxMessageView"];
type Card = NonNullable<SalesSchemas["MessageDispositionView"]["triage"]>;
type Step = NonNullable<Card["step"]>;

/** The PICs' pool, as a routed message names it (`SALES_PIC_POOL`). */
const POOL = "role:sales_pic";
/** The steps a card may lead to, the closed set (`domain.triage.TriageStep`). */
const STEPS: readonly Step[] = [
  "reply_to_case",
  "delivery_change",
  "complaint",
  "sample_request",
  "portal_notice",
];
const DECIDED: Record<NonNullable<Card["decided"]>["decision"], string> = {
  taken: "Đã làm theo gợi ý",
  changed: "Đã chọn bước khác",
  dismissed: "Đã bỏ qua gợi ý",
};
/** The skill a card reads with, and the one taught from it (ticket 34). */
const MAIL_KINDS = "mail-kinds";

/**
 * Thẻ gợi ý (ticket 33): a mail routed "Khác" that nothing read, with what
 * DW1 thinks it is, the case of the sender's own customer it seems to
 * concern, and one step. Advice: the mail stays where it is until a person
 * takes the step, picks another or dismisses the card; the server checks
 * who may and moves it only within the closed set, to the card's own case.
 * "Dạy DW1 loại thư này" (ticket 34) proposes a version of the mail kinds
 * from this mail, which the head approves after a replay that reads it.
 */
export function TriageCardPanel({
  message,
  onChanged,
}: {
  message: Message;
  onChanged: () => void;
}) {
  const card = message.disposition.triage!;
  const { hasScope, email } = useAuth();
  const name = usePeople();
  const { run, pending } = useAction();
  const [error, setError] = useState<unknown>(null);
  const [other, setOther] = useState<Step | null>(null);
  const [teaching, setTeaching] = useState<{
    skill: Skill;
    versions: SkillVersion[];
  } | null>(null);
  const [loadingSkill, setLoadingSkill] = useState(false);
  const ref = messageRef(message.message_id);
  const owner = (message.disposition.owner ?? "").toLowerCase();
  const allowed =
    (hasScope(SCOPE.inbox) &&
      (owner === POOL || owner === (email ?? "").toLowerCase())) ||
    hasScope(SCOPE.assign);
  const reason = allowed
    ? null
    : `Thư này giao cho người khác: người phụ trách hoặc ${label(SALES_ROLE, "sales_head")} quyết.`;
  const id = `triage/${message.message_id}`;
  const attach = card.step === "reply_to_case" && Boolean(card.case);

  const decide = async (step: Step | null, toCase: boolean, done: string) => {
    const result = await run(
      id,
      { step, attach: toCase },
      (key) =>
        salesApi().decideTriageCard(
          message.message_id,
          { step, attach: toCase },
          key,
        ),
      done,
    );
    if (result.ok) {
      setError(null);
      onChanged();
    } else setError(result.error);
  };

  // The mail kinds as the company holds them now, read when asked: the
  // words a person edits start from the version in force.
  const teach = async () => {
    setLoadingSkill(true);
    try {
      const skills = await salesApi().skills();
      const skill = skills.skills.find((s) => s.name === MAIL_KINDS);
      if (skill) setTeaching({ skill, versions: skills.versions });
    } catch (failure) {
      setError(failure);
    } finally {
      setLoadingSkill(false);
    }
  };

  const kind = card.kind
    ? intentKindLabel({ kind: card.kind, kind_label: card.kind_label })
    : null;

  return (
    <Flex vertical gap={6} className="max-w-xl">
      <Space wrap>
        <StatusTag tone="warn">DW1 gợi ý</StatusTag>
        <Typography.Text>
          {kind ? `Có vẻ là: ${kind}` : "DW1 không nhận ra loại thư"}
        </Typography.Text>
        {card.case ? (
          <Typography.Text>
            Liên quan:{" "}
            <Link href={`/sales/orders/${card.case.case_id}`}>
              PO {card.case.number}
            </Link>
          </Typography.Text>
        ) : null}
      </Space>
      {card.decided ? (
        <Typography.Text>
          {DECIDED[card.decided.decision]}
          {card.decided.step
            ? `: ${label(INTENT_KIND, card.decided.step)}`
            : ""}{" "}
          ({name(card.decided.by)}, {formatDateTime(card.decided.at)}).
        </Typography.Text>
      ) : (
        <Space wrap>
          {card.step ? (
            <GuardedButton
              type="primary"
              reason={reason}
              loading={pending === id}
              aria-label={`Làm theo gợi ý cho thư ${ref}`}
              onClick={() =>
                void decide(
                  card.step!,
                  attach,
                  `Đã làm theo gợi ý cho thư ${ref}`,
                )
              }
            >
              {attach
                ? `Gắn vào hồ sơ PO ${card.case!.number}`
                : `Làm theo: ${label(INTENT_KIND, card.step)}`}
            </GuardedButton>
          ) : null}
          <Select<Step>
            aria-label={`Bước khác cho thư ${ref}`}
            placeholder="Bước khác"
            className="min-w-48"
            value={other ?? undefined}
            onChange={setOther}
            options={STEPS.filter((s) => s !== card.step).map((s) => ({
              value: s,
              label: label(INTENT_KIND, s),
            }))}
          />
          <GuardedButton
            reason={reason ?? (other ? null : "Chọn một bước trước.")}
            inlineReason={false}
            loading={pending === id}
            onClick={() =>
              other &&
              void decide(
                other,
                false,
                `Đã chuyển thư ${ref} theo bước đã chọn`,
              )
            }
          >
            Chuyển theo bước này
          </GuardedButton>
          <GuardedButton
            reason={reason}
            inlineReason={false}
            loading={pending === id}
            onClick={() =>
              void decide(null, false, `Đã bỏ qua gợi ý cho thư ${ref}`)
            }
          >
            Bỏ qua gợi ý
          </GuardedButton>
        </Space>
      )}
      <div>
        {/* Disabled with who can, not hidden (ui-quality §5): a PIC
            triaging mail learns the control and whom to ask. */}
        <GuardedButton
          type="link"
          reason={hasScope(SCOPE.rulesPropose) ? null : NO_TEACH}
          inlineReason={false}
          loading={loadingSkill}
          onClick={() => void teach()}
        >
          Dạy DW1 loại thư này
        </GuardedButton>
      </div>
      <ActionError error={error} />
      {teaching ? (
        <ProposeSkill
          skill={teaching.skill}
          versions={teaching.versions.filter((v) => v.name === MAIL_KINDS)}
          fromMessage={message.message_id}
          onClose={() => setTeaching(null)}
          onProposed={() => setTeaching(null)}
        />
      ) : null}
    </Flex>
  );
}
