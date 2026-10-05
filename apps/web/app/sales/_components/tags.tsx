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
import { Tag } from "antd";
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
 * icon, never colour alone (§7), and the colours are antd's presets, which the
 * theme owns. Purple is kept for "Chưa chắc chắn" alone: the unknown state
 * has a colour that means nothing else here.
 */
type Tone =
  | "default"
  | "processing"
  | "success"
  | "warning"
  | "error"
  | "purple"
  | "gold";

function Chip({
  tone,
  icon,
  children,
}: {
  tone: Tone;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <Tag color={tone} icon={icon} className="me-0">
      {children}
    </Tag>
  );
}

const ORDER_TONE: Record<string, [Tone, ReactNode]> = {
  received: ["default", <ClockCircleOutlined key="i" aria-hidden />],
  checked: ["default", <ClockCircleOutlined key="i" aria-hidden />],
  in_review: ["processing", <SyncOutlined key="i" aria-hidden />],
  correction_requested: [
    "warning",
    <ExclamationCircleOutlined key="i" aria-hidden />,
  ],
  prepared: ["processing", <SyncOutlined key="i" aria-hidden />],
  uploaded_to_bravo: ["processing", <SyncOutlined key="i" aria-hidden />],
  cross_checked: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  confirmed: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  change_review: ["warning", <ExclamationCircleOutlined key="i" aria-hidden />],
  closed: ["default", <StopOutlined key="i" aria-hidden />],
};

export function OrderStateTag({ status }: { status: string }) {
  const [tone, icon] = ORDER_TONE[status] ?? ["default", null];
  return (
    <Chip tone={tone} icon={icon}>
      {label(ORDER_STATE, status)}
    </Chip>
  );
}

const QUOTE_TONE: Record<string, [Tone, ReactNode]> = {
  received: ["default", <ClockCircleOutlined key="i" aria-hidden />],
  ycbg_drafted: ["processing", <SyncOutlined key="i" aria-hidden />],
  ycbg_recorded: ["processing", <SyncOutlined key="i" aria-hidden />],
  sent_to_design: ["warning", <ClockCircleOutlined key="i" aria-hidden />],
  design_replied: ["processing", <SyncOutlined key="i" aria-hidden />],
  spec_discussion: ["warning", <ClockCircleOutlined key="i" aria-hidden />],
  priced: ["processing", <SyncOutlined key="i" aria-hidden />],
  pending_approval: ["warning", <ClockCircleOutlined key="i" aria-hidden />],
  returned: ["error", <CloseCircleOutlined key="i" aria-hidden />],
  approved: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  sent: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  master_list_recorded: [
    "success",
    <CheckCircleOutlined key="i" aria-hidden />,
  ],
  declined: ["default", <StopOutlined key="i" aria-hidden />],
};

export function QuoteStateTag({ status }: { status: string }) {
  const [tone, icon] = QUOTE_TONE[status] ?? ["default", null];
  return (
    <Chip tone={tone} icon={icon}>
      {label(QUOTE_STATE, status)}
    </Chip>
  );
}

const VALUE_TONE: Record<string, [Tone, ReactNode]> = {
  dw: ["default", <RobotOutlined key="i" aria-hidden />],
  uncertain: ["purple", <QuestionCircleOutlined key="i" aria-hidden />],
  confirmed: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  hand_entered: ["gold", <EditOutlined key="i" aria-hidden />],
  superseded: ["default", <HistoryOutlined key="i" aria-hidden />],
};

/** How sure a value is (CONTEXT.md "Value states"); every state is drawn. */
export function ValueStateTag({ state }: { state: string }) {
  const [tone, icon] = VALUE_TONE[state] ?? ["default", null];
  return (
    <Chip tone={tone} icon={icon}>
      {label(VALUE_STATE, state)}
    </Chip>
  );
}

const MAPPING_TONE: Record<string, [Tone, ReactNode]> = {
  exact: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  candidate: ["warning", <QuestionCircleOutlined key="i" aria-hidden />],
  ambiguous: ["warning", <QuestionCircleOutlined key="i" aria-hidden />],
  unmapped: ["error", <CloseCircleOutlined key="i" aria-hidden />],
  candidate_confirmed: ["success", <EditOutlined key="i" aria-hidden />],
};

export function MappingTag({ status }: { status: string }) {
  const [tone, icon] = MAPPING_TONE[status] ?? ["default", null];
  return (
    <Chip tone={tone} icon={icon}>
      {label(MAPPING_STATUS, status)}
    </Chip>
  );
}

const DISPOSITION_TONE: Record<string, [Tone, ReactNode]> = {
  open: ["warning", <ExclamationCircleOutlined key="i" aria-hidden />],
  accepted: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  corrected_by_sales: ["gold", <EditOutlined key="i" aria-hidden />],
  ask_customer: ["processing", <SyncOutlined key="i" aria-hidden />],
};

export function DispositionTag({ kind }: { kind: string }) {
  const [tone, icon] = DISPOSITION_TONE[kind] ?? ["default", null];
  return (
    <Chip tone={tone} icon={icon}>
      {label(FINDING_DISPOSITION, kind)}
    </Chip>
  );
}

/** "Chặn" for a finding the step cannot pass; "Cảnh báo" for one it can. */
export function SeverityTag({ blocking }: { blocking: boolean }) {
  return blocking ? (
    <Chip tone="error" icon={<CloseCircleOutlined aria-hidden />}>
      Chặn
    </Chip>
  ) : (
    <Chip tone="warning" icon={<ExclamationCircleOutlined aria-hidden />}>
      Cảnh báo
    </Chip>
  );
}

const MESSAGE_TONE: Record<string, [Tone, ReactNode]> = {
  case_created: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  attached_to_case: ["success", <CheckCircleOutlined key="i" aria-hidden />],
  routed_to_sales: [
    "warning",
    <ExclamationCircleOutlined key="i" aria-hidden />,
  ],
  not_yet_processed: ["default", <MinusCircleOutlined key="i" aria-hidden />],
};

export function MessageDispositionTag({ kind }: { kind: string }) {
  const [tone, icon] = MESSAGE_TONE[kind] ?? ["default", null];
  return (
    <Chip tone={tone} icon={icon}>
      {label(MESSAGE_DISPOSITION, kind)}
    </Chip>
  );
}
