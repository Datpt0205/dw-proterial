"use client";

import { Suspense, useCallback, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Alert,
  App,
  Button,
  Card,
  Flex,
  Input,
  Segmented,
  Skeleton,
  Table,
  Tooltip,
  Typography,
} from "antd";
import { RobotOutlined, SendOutlined } from "@ant-design/icons";
import type {
  Approval,
  PurchaseAutomationLevel,
  PurchaseStepLevel,
  PurchasingRuleKey,
  PurchasingRuleVersion,
  PurchasingRules,
  PurchasingWordsDraft,
} from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime } from "../../../lib/dates";
import { errorMessage } from "../../../lib/error-message";
import { useIdempotencyKeys } from "../../../lib/idempotency";
import { useAuth } from "../../../lib/auth/auth-context";
import { apiClient } from "../../../lib/session";
import { useCachedResource } from "../../../lib/use-cached-resource";
import { purchasingApi } from "../_lib/api";
import { LEVEL, LEVEL_WHY, MODEL_STEP, STEP } from "../_lib/labels";
import { usePeople } from "../_lib/people";
import {
  changesInWords,
  problemWords,
  RULE_NAME,
  type Change,
} from "../_lib/rule-words";
import { SCOPE } from "../_lib/scopes";
import { DecideApproval } from "../_components/decide-approval";
import { Rows } from "../_components/rows";
import { purchasingCrumbs, ScopeGate } from "../_components/frame";
import { LevelTag, MarkTag } from "../_components/tags";

/**
 * "Cài đặt DW2": how far DW2 goes on its own at each step, and the company's
 * purchasing rules, both changed without a form of codes. A switch is set by
 * a press, a rule by a sentence ("hạn mức trưởng phòng lên 50 triệu") that
 * the model turns into a draft the platform's checks decide; either way the
 * person reads the change in words and sends it, and a second person approves
 * it (the head's own applies at once). Never JSON, YAML or a field code.
 */
export default function SettingsPage() {
  return (
    <ScopeGate scope={[SCOPE.propose, SCOPE.rulesApprove]}>
      {/* `useSearchParams` (the version a link opens) needs a boundary to build. */}
      <Suspense fallback={<Skeleton active />}>
        <Settings />
      </Suspense>
    </ScopeGate>
  );
}

const ORDER: PurchaseAutomationLevel[] = ["person", "ai_review", "ai_auto"];

function Settings() {
  // A rules approver (granted by permission set) reads and decides; only a
  // proposer changes anything. The server refuses the rest either way.
  const proposes = useAuth().hasScope(SCOPE.propose);
  const rules = useCachedResource(
    "purchasing/rules",
    useCallback(() => purchasingApi().rules(), []),
  );
  const switches = useCachedResource(
    "purchasing/automation",
    useCallback(() => purchasingApi().switches(), []),
  );
  const reload = () => {
    rules.reload();
    switches.reload();
  };
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={purchasingCrumbs("Cài đặt DW2")}
        title="Cài đặt DW2"
        subtitle="Mỗi bước DW2 tự làm đến đâu, và quy tắc mua hàng của công ty. Mọi thay đổi đều được một người khác duyệt."
      />
      {rules.error && !rules.data ? (
        <LoadError error={rules.error} onRetry={rules.reload} />
      ) : null}
      {switches.error && !switches.data ? (
        <LoadError error={switches.error} onRetry={switches.reload} />
      ) : null}
      {switches.data && rules.data ? (
        <Switches
          steps={switches.data.steps}
          rules={rules.data}
          proposes={proposes}
          onSent={reload}
        />
      ) : (
        <Skeleton active />
      )}
      {rules.data ? (
        <>
          {(proposes ? rules.data.keys : []).map((k) => (
            <RuleInWords
              key={k.key}
              rules={rules.data!}
              ruleKey={k.key}
              onSent={reload}
            />
          ))}
          <Versions rules={rules.data} onDecided={reload} />
        </>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------ switches --

function Switches({
  steps,
  rules,
  proposes,
  onSent,
}: {
  steps: PurchaseStepLevel[];
  rules: PurchasingRules;
  proposes: boolean;
  onSent: () => void;
}) {
  const inForce = rules.keys.find((k) => k.key === "purchasing_automation");
  const [chosen, setChosen] = useState<Record<string, PurchaseAutomationLevel>>(
    {},
  );
  const before = useMemo(() => inForce?.document ?? {}, [inForce]);
  const after = useMemo(() => {
    // No number: the platform gives the next one nobody has used.
    const { policy_version: _inForce, ...rest } = before;
    void _inForce;
    return {
      ...rest,
      steps: { ...((before.steps as Record<string, string>) ?? {}), ...chosen },
    };
  }, [before, chosen]);
  const changes = changesInWords(before, after);
  return (
    <Card size="small" title="Công tắc tự động">
      <Flex vertical gap={12}>
        <Typography.Text>
          “AI tự làm” chỉ có hiệu lực khi bước đó đã được đo trên model của nhà
          máy; trước đó DW2 làm và một người duyệt. Tiền, phê duyệt, thư gửi ra
          ngoài và Bravo luôn có người.
        </Typography.Text>
        <Table<PurchaseStepLevel>
          rowKey="step"
          size="small"
          pagination={false}
          scroll={{ x: "max-content" }}
          dataSource={steps}
          columns={[
            { title: "Bước", key: "s", render: (_, s) => STEP[s.step] },
            {
              title: "Đang chạy",
              key: "l",
              render: (_, s) => (
                <Flex vertical gap={2}>
                  <LevelTag level={s.level} />
                  <Typography.Text>
                    {LEVEL_WHY[s.why]}
                    {s.waiting_on.length
                      ? `: ${s.waiting_on.map((m) => MODEL_STEP[m]).join(", ")}`
                      : ""}
                  </Typography.Text>
                </Flex>
              ),
            },
            {
              title: "Công ty chọn",
              key: "c",
              render: (_, s) => (
                <Segmented<PurchaseAutomationLevel>
                  aria-label={`Mức cho bước ${STEP[s.step]}`}
                  value={chosen[s.step] ?? s.chosen}
                  disabled={!proposes}
                  onChange={(level) =>
                    setChosen((c) => ({ ...c, [s.step]: level }))
                  }
                  options={ORDER.map((level) => ({
                    value: level,
                    label: LEVEL[level],
                    disabled: ORDER.indexOf(level) > ORDER.indexOf(s.ceiling),
                  }))}
                />
              ),
            },
            {
              title: "Cao nhất",
              key: "x",
              render: (_, s) =>
                s.ceiling === "ai_auto"
                  ? LEVEL.ai_auto
                  : `${LEVEL[s.ceiling]}: bước này luôn có người quyết`,
            },
          ]}
        />
        {changes.length ? (
          <Propose
            ruleKey="purchasing_automation"
            document={after}
            changes={changes}
            onSent={() => {
              setChosen({});
              onSent();
            }}
          />
        ) : null}
      </Flex>
    </Card>
  );
}

// --------------------------------------------------------------- words --

function RuleInWords({
  rules,
  ruleKey,
  onSent,
}: {
  rules: PurchasingRules;
  ruleKey: PurchasingRuleKey;
  onSent: () => void;
}) {
  const { message } = App.useApp();
  const inForce = rules.keys.find((k) => k.key === ruleKey)!;
  const [request, setRequest] = useState("");
  const [draft, setDraft] = useState<PurchasingWordsDraft | null>(null);
  const [reading, setReading] = useState(false);

  async function read() {
    setReading(true);
    setDraft(null);
    try {
      setDraft(await purchasingApi().ruleInWords(ruleKey, request.trim()));
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setReading(false);
    }
  }

  const version = inForce.ref.split("@")[1] ?? inForce.ref;
  const changes = draft?.document
    ? changesInWords(inForce.document, draft.document)
    : [];
  return (
    <Card
      size="small"
      title={RULE_NAME[ruleKey]}
      extra={
        <Typography.Text>
          Đang áp dụng phiên bản {version}
          {inForce.layer === "tenant"
            ? " của công ty"
            : " dựng sẵn của nền tảng"}
        </Typography.Text>
      }
    >
      <Flex vertical gap={8}>
        <Input.TextArea
          aria-label={`Điều cần đổi trong ${RULE_NAME[ruleKey]}`}
          placeholder={
            ruleKey === "purchasing_rules"
              ? "Ví dụ: Hạn mức trưởng phòng lên 50 triệu"
              : "Ví dụ: Soạn thư hỏi giá để người làm"
          }
          autoSize={{ minRows: 1, maxRows: 4 }}
          maxLength={2000}
          value={request}
          onChange={(event) => setRequest(event.target.value)}
        />
        <Flex>
          <Button
            icon={<RobotOutlined aria-hidden />}
            loading={reading}
            disabled={!request.trim()}
            onClick={() => void read()}
          >
            DW2 soạn thay đổi
          </Button>
        </Flex>
        {draft && !draft.document ? (
          <Alert
            type="warning"
            showIcon
            title="Không có bản nháp"
            description={
              <ul className="mb-0 ps-4">
                {[...new Set(draft.problems.map(problemWords))].map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            }
          />
        ) : null}
        {draft?.document ? (
          <Propose
            ruleKey={ruleKey}
            document={draft.document}
            changes={changes}
            machine
            onSent={() => {
              setDraft(null);
              setRequest("");
              onSent();
            }}
          />
        ) : null}
      </Flex>
    </Card>
  );
}

// ------------------------------------------------------------- propose --

function ChangeList({ changes }: { changes: Change[] }) {
  return (
    <Rows<Change>
      items={changes}
      empty="Không có gì thay đổi so với phiên bản đang áp dụng."
      rowKey={(c) => c.path}
      render={(c) => (
        <Typography.Text>
          <Typography.Text strong>{c.name}</Typography.Text>: {c.before} →{" "}
          {c.after}
        </Typography.Text>
      )}
    />
  );
}

function Propose({
  ruleKey,
  document,
  changes,
  machine,
  onSent,
}: {
  ruleKey: PurchasingRuleKey;
  document: Record<string, unknown>;
  changes: Change[];
  machine?: boolean;
  onSent: () => void;
}) {
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [pending, setPending] = useState(false);
  async function send() {
    const id = `propose:${ruleKey}`;
    setPending(true);
    try {
      const sent = await purchasingApi().proposeRules(
        ruleKey,
        document,
        keys.keyFor(id, document),
      );
      keys.settle(id);
      message.success(
        sent.applied_directly
          ? `Đã áp dụng phiên bản ${sent.version}`
          : `Đã gửi phiên bản ${sent.version}: chờ người khác duyệt`,
      );
      onSent();
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <Flex vertical gap={8}>
      <Flex gap={8} align="center" wrap>
        <Typography.Text strong>Thay đổi sẽ gửi duyệt</Typography.Text>
        {machine ? (
          <MarkTag
            mark="machine_written"
            tip="DW2 đề xuất từ lời bạn viết; hệ thống đã kiểm tra bản nháp."
          />
        ) : null}
      </Flex>
      <ChangeList changes={changes} />
      <Flex>
        <Tooltip title={changes.length ? null : "Không có gì để gửi."}>
          <Button
            type="primary"
            icon={<SendOutlined aria-hidden />}
            loading={pending}
            disabled={!changes.length}
            onClick={() => void send()}
          >
            Gửi duyệt
          </Button>
        </Tooltip>
      </Flex>
    </Flex>
  );
}

// ------------------------------------------------------------ versions --

const VERSION_STATUS: Record<
  PurchasingRuleVersion["status"],
  [string, "warn" | "ok" | "err" | "gray"]
> = {
  proposed: ["Chờ duyệt", "warn"],
  approved: ["Đã duyệt", "ok"],
  rejected: ["Từ chối", "err"],
  superseded: ["Đã thay", "gray"],
};

function Versions({
  rules,
  onDecided,
}: {
  rules: PurchasingRules;
  onDecided: () => void;
}) {
  const focus = useSearchParams().get("version");
  const actor = usePeople();
  const versions = [...rules.versions].sort((a, b) =>
    b.proposed_at.localeCompare(a.proposed_at),
  );
  return (
    <Card size="small" title="Các phiên bản của công ty">
      <Rows<PurchasingRuleVersion>
        items={versions}
        rowKey={(v) => v.version_id}
        empty="Công ty chưa có phiên bản riêng: DW2 chạy theo bản dựng sẵn."
        render={(v) => {
          const inForce = rules.keys.find((k) => k.key === v.key);
          const [label, tone] = VERSION_STATUS[v.status];
          return (
            <div
              id={v.version_id}
              className={focus === v.version_id ? "scroll-mt-24" : undefined}
            >
              <Flex vertical gap={6} className="w-full">
                <Flex gap={8} align="center" wrap>
                  <Typography.Text strong>
                    {RULE_NAME[v.key]} · phiên bản {v.version}
                  </Typography.Text>
                  <StatusTag tone={tone}>{label}</StatusTag>
                  <Typography.Text>
                    {actor(v.proposed_by).name} gửi{" "}
                    {formatDateTime(v.proposed_at)}
                    {v.decided_at
                      ? ` · ${actor(v.decided_by).name} quyết ${formatDateTime(v.decided_at)}`
                      : ""}
                  </Typography.Text>
                </Flex>
                {v.comment ? (
                  <Typography.Text>Lý do: {v.comment}</Typography.Text>
                ) : null}
                {v.status === "proposed" && inForce ? (
                  <>
                    <ChangeList
                      changes={changesInWords(inForce.document, v.document)}
                    />
                    {v.approval_id ? (
                      <VersionDecision
                        approvalId={v.approval_id}
                        v={v}
                        onDecided={onDecided}
                      />
                    ) : null}
                  </>
                ) : null}
              </Flex>
            </div>
          );
        }}
      />
    </Card>
  );
}

function VersionDecision({
  approvalId,
  v,
  onDecided,
}: {
  approvalId: string;
  v: PurchasingRuleVersion;
  onDecided: () => void;
}) {
  const { hasScope } = useAuth();
  const canDecide = hasScope(SCOPE.decide);
  const approval = useCachedResource<Approval | null>(
    `approvals/${approvalId}:${canDecide}`,
    useCallback(
      () =>
        canDecide ? apiClient().getApproval(approvalId) : Promise.resolve(null),
      [approvalId, canDecide],
    ),
  );
  if (!approval.data || approval.data.status !== "pending") return null;
  return (
    <DecideApproval
      approval={approval.data}
      what={`phiên bản ${v.version} của ${RULE_NAME[v.key]}`}
      onDecided={onDecided}
    />
  );
}
