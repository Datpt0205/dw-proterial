"use client";

import type { ReactNode } from "react";
import {
  CheckCircleOutlined,
  ClockCircleOutlined,
  CloseCircleOutlined,
  EditOutlined,
  FileTextOutlined,
  InboxOutlined,
  RobotOutlined,
  SyncOutlined,
  UserOutlined,
} from "@ant-design/icons";
import type {
  PurchaseAutomationLevel,
  PurchaseCaseStatus,
} from "@dw/api-client";
import { StatusTag, type StatusTone } from "@dw/ui";
import { CASE_STATUS, LEVEL, MARK, type Mark } from "../_lib/labels";

/**
 * The DW2 status tags: one per concept, so a state looks the same on every
 * screen (ui-quality §1), each with its words and an icon, never colour
 * alone (§7). The tones follow the Sales pages' table: `pri` for work moving,
 * `warn` for something waiting on a person, `err` for what stopped, `ok` for
 * done.
 */
type Look = [StatusTone, ReactNode];

const STATUS_LOOK: Record<PurchaseCaseStatus, Look> = {
  received: ["outline", <InboxOutlined key="i" aria-hidden />],
  awaiting_approval: ["warn", <ClockCircleOutlined key="i" aria-hidden />],
  approved: ["ok", <CheckCircleOutlined key="i" aria-hidden />],
  rejected: ["err", <CloseCircleOutlined key="i" aria-hidden />],
  rfq_drafted: ["pri", <SyncOutlined key="i" aria-hidden />],
  awaiting_reapproval: ["warn", <ClockCircleOutlined key="i" aria-hidden />],
  supplier_selected: ["pri", <CheckCircleOutlined key="i" aria-hidden />],
  po_drafted: ["ok", <FileTextOutlined key="i" aria-hidden />],
  delivered: ["ok", <CheckCircleOutlined key="i" aria-hidden />],
};

export function CaseStatusTag({ status }: { status: PurchaseCaseStatus }) {
  const [tone, icon] = STATUS_LOOK[status];
  return (
    <StatusTag tone={tone} icon={icon}>
      {CASE_STATUS[status]}
    </StatusTag>
  );
}

/**
 * Where a value or a text came from. A machine's mark stays after a person
 * read it (ui-quality §7): "Máy đọc" is what the model read from words,
 * "Máy viết" what it wrote, "Mẫu cố định" code's template, "Người nhập" a
 * person's.
 */
const MARK_LOOK: Record<Mark, Look> = {
  machine_read: ["geek", <RobotOutlined key="i" aria-hidden />],
  machine_written: ["geek", <RobotOutlined key="i" aria-hidden />],
  template: ["gray", <FileTextOutlined key="i" aria-hidden />],
  person: ["gray", <UserOutlined key="i" aria-hidden />],
};

export function MarkTag({ mark, tip }: { mark: Mark; tip?: ReactNode }) {
  const [tone, icon] = MARK_LOOK[mark];
  return (
    <StatusTag tone={tone} icon={icon} tip={tip}>
      {MARK[mark]}
    </StatusTag>
  );
}

const LEVEL_LOOK: Record<PurchaseAutomationLevel, Look> = {
  ai_auto: ["ok", <RobotOutlined key="i" aria-hidden />],
  ai_review: ["pri", <EditOutlined key="i" aria-hidden />],
  person: ["gray", <UserOutlined key="i" aria-hidden />],
};

export function LevelTag({ level }: { level: PurchaseAutomationLevel }) {
  const [tone, icon] = LEVEL_LOOK[level];
  return (
    <StatusTag tone={tone} icon={icon}>
      {LEVEL[level]}
    </StatusTag>
  );
}
