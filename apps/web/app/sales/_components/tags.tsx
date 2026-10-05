"use client";

import type { ReactNode } from "react";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  ExclamationCircleOutlined,
  HistoryOutlined,
  MinusCircleOutlined,
  QuestionCircleOutlined,
  RobotOutlined,
  StopOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import { StatusTag, type StatusTone } from "@dw/ui";
import {
  FINDING_DISPOSITION,
  label,
  MAPPING_STATUS,
  MESSAGE_DISPOSITION,
  ORDER_STATE,
  QUOTE_STATE,
  VALUE_STATE,
} from "../_lib/labels";

/**
 * The Sales status tags: one component per concept, so the same state looks
 * the same on every screen (ui-quality §1). Every tag carries its words and an
 * icon, never colour alone (§7); the look is `@dw/ui`'s `StatusTag`, whose
 * tones are the prototype's label table: `pri` for work moving, `geek` for
 * waiting on someone outside Sales, `warn` for something to look at, `err`
 * for what blocks, `ok` for done. The dashed purple `unk` is kept for
 * "Chưa chắc chắn" alone: the unknown state has a look that means nothing else.
 */
type Look = [StatusTone, ReactNode];

const i = {
  clock: <ClockCircleOutlined key="i" aria-hidden />,
  sync: <SyncOutlined key="i" aria-hidden />,
  check: <CheckCircleOutlined key="i" aria-hidden />,
  close: <CloseCircleOutlined key="i" aria-hidden />,
  warn: <ExclamationCircleOutlined key="i" aria-hidden />,
  stop: <StopOutlined key="i" aria-hidden />,
  edit: <EditOutlined key="i" aria-hidden />,
  question: <QuestionCircleOutlined key="i" aria-hidden />,
  robot: <RobotOutlined key="i" aria-hidden />,
  history: <HistoryOutlined key="i" aria-hidden />,
  minus: <MinusCircleOutlined key="i" aria-hidden />,
};

function Chip({
  look,
  children,
}: {
  look: Look | undefined;
  children: ReactNode;
}) {
  const [tone, icon] = look ?? ["gray", null];
  return (
    <StatusTag tone={tone} icon={icon}>
      {children}
    </StatusTag>
  );
}

const ORDER_LOOK: Record<string, Look> = {
  received: ["gray", i.clock],
  checked: ["gray", i.clock],
  in_review: ["pri", i.sync],
  correction_requested: ["geek", i.clock],
  prepared: ["pri", i.sync],
  uploaded_to_bravo: ["pri", i.sync],
  cross_checked: ["ok", i.check],
  confirmed: ["ok", i.check],
  change_review: ["warn", i.warn],
  closed: ["gray", i.stop],
};

export function OrderStateTag({ status }: { status: string }) {
  return <Chip look={ORDER_LOOK[status]}>{label(ORDER_STATE, status)}</Chip>;
}

const QUOTE_LOOK: Record<string, Look> = {
  received: ["gray", i.clock],
  ycbg_drafted: ["pri", i.sync],
  ycbg_recorded: ["pri", i.sync],
  sent_to_design: ["geek", i.clock],
  design_replied: ["pri", i.sync],
  spec_discussion: ["geek", i.clock],
  priced: ["pri", i.sync],
  pending_approval: ["pri", i.clock],
  returned: ["warn", i.close],
  approved: ["ok", i.check],
  sent: ["ok", i.check],
  master_list_recorded: ["ok", i.check],
  declined: ["gray", i.stop],
};

export function QuoteStateTag({ status }: { status: string }) {
  return <Chip look={QUOTE_LOOK[status]}>{label(QUOTE_STATE, status)}</Chip>;
}

const VALUE_LOOK: Record<string, Look> = {
  dw: ["outline", i.robot],
  uncertain: ["unk", i.question],
  confirmed: ["ok", i.check],
  hand_entered: ["gray", i.edit],
  superseded: ["gray", i.history],
};

/** How sure a value is (CONTEXT.md "Value states"); every state is drawn. */
export function ValueStateTag({ state }: { state: string }) {
  return <Chip look={VALUE_LOOK[state]}>{label(VALUE_STATE, state)}</Chip>;
}

const MAPPING_LOOK: Record<string, Look> = {
  exact: ["ok", i.check],
  candidate: ["warn", i.question],
  ambiguous: ["warn", i.question],
  unmapped: ["err", i.close],
  candidate_confirmed: ["ok", i.edit],
};

export function MappingTag({ status }: { status: string }) {
  return (
    <Chip look={MAPPING_LOOK[status]}>{label(MAPPING_STATUS, status)}</Chip>
  );
}

const DISPOSITION_LOOK: Record<string, Look> = {
  open: ["warn", i.warn],
  accepted: ["ok", i.check],
  corrected_by_sales: ["ok", i.edit],
  ask_customer: ["geek", i.sync],
};

export function DispositionTag({ kind }: { kind: string }) {
  return (
    <Chip look={DISPOSITION_LOOK[kind]}>
      {label(FINDING_DISPOSITION, kind)}
    </Chip>
  );
}

/** "Chặn" for a finding the step cannot pass; "Cảnh báo" for one it can. */
export function SeverityTag({ blocking }: { blocking: boolean }) {
  return blocking ? (
    <Chip look={["err", i.stop]}>Chặn</Chip>
  ) : (
    <Chip look={["warn", i.warn]}>Cảnh báo</Chip>
  );
}

const MESSAGE_LOOK: Record<string, Look> = {
  case_created: ["ok", i.check],
  attached_to_case: ["ok", i.check],
  routed_to_sales: ["warn", i.warn],
  not_yet_processed: ["gray", i.minus],
};

export function MessageDispositionTag({ kind }: { kind: string }) {
  return (
    <Chip look={MESSAGE_LOOK[kind]}>{label(MESSAGE_DISPOSITION, kind)}</Chip>
  );
}
