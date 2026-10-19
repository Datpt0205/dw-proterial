"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import Link from "next/link";
import {
  Alert,
  App,
  Button,
  Drawer,
  Form,
  Input,
  Segmented,
  Select,
  Skeleton,
  Space,
  Table,
  Typography,
} from "antd";
import { ApiError, type SalesSchemas } from "@dw/api-client";
import { PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { formatDateTime, TIME_ZONE_LABEL } from "../../../lib/dates";
import { errorCode } from "../../../lib/error-message";
import { salesApi } from "../_lib/api";
import { ActionError, detailList } from "../_lib/errors";
import { usePeople } from "../_lib/people";
import {
  keyRows,
  nextVersion,
  parseDocument,
  RULE_KEY,
  RULE_LAYER,
  RULE_STATUS,
  startOptions,
  type KeyRow,
  type RuleKey,
  type RuleVersion,
  type StartOption,
} from "../_lib/rules";
import { pathLabel } from "../_lib/rule-labels";
import {
  formName,
  fromForm,
  parseLoc,
  readSchema,
  toForm,
  versionField,
  type JsonSchema,
  type RuleNode,
} from "../_lib/rule-schema";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { salesCrumbs } from "../_components/crumbs";
import { RuleDiffView } from "../_components/rule-diff-view";
import { RuleFields } from "../_components/rule-form";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";

const TONE: Record<RuleVersion["status"], "ok" | "warn" | "err" | "unk"> = {
  proposed: "warn",
  approved: "ok",
  rejected: "err",
  superseded: "unk",
};

/**
 * Quy tắc (tickets 19, 38, 36, 40): what applies to the company per key, the
 * platform's or its own, and every version it proposed. A holder of
 * `sales.rules.propose` (Sales phụ trách or Trưởng bộ phận Sales) proposes a
 * whole document for one key in a form drawn from that key's JSON Schema,
 * reads what it changes against the version in force, and sends it; the
 * server validates it again and opens a `sales.rules` platform approval,
 * which someone who did not propose it decides on `/approvals`. Nothing here
 * decides. The server answers this page only to holders of the scope (the
 * documents can hold price rules), and refuses a proposal from anyone else.
 */
export default function RulesPage() {
  return (
    <ScopeGate scope={SCOPE.rulesPropose}>
      <Suspense>
        <Rules />
      </Suspense>
    </ScopeGate>
  );
}

interface Proposing {
  key: RuleKey;
  /** The `StartOption.id` to open with; what applies now when absent. */
  start?: string;
}

function Rules() {
  const name = usePeople();
  const rules = useResource(
    "sales/rules",
    useCallback(() => salesApi().rules(), []),
  );
  const [proposing, setProposing] = useState<Proposing | null>(null);

  const keys = rules.data ? keyRows(rules.data) : [];
  const versions = rules.data?.versions ?? [];
  const own = keys.filter((k) => k.layer === "tenant").length;
  const waiting = versions.filter((v) => v.status === "proposed").length;
  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={salesCrumbs("Quy tắc")}
        title="Quy tắc của công ty"
        subtitle={`${own}/${keys.length} quy tắc đang dùng phiên bản riêng · ${waiting} phiên bản chờ duyệt. Người đề xuất không tự duyệt; phiên bản được quyết trên trang Duyệt, mở từ liên kết ở mỗi phiên bản.`}
      />
      {rules.error ? (
        <LoadError error={rules.error} onRetry={rules.reload} />
      ) : (
        <>
          <Table<KeyRow>
            rowKey="key"
            loading={rules.loading}
            dataSource={keys}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{ emptyText: rules.loading ? " " : "Không có quy tắc." }}
            footer={() => `${keys.length} quy tắc`}
            columns={[
              {
                title: "Quy tắc",
                key: "key",
                render: (_, k) => (
                  <span className="flex flex-col">
                    <Typography.Text strong>{RULE_KEY[k.key]}</Typography.Text>
                    <Typography.Text code>{k.key}</Typography.Text>
                  </span>
                ),
              },
              {
                title: "Đang áp dụng",
                key: "in_force",
                render: (_, k) => (
                  <Space orientation="vertical" size={2}>
                    <Typography.Text code>{k.inForce}</Typography.Text>
                    <StatusTag tone={k.layer === "tenant" ? "ok" : "gray"}>
                      {RULE_LAYER[k.layer]}
                    </StatusTag>
                  </Space>
                ),
              },
              {
                title: "Bản của nền tảng",
                key: "platform",
                render: (_, k) => (
                  <Typography.Text code>{k.platform}</Typography.Text>
                ),
              },
              {
                title: "Chờ duyệt",
                key: "waiting",
                align: "right",
                render: (_, k) => k.waiting,
              },
              {
                title: "Đề xuất",
                key: "propose",
                fixed: "right",
                render: (_, k) => (
                  <Button
                    size="small"
                    onClick={() => setProposing({ key: k.key })}
                    aria-label={`Đề xuất phiên bản mới: ${RULE_KEY[k.key]}`}
                  >
                    Đề xuất phiên bản mới
                  </Button>
                ),
              },
            ]}
          />
          <Typography.Title level={4} className="mb-0!">
            Các phiên bản của công ty
          </Typography.Title>
          <Table<RuleVersion>
            rowKey="version_id"
            loading={rules.loading}
            dataSource={versions}
            pagination={false}
            scroll={{ x: "max-content" }}
            locale={{
              emptyText: rules.loading
                ? " "
                : "Công ty chưa có phiên bản riêng nào: mọi quy tắc đang theo bản của nền tảng.",
            }}
            footer={() => `${versions.length} phiên bản`}
            expandable={{
              expandedRowRender: (v) => (
                <pre
                  aria-label={`Tài liệu ${v.ref}`}
                  className="m-0 max-h-96 overflow-auto whitespace-pre-wrap"
                >
                  {JSON.stringify(v.document, null, 2)}
                </pre>
              ),
            }}
            columns={[
              {
                title: "Phiên bản",
                key: "ref",
                render: (_, v) => (
                  <span className="flex flex-col">
                    <Typography.Text strong>{RULE_KEY[v.key]}</Typography.Text>
                    <Typography.Text code>{v.ref}</Typography.Text>
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
                title: `Người đề xuất (${TIME_ZONE_LABEL})`,
                key: "proposed",
                render: (_, v) => (
                  <span className="flex flex-col">
                    <span>{name(v.proposed_by)}</span>
                    <span>
                      {formatDateTime(v.proposed_at, { zoneLabel: false })}
                    </span>
                  </span>
                ),
              },
              {
                title: `Người quyết định (${TIME_ZONE_LABEL})`,
                key: "decided",
                render: (_, v) =>
                  v.decided_by ? (
                    <span className="flex flex-col">
                      <span>{name(v.decided_by)}</span>
                      <span>
                        {formatDateTime(v.decided_at, { zoneLabel: false })}
                      </span>
                      {v.comment ? <span>{v.comment}</span> : null}
                    </span>
                  ) : (
                    ""
                  ),
              },
              {
                title: "Thao tác",
                key: "actions",
                fixed: "right",
                render: (_, v) => (
                  <Space orientation="vertical" size={2}>
                    {v.approval_id ? (
                      <Link href={`/approvals/${v.approval_id}`}>
                        Mở yêu cầu duyệt
                      </Link>
                    ) : null}
                    <Button
                      size="small"
                      onClick={() =>
                        setProposing({
                          key: v.key,
                          start: `tenant:${v.version_id}`,
                        })
                      }
                      aria-label={`Dùng lại phiên bản này: ${v.ref}`}
                    >
                      Dùng lại phiên bản này
                    </Button>
                  </Space>
                ),
              },
            ]}
          />
        </>
      )}
      {proposing && rules.data ? (
        <ProposeDrawer
          ruleKey={proposing.key}
          initialStart={proposing.start}
          view={rules.data}
          onClose={() => setProposing(null)}
          onProposed={() => {
            setProposing(null);
            rules.reload();
          }}
        />
      ) : null}
    </div>
  );
}

type View = SalesSchemas["RulesInForceView"];

/** The proposal drawer: loads the key's schema and the platform's versions. */
function ProposeDrawer({
  ruleKey,
  initialStart,
  view,
  onClose,
  onProposed,
}: {
  ruleKey: RuleKey;
  initialStart?: string;
  view: View;
  onClose: () => void;
  onProposed: () => void;
}) {
  const schema = useResource(
    `sales/rules/${ruleKey}/schema`,
    useCallback(() => salesApi().ruleSchema(ruleKey), [ruleKey]),
  );
  const platform = useResource(
    `sales/rules/${ruleKey}/platform`,
    useCallback(() => salesApi().rulePlatformDocuments(ruleKey), [ruleKey]),
  );
  const root = useMemo(
    () =>
      schema.data
        ? readSchema(schema.data.json_schema as unknown as JsonSchema)
        : null,
    [schema.data],
  );
  const options = useMemo(
    () => (platform.data ? startOptions(view, ruleKey, platform.data) : []),
    [platform.data, view, ruleKey],
  );
  const failed = schema.error ?? platform.error;
  const title = `Đề xuất phiên bản mới: ${RULE_KEY[ruleKey]}`;

  if (failed || !root || !platform.data)
    return (
      <Drawer open onClose={onClose} size="min(960px, 100vw)" title={title}>
        {failed ? (
          <LoadError
            error={failed}
            onRetry={() => {
              schema.reload();
              platform.reload();
            }}
          />
        ) : (
          <Skeleton active paragraph={{ rows: 10 }} />
        )}
      </Drawer>
    );
  return (
    <Editor
      ruleKey={ruleKey}
      root={root}
      options={options}
      initialStart={initialStart}
      title={title}
      onClose={onClose}
      onProposed={onProposed}
    />
  );
}

type Mode = "form" | "json";
type Step = "edit" | "review";

const SERVER_REFUSED =
  "Máy chủ không nhận giá trị này. Kiểm lại theo hướng dẫn của trường.";

/** A start document with the next free version number already in place. */
function prepared(
  root: RuleNode,
  option: StartOption,
  options: readonly StartOption[],
): Record<string, unknown> {
  const field = versionField(root);
  if (!field) return option.document;
  return {
    ...option.document,
    [field]: nextVersion(options.map((o) => o.ref)),
  };
}

function Editor({
  ruleKey,
  root,
  options,
  initialStart,
  title,
  onClose,
  onProposed,
}: {
  ruleKey: RuleKey;
  root: RuleNode;
  options: StartOption[];
  initialStart?: string;
  title: string;
  onClose: () => void;
  onProposed: () => void;
}) {
  const { modal } = App.useApp();
  const { run, pending } = useAction();
  const [form] = Form.useForm();
  const inForce = options.find((o) => o.inForce) ?? options[0]!;
  const [startId, setStartId] = useState(
    options.some((o) => o.id === initialStart) ? initialStart! : inForce.id,
  );
  const start = options.find((o) => o.id === startId) ?? inForce;
  const [initial, setInitial] = useState(() =>
    toForm(root, prepared(root, start, options)),
  );
  const [mode, setMode] = useState<Mode>("form");
  const [json, setJson] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [step, setStep] = useState<Step>("edit");
  const [proposal, setProposal] = useState<Record<string, unknown> | null>(
    null,
  );
  const [failedCount, setFailedCount] = useState(0);
  const [unplaced, setUnplaced] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const touched = useRef(false);
  const id = `propose/${ruleKey}`;

  // A new start replaces the whole form: the store is reset to it.
  useEffect(() => {
    form.resetFields();
  }, [initial, form]);

  const current = (): Record<string, unknown> =>
    fromForm(root, form.getFieldsValue(true)) as Record<string, unknown>;

  const confirmDiscard = (onOk: () => void, title: string) => {
    if (!touched.current) return onOk();
    modal.confirm({
      title,
      content: "Những thay đổi chưa gửi duyệt sẽ mất.",
      okText: "Bỏ thay đổi",
      okButtonProps: { danger: true },
      cancelText: "Tiếp tục sửa",
      autoFocusButton: "cancel",
      onOk,
    });
  };

  const choose = (next: string) =>
    confirmDiscard(() => {
      const option = options.find((o) => o.id === next)!;
      setStartId(next);
      setInitial(toForm(root, prepared(root, option, options)));
      setJson(JSON.stringify(prepared(root, option, options), null, 2));
      touched.current = false;
      setError(null);
      setFailedCount(0);
      setUnplaced([]);
    }, "Bắt đầu lại từ phiên bản khác?");

  const switchMode = (next: Mode) => {
    if (next === "json") {
      setJson(JSON.stringify(current(), null, 2));
      setJsonError(null);
      setMode("json");
      return;
    }
    const parsed = parseDocument(json);
    if (!parsed.ok) return setJsonError(parsed.error);
    setInitial(toForm(root, parsed.document));
    setMode("form");
  };

  const review = (document: Record<string, unknown>) => {
    setProposal(document);
    setFailedCount(0);
    setStep("review");
  };

  const toReview = () => {
    if (mode === "form") return form.submit();
    const parsed = parseDocument(json);
    if (!parsed.ok) return setJsonError(parsed.error);
    review(parsed.document);
  };

  /** The server's 422 named fields: put each on its field, the rest above. */
  const placeServerErrors = (refusal: unknown) => {
    if (
      !(refusal instanceof ApiError) ||
      errorCode(refusal) !== "validation_failed"
    )
      return;
    const locs = detailList(refusal.body.details?.errors);
    if (!locs.length) return;
    const values = mode === "form" ? form.getFieldsValue(true) : null;
    const fields: { name: (string | number)[]; errors: string[] }[] = [];
    const elsewhere: string[] = [];
    for (const loc of locs) {
      const path = parseLoc(loc);
      const name = mode === "form" ? formName(root, values, path) : null;
      if (name && name.length) fields.push({ name, errors: [SERVER_REFUSED] });
      else
        elsewhere.push(
          path.length ? pathLabel(ruleKey, root, path) : "Toàn bộ tài liệu",
        );
    }
    form.setFields(fields);
    setFailedCount(fields.length);
    setUnplaced(elsewhere);
  };

  const propose = async () => {
    if (!proposal) return;
    const body = { document: proposal };
    const result = await run(
      id,
      { ruleKey, ...body },
      (key) => salesApi().proposeRule(ruleKey, body, key),
      `Đã gửi duyệt phiên bản mới của "${RULE_KEY[ruleKey]}". Người khác duyệt trên trang Duyệt.`,
    );
    if (result.ok) return onProposed();
    setError(result.error);
    setStep("edit");
    placeServerErrors(result.error);
  };

  const close = () => confirmDiscard(onClose, "Bỏ tài liệu đang sửa?");
  const proposedRef = proposal
    ? `${ruleKey}@${String(proposal[versionField(root) ?? "version"] ?? "")}`
    : "";

  return (
    <Drawer
      open
      onClose={close}
      size="min(960px, 100vw)"
      title={title}
      destroyOnHidden
      footer={
        step === "edit" ? (
          <Space wrap>
            <Button type="primary" onClick={toReview}>
              Xem thay đổi
            </Button>
            <Button onClick={close}>Hủy</Button>
          </Space>
        ) : (
          <Space wrap>
            <Button
              type="primary"
              loading={pending === id}
              onClick={() => void propose()}
            >
              Gửi duyệt
            </Button>
            <Button onClick={() => setStep("edit")}>Quay lại sửa</Button>
          </Space>
        )
      }
    >
      <div className="space-y-4">
        <Typography.Paragraph>
          Bắt đầu từ một phiên bản, sửa, rồi xem các thay đổi so với bản đang áp
          dụng trước khi gửi duyệt. Máy chủ kiểm lại toàn bộ tài liệu, và từ
          chối số phiên bản đã dùng.
        </Typography.Paragraph>
        {step === "review" && proposal ? (
          <RuleDiffView
            ruleKey={ruleKey}
            root={root}
            before={inForce.document}
            after={proposal}
            beforeRef={inForce.ref}
            afterRef={proposedRef}
          />
        ) : null}
        <div hidden={step === "review"} className="space-y-4">
          <Form.Item
            label="Bắt đầu từ phiên bản"
            htmlFor="rule-start"
            layout="vertical"
            extra="Dùng lại một phiên bản cũ: nội dung của nó được mở sẵn, và gửi đi như một đề xuất mới."
          >
            <Select
              id="rule-start"
              value={startId}
              onChange={choose}
              options={options.map((o) => ({
                value: o.id,
                label: startLabel(o),
              }))}
            />
          </Form.Item>
          <Segmented<Mode>
            value={mode}
            onChange={switchMode}
            options={[
              { value: "form", label: "Biểu mẫu" },
              { value: "json", label: "JSON nâng cao" },
            ]}
          />
          {jsonError ? <Alert type="error" showIcon title={jsonError} /> : null}
          {failedCount || unplaced.length ? (
            <Alert
              type="error"
              showIcon
              title={`Còn ${failedCount + unplaced.length} trường cần sửa.`}
              description={
                unplaced.length ? (
                  <ul className="m-0 list-none p-0">
                    {unplaced.map((where) => (
                      <li key={where}>
                        {where}: {SERVER_REFUSED}
                      </li>
                    ))}
                  </ul>
                ) : undefined
              }
            />
          ) : null}
          {mode === "json" ? (
            <Form.Item
              label="Tài liệu (JSON)"
              htmlFor="rule-json"
              layout="vertical"
            >
              <Input.TextArea
                id="rule-json"
                rows={20}
                spellCheck={false}
                value={json}
                onChange={(e) => {
                  touched.current = true;
                  setJson(e.target.value);
                }}
              />
            </Form.Item>
          ) : (
            <Form
              form={form}
              layout="vertical"
              validateTrigger="onBlur"
              scrollToFirstError={{ focus: true }}
              initialValues={initial as Record<string, unknown>}
              onValuesChange={() => {
                touched.current = true;
              }}
              onFinishFailed={({ errorFields }) => {
                setUnplaced([]);
                setFailedCount(errorFields.length);
              }}
              onFinish={() => {
                setUnplaced([]);
                review(current());
              }}
            >
              <RuleFields
                ruleKey={ruleKey}
                root={root}
                form={form}
                base={inForce.document}
              />
            </Form>
          )}
          <ActionError error={error} />
        </div>
      </div>
    </Drawer>
  );
}

/** "sales_kpi@1.0.1 · Riêng của công ty · Đã duyệt · đang áp dụng". */
function startLabel(option: StartOption): string {
  return [
    option.ref,
    RULE_LAYER[option.layer],
    option.status ? RULE_STATUS[option.status] : null,
    option.inForce ? "đang áp dụng" : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
