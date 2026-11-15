"use client";

import { Suspense, useCallback, useRef, useState } from "react";
import Link from "next/link";
import {
  Alert,
  Button,
  Drawer,
  Form,
  Grid,
  Input,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import { InfoTip, PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { useAuth } from "../../../../lib/auth/auth-context";
import { salesApi } from "../../_lib/api";
import { ActionError } from "../../_lib/errors";
import { usePeople } from "../../_lib/people";
import { RULE_STATUS } from "../../_lib/rules";
import {
  SKILL_LAYER,
  incompleteLine,
  nextSkillVersion,
  replayLine,
  securityLine,
  versionsOf,
  type Skill,
  type SkillVersion,
  type SkillsView,
} from "../../_lib/skills";
import { useAction } from "../../_lib/use-action";
import { useResource } from "../../_lib/use-resource";
import { salesCrumbs } from "../../_components/crumbs";
import {
  usePhoneColumns,
  usePhoneTable,
  useIsPhone,
} from "../../_components/list-parts";
import { GuardedButton } from "../../_components/guarded-button";
import { useConfirmDiscard } from "../../_components/rule-editor";
import { SCOPE } from "../../_components/sales-frame";
import { ScopeGate } from "../../_components/scope-gate";

const TONE: Record<SkillVersion["status"], "ok" | "warn" | "err" | "unk"> = {
  proposed: "warn",
  approved: "ok",
  rejected: "err",
  superseded: "unk",
};
// The server refuses a second proposal of one skill (`one_open_proposal`).
const ONE_WAITING =
  "Đang có một phiên bản chờ duyệt: quyết xong mới đề xuất bản khác.";

/**
 * Kỹ năng của DW1 (ticket 40, dw_sales ADR 0014): the words DW1 reads a
 * kind of mail by, the platform's or the company's own version, and every
 * version the company proposed with the worker's replay of it on example
 * mails, with it and with the skills in force. A holder of
 * `sales.rules.propose` proposes a whole new text; it opens a `sales.skills`
 * approval the head decides on `/approvals`, never the proposer, and only
 * once the replay is stored (the server refuses before). Nothing here decides.
 */
export default function SkillsPage() {
  return (
    <ScopeGate scope={SCOPE.rulesPropose}>
      <Suspense>
        <Skills />
      </Suspense>
    </ScopeGate>
  );
}

function Skills() {
  const { hasScope } = useAuth();
  const seesApprovals = hasScope("approvals.read");
  const name = usePeople();
  const phone = usePhoneColumns();
  const table = usePhoneTable();
  const isPhone = useIsPhone();
  const skills = useResource(
    "sales/skills",
    useCallback(() => salesApi().skills(), []),
  );
  const [editing, setEditing] = useState<Skill | null>(null);

  const view: SkillsView | null = skills.data;
  const list = view?.skills ?? [];
  const versions = view?.versions ?? [];
  const waiting = versions.filter((v) => v.status === "proposed").length;
  const own = list.filter((s) => s.layer === "tenant").length;

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs(
          { title: "Quy tắc", href: "/sales/rules" },
          "Kỹ năng của DW1",
        )}
        title="Kỹ năng của DW1"
        subtitle={`${own}/${list.length} kỹ năng đang dùng bản riêng · ${waiting} phiên bản chờ duyệt`}
        help="Kỹ năng là lời hướng dẫn DW1 đọc một loại thư. Bản đề xuất được chạy thử trên thư mẫu, rồi Trưởng bộ phận duyệt; người đề xuất không tự duyệt. Kỹ năng chỉ là lời: không thêm công cụ, quyền, người nhận hay con số nào."
      />
      {skills.error ? (
        <LoadError error={skills.error} onRetry={skills.reload} />
      ) : (
        <>
          <Table<Skill>
            rowKey="name"
            loading={skills.loading}
            dataSource={list}
            pagination={false}
            scroll={table.scroll()}
            tableLayout={table.tableLayout}
            locale={{
              emptyText: skills.loading ? " " : "Nền tảng chưa có kỹ năng nào.",
            }}
            expandable={{
              expandedRowRender: (s) => (
                <Instructions
                  label={`Lời hướng dẫn ${s.ref}`}
                  text={s.instructions}
                />
              ),
            }}
            columns={phone(
              [
                {
                  title: "Kỹ năng",
                  key: "name",
                  render: (_, s) => (
                    <span className="flex flex-col">
                      <Typography.Text strong>{s.name}</Typography.Text>
                      <Typography.Text
                        ellipsis={{ tooltip: s.description }}
                        className="max-w-xl"
                      >
                        {s.description}
                      </Typography.Text>
                      {isPhone ? (
                        <span className="mt-1">
                          <StatusTag
                            tone={s.layer === "tenant" ? "ok" : "gray"}
                          >
                            {SKILL_LAYER[s.layer]}
                          </StatusTag>
                        </span>
                      ) : null}
                    </span>
                  ),
                },
                {
                  title: "Đang dùng",
                  key: "in_force",
                  render: (_, s) => (
                    <span className="flex flex-col items-start gap-1">
                      <StatusTag tone={s.layer === "tenant" ? "ok" : "gray"}>
                        {SKILL_LAYER[s.layer]}
                      </StatusTag>
                      <Typography.Text code>{s.ref}</Typography.Text>
                    </span>
                  ),
                },
                {
                  title: "Đề xuất",
                  key: "propose",
                  fixed: "right",
                  render: (_, s) => (
                    <GuardedButton
                      size="small"
                      reason={
                        versionsOf(s, versions).some(
                          (v) => v.status === "proposed",
                        )
                          ? ONE_WAITING
                          : null
                      }
                      inlineReason={false}
                      onClick={() => setEditing(s)}
                      aria-label={`Đề xuất sửa kỹ năng ${s.name}`}
                    >
                      Đề xuất sửa
                    </GuardedButton>
                  ),
                },
              ],
              ["propose"],
            )}
          />
          <Typography.Title level={4} className="mb-0!">
            Các phiên bản của công ty
          </Typography.Title>
          <Table<SkillVersion>
            rowKey="version_id"
            loading={skills.loading}
            dataSource={versions}
            pagination={false}
            scroll={table.scroll()}
            tableLayout={table.tableLayout}
            locale={{
              emptyText: skills.loading
                ? " "
                : "Công ty chưa đề xuất phiên bản kỹ năng nào: DW1 đọc theo bản của nền tảng.",
            }}
            footer={() => `${versions.length} phiên bản`}
            expandable={{
              expandedRowRender: (v) => (
                <Instructions
                  label={`Lời hướng dẫn ${v.ref}`}
                  text={v.instructions}
                />
              ),
            }}
            columns={phone(
              [
                {
                  title: "Phiên bản",
                  key: "ref",
                  render: (_, v) => (
                    <span className="flex flex-col">
                      <Typography.Text strong>{v.name}</Typography.Text>
                      <Typography.Text code>{v.ref}</Typography.Text>
                      {isPhone ? <Replay version={v} /> : null}
                    </span>
                  ),
                },
                {
                  title: "Trạng thái",
                  key: "status",
                  render: (_, v) => (
                    <StatusTag tone={TONE[v.status]}>
                      {RULE_STATUS[v.status]}
                    </StatusTag>
                  ),
                },
                {
                  title: "Chạy thử trên thư mẫu",
                  key: "replay",
                  render: (_, v) => <Replay version={v} />,
                },
                {
                  title: "Người đề xuất · quyết định",
                  key: "people",
                  render: (_, v) => (
                    <span className="flex flex-col">
                      <span>{name(v.proposed_by)}</span>
                      {v.decided_by ? <span>{name(v.decided_by)}</span> : null}
                    </span>
                  ),
                },
                {
                  title: "Thao tác",
                  key: "actions",
                  fixed: "right",
                  render: (_, v) =>
                    v.approval_id &&
                    seesApprovals &&
                    v.status === "proposed" ? (
                      <Link href={`/approvals/${v.approval_id}`}>
                        Mở phê duyệt
                      </Link>
                    ) : null,
                },
              ],
              ["status", "actions"],
            )}
          />
        </>
      )}
      {editing && view ? (
        <ProposeSkill
          skill={editing}
          versions={versions}
          onClose={() => setEditing(null)}
          onProposed={() => {
            setEditing(null);
            skills.reload();
          }}
        />
      ) : null}
    </div>
  );
}

/** A skill's instructions, whole, as written. */
function Instructions({ label, text }: { label: string; text: string }) {
  return (
    <Typography.Paragraph
      aria-label={label}
      className="m-0 max-h-96 overflow-auto whitespace-pre-wrap"
    >
      {text}
    </Typography.Paragraph>
  );
}

/** What the worker's replay found, or that it has not run yet. */
function Replay({ version }: { version: SkillVersion }) {
  const replay = version.replay ?? null;
  if (!replay) {
    if (version.status !== "proposed") return null;
    return (
      <span className="flex flex-col items-start gap-1">
        <Tag color="processing">Đang chạy thử trên thư mẫu</Tag>
        <Typography.Text>
          Trưởng bộ phận chỉ duyệt được khi có kết quả.
        </Typography.Text>
      </span>
    );
  }
  const security = securityLine(replay);
  const incomplete = incompleteLine(replay);
  return (
    <span className="flex flex-col items-start gap-1">
      <span className="inline-flex items-center gap-1">
        <Typography.Text>{replayLine(replay)}</Typography.Text>
        <InfoTip label="Thư mẫu nào?">
          Chạy trên thư mẫu của nền tảng (chưa có thư công ty đã kiểm): mỗi thư
          được đọc một lần với bản đề xuất và một lần với bản đang dùng.
        </InfoTip>
      </span>
      {incomplete ? <Alert type="warning" showIcon title={incomplete} /> : null}
      {security ? <Alert type="error" showIcon title={security} /> : null}
    </span>
  );
}

interface ProposalForm {
  version: string;
  description: string;
  instructions: string;
}

/** "Đề xuất sửa": a whole new text of one skill, sent for the head's approval. */
function ProposeSkill({
  skill,
  versions,
  onClose,
  onProposed,
}: {
  skill: Skill;
  versions: readonly SkillVersion[];
  onClose: () => void;
  onProposed: () => void;
}) {
  const { run, pending } = useAction();
  const discard = useConfirmDiscard();
  const [form] = Form.useForm<ProposalForm>();
  const [error, setError] = useState<unknown>(null);
  const touched = useRef(false);
  // A bottom sheet on a phone (ui-quality §9); from the right from md up.
  const sheet = Grid.useBreakpoint().md === false;
  const id = `propose-skill/${skill.name}`;

  const close = () => (touched.current ? discard(onClose) : onClose());
  const submit = async (values: ProposalForm) => {
    setError(null);
    const result = await run(
      id,
      { name: skill.name, ...values },
      (key) => salesApi().proposeSkill(skill.name, values, key),
      `Đã gửi duyệt kỹ năng "${skill.name}" ${values.version}. DW1 chạy thử trên thư mẫu, rồi Trưởng bộ phận duyệt trên trang Duyệt.`,
    );
    if (result.ok) return onProposed();
    setError(result.error);
  };

  return (
    <Drawer
      open
      onClose={close}
      placement={sheet ? "bottom" : "right"}
      size={sheet ? "90vh" : "min(960px, 100vw)"}
      title={`Đề xuất sửa kỹ năng ${skill.name}`}
      destroyOnHidden
      footer={
        <Space wrap>
          <Button
            type="primary"
            loading={pending === id}
            onClick={() => form.submit()}
          >
            Gửi duyệt
          </Button>
          <Button onClick={close}>Hủy</Button>
        </Space>
      }
    >
      <div className="space-y-4">
        <ActionError error={error} />
        <Form<ProposalForm>
          form={form}
          layout="vertical"
          validateTrigger="onBlur"
          scrollToFirstError={{ focus: true }}
          initialValues={{
            version: nextSkillVersion(skill, versions),
            description: skill.description,
            instructions: skill.instructions,
          }}
          onValuesChange={() => {
            touched.current = true;
          }}
          onFinish={(values) => void submit(values)}
        >
          <Form.Item
            name="version"
            label="Số phiên bản"
            rules={[
              {
                required: true,
                message: "Cần số phiên bản",
                validateTrigger: "onSubmit",
              },
              { pattern: /^\d+\.\d+\.\d+$/, message: "Dạng 1.2.3" },
            ]}
          >
            <Input className="max-w-40" />
          </Form.Item>
          <Form.Item
            name="description"
            label="Dùng khi nào (DW1 chọn kỹ năng theo câu này)"
            rules={[
              {
                required: true,
                message: "Cần mô tả",
                validateTrigger: "onSubmit",
              },
              { max: 1024, message: "Tối đa 1024 ký tự" },
            ]}
          >
            <Input.TextArea
              autoSize={{ minRows: 2, maxRows: 6 }}
              maxLength={1024}
              showCount
            />
          </Form.Item>
          <Form.Item
            name="instructions"
            label="Lời hướng dẫn"
            rules={[
              {
                required: true,
                message: "Cần lời hướng dẫn",
                validateTrigger: "onSubmit",
              },
              { max: 12000, message: "Tối đa 12000 ký tự" },
            ]}
          >
            <Input.TextArea
              autoSize={{ minRows: 8, maxRows: 30 }}
              maxLength={12000}
              showCount
            />
          </Form.Item>
        </Form>
      </div>
    </Drawer>
  );
}
