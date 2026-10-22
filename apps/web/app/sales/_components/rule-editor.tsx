"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MutableRefObject,
} from "react";
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
  Tooltip,
  Typography,
  Upload,
} from "antd";
import { UploadOutlined } from "@ant-design/icons";
import { ApiError, type SalesSchemas } from "@dw/api-client";
import { LoadError } from "../../../components/load-error";
import { errorCode } from "../../../lib/error-message";
import { salesApi } from "../_lib/api";
import { toBase64 } from "../_lib/catalog";
import { ActionError, detailList } from "../_lib/errors";
import { usePeople } from "../_lib/people";
import {
  DRAFT_ACCEPT,
  DRAFT_STATUS,
  draftChoices,
  draftOption,
  draftProblemText,
  machineRead,
  MAX_DRAFT_BYTES,
  nextVersion,
  parseDocument,
  RULE_KEY,
  RULE_LAYER,
  RULE_STATUS,
  startOptions,
  waitingNotice,
  waitingVersion,
  type RuleDraft,
  type RuleKey,
  type StartOption,
} from "../_lib/rules";
import { pathLabel } from "../_lib/rule-labels";
import {
  formName,
  fromForm,
  holdsPath,
  parseLoc,
  readSchema,
  toForm,
  versionField,
  type DocPath,
  type JsonSchema,
  type RuleNode,
} from "../_lib/rule-schema";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { RuleDiffView } from "./rule-diff-view";
import { RuleFields, type LockedField } from "./rule-form";

/**
 * The rules editor (tickets 38, 40), shared by `/sales/rules` and the process
 * page (`/sales/rules/process`, 2026-10-22): a proposal drawer for one key,
 * which loads the key's schema and the platform's versions, lets a person
 * start from a version, edit it in a form drawn from the schema (or as JSON),
 * read what it changes against the version in force, and send it for
 * approval. It always proposes the WHOLE document: the server validates it
 * again and opens a `sales.rules` approval that someone else decides.
 *
 * `step` limits the form to one process step's fields (the process page's
 * placements, `process_settings.py`): the form's store still holds the whole
 * document, so the other fields go out as they started, and a server refusal
 * of a field the form does not draw is listed above the form rather than
 * put on a field nobody can see.
 *
 * A key holds one proposal waiting at a time (409 `one_open_proposal`): while
 * one waits, the editor says so and does not send; after the server refuses
 * one, this form is not sent again, because it started from a version a
 * decision may have replaced since, and resending it would undo that
 * decision. Reopened, it starts from the version in force.
 */

/** Asks before unsent changes are thrown away (ui-quality §9). */
export function useConfirmDiscard() {
  const { modal } = App.useApp();
  return useCallback(
    (onOk: () => void, title = "Bỏ tài liệu đang sửa?") =>
      modal.confirm({
        title,
        content: "Những thay đổi chưa gửi duyệt sẽ mất.",
        okText: "Bỏ thay đổi",
        okButtonProps: { danger: true },
        cancelText: "Tiếp tục sửa",
        autoFocusButton: "cancel",
        onOk,
      }),
    [modal],
  );
}

/** A form limited to the fields one process step (or lane) reads. */
export interface StepScope {
  /** Where the fields are read, in words: "Đơn hàng · Chờ PIC tự kiểm". */
  label: string;
  /** The document paths drawn, each with its subtree. */
  only: DocPath[];
  /** Drawn but not edited here, each with why. */
  locked: LockedField[];
}

type View = SalesSchemas["RulesInForceView"];

/** The proposal drawer: loads the key's schema and the platform's versions. */
export function ProposeDrawer({
  ruleKey,
  initialStart,
  view,
  scope,
  touched,
  onClose,
  onProposed,
  onHeld,
}: {
  ruleKey: RuleKey;
  initialStart?: string;
  view: View;
  /** Only one step's fields; the whole key when absent. */
  scope?: StepScope;
  /** Whether anything was typed, for a caller that closes it from outside. */
  touched?: MutableRefObject<boolean>;
  onClose: () => void;
  onProposed: () => void;
  /** The server refused it because a proposal waits on the key: reload the view. */
  onHeld?: () => void;
}) {
  const name = usePeople();
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
  const waiting = waitingVersion(view, ruleKey);
  const held = waiting
    ? waitingNotice(waiting, name(waiting.proposed_by))
    : null;
  const title = scope
    ? `Đề xuất phiên bản mới: ${RULE_KEY[ruleKey]} · ${scope.label}`
    : `Đề xuất phiên bản mới: ${RULE_KEY[ruleKey]}`;

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
      draftable={view.draftable.includes(ruleKey)}
      title={title}
      scope={scope}
      held={held}
      touched={touched}
      onClose={onClose}
      onProposed={onProposed}
      onHeld={onHeld}
    />
  );
}

// How often a template the worker is still reading is asked about again,
// and for how long before the page stops asking.
const POLL_MS = 3000;
const POLL_GIVE_UP_MS = 3 * 60 * 1000;
const DRAFT_STALLED = "DW1 chưa đọc xong tệp mẫu, hãy thử tải lại sau.";

type Mode = "form" | "json";
type Step = "edit" | "review";

const SERVER_REFUSED =
  "Máy chủ không nhận giá trị này. Kiểm lại theo hướng dẫn của trường.";
const REFUSED_HELD =
  "Biểu mẫu này không gửi lại được: đóng nó, và khi phiên bản đang chờ đã được quyết định, mở lại để bắt đầu từ phiên bản đang áp dụng.";

/** A start document with the next free version number already in place. */
function prepared(
  root: RuleNode,
  option: StartOption,
  options: readonly StartOption[],
): Record<string, unknown> {
  const field = versionField(root);
  // A new proposal says what it changes: the note of the version it starts
  // from (the platform's, in English) is not that.
  const rest = { ...option.document };
  delete rest.description;
  if (!field) return rest;
  return {
    ...rest,
    [field]: nextVersion(options.map((o) => o.ref)),
  };
}

function Editor({
  ruleKey,
  root,
  options: versions,
  initialStart,
  draftable,
  title,
  scope,
  held,
  touched: outside,
  onClose,
  onProposed,
  onHeld,
}: {
  ruleKey: RuleKey;
  root: RuleNode;
  options: StartOption[];
  initialStart?: string;
  /** Whether a version of this key may be drafted from the company's file. */
  draftable: boolean;
  title: string;
  scope?: StepScope;
  /** A version of the key waits on its approval: nothing is sent until it is decided. */
  held: { title: string; description: string } | null;
  touched?: MutableRefObject<boolean>;
  onClose: () => void;
  onProposed: () => void;
  onHeld?: () => void;
}) {
  const { message } = App.useApp();
  const discard = useConfirmDiscard();
  const { run, pending } = useAction();
  const [form] = Form.useForm();
  // "Tạo từ tệp mẫu": every template uploaded here, the latest last. An
  // earlier draft stays a start option while a later one is read.
  const [drafts, setDrafts] = useState<RuleDraft[]>([]);
  const draft = drafts[drafts.length - 1] ?? null;
  const keepDraft = useCallback(
    (next: RuleDraft) =>
      setDrafts((list) =>
        list.some((d) => d.draft_id === next.draft_id)
          ? list.map((d) => (d.draft_id === next.draft_id ? next : d))
          : [...list, next],
      ),
    [],
  );
  // The draft the page stopped asking about: the API answered with an
  // error, or the worker did not finish within `POLL_GIVE_UP_MS`.
  const [unpolled, setUnpolled] = useState<string | null>(null);
  const options = useMemo(() => {
    const drafted = drafts
      .map(draftOption)
      .filter((o): o is StartOption => o !== null);
    return [...versions, ...drafted];
  }, [versions, drafts]);
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
  // The server refused this form because a proposal waits on the key.
  const [refusedHeld, setRefusedHeld] = useState(false);
  const own = useRef(false);
  const touched = outside ?? own;
  const errorAt = useRef<HTMLDivElement>(null);
  const id = `propose/${ruleKey}`;

  // A new start replaces the whole form: the store is reset to it.
  useEffect(() => {
    form.resetFields();
  }, [initial, form]);

  const current = (): Record<string, unknown> =>
    fromForm(root, form.getFieldsValue(true)) as Record<string, unknown>;

  const confirmDiscard = (onOk: () => void, title?: string) => {
    if (!touched.current) return onOk();
    discard(onOk, title);
  };

  // A refusal is drawn at the top of the form: bring it into view.
  useEffect(() => {
    if (error) errorAt.current?.scrollIntoView?.({ block: "nearest" });
  }, [error]);

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

  // A template the worker has not read yet: asked about again until it has,
  // an error answers, or `POLL_GIVE_UP_MS` passes.
  const polled =
    draft?.status === "queued" && draft.draft_id !== unpolled
      ? draft.draft_id
      : null;
  useEffect(() => {
    if (!polled) return;
    const timer = window.setInterval(() => {
      salesApi()
        .ruleDraft(polled)
        .then(keepDraft, (failure: unknown) => {
          setUnpolled(polled);
          setError(failure);
        });
    }, POLL_MS);
    const giveUp = window.setTimeout(
      () => setUnpolled(polled),
      POLL_GIVE_UP_MS,
    );
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(giveUp);
    };
  }, [polled, keepDraft]);

  // Read, the draft opens as the version to start from (once per draft).
  const opened = useRef<string | null>(null);
  useEffect(() => {
    if (!draft || draft.status === "queued") return;
    if (opened.current === draft.draft_id) return;
    opened.current = draft.draft_id;
    const option = draftOption(draft);
    if (option) choose(option.id);
  });

  const requestDraft = async (file: File) => {
    setError(null);
    if (file.size > MAX_DRAFT_BYTES) {
      void message.error("Tệp lớn hơn 2 MB: bỏ các sheet hoặc dòng không cần.");
      return;
    }
    const body = {
      file_name: file.name,
      content_b64: toBase64(new Uint8Array(await file.arrayBuffer())),
    };
    const result = await run(
      `draft/${ruleKey}`,
      {
        ruleKey,
        name: file.name,
        size: file.size,
        modified: file.lastModified,
      },
      (key) => salesApi().requestRuleDraft(ruleKey, body, key),
      `Đã nhận tệp ${file.name}: DW1 đang đọc, bản nháp tự mở ở đây khi xong.`,
    );
    if (result.ok) keepDraft(result.value);
    else setError(result.error);
  };

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

  /**
   * The server's 422 named fields: put each on its field, the rest above. A
   * field outside the step's (`scope.only`) has no control on screen, so it
   * is listed above too, never put on a field nobody can see.
   */
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
      const name =
        mode === "form" && holdsPath(scope?.only, path)
          ? formName(root, values, path)
          : null;
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
    if (
      result.error instanceof ApiError &&
      result.error.body.details?.rule === "one_open_proposal"
    ) {
      setRefusedHeld(true);
      onHeld?.();
    }
  };

  const close = () => confirmDiscard(onClose);
  const blocked = refusedHeld ? REFUSED_HELD : (held?.title ?? null);
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
            <Tooltip title={blocked}>
              <Button
                type="primary"
                loading={pending === id}
                disabled={blocked !== null}
                onClick={() => void propose()}
              >
                Gửi duyệt
              </Button>
            </Tooltip>
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
        {scope ? (
          <Alert
            type="info"
            showIcon
            title={`Biểu mẫu chỉ hiện các trường của ${scope.label}.`}
            description="Phiên bản gửi duyệt vẫn là toàn bộ quy tắc: các trường không hiện ở đây được gửi đúng như phiên bản bắt đầu, và phần thay đổi bên dưới chỉ liệt kê những gì đã sửa. Sửa cả tài liệu, hoặc dạng JSON, ở trang Quy tắc."
          />
        ) : null}
        {held && !refusedHeld ? (
          <Alert
            type="warning"
            showIcon
            title={held.title}
            description={held.description}
          />
        ) : null}
        <div ref={errorAt} className="space-y-2">
          <ActionError error={error} />
          {refusedHeld ? (
            <Alert type="warning" showIcon title={REFUSED_HELD} />
          ) : null}
        </div>
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
          {draftable ? (
            <Form.Item
              label="Mẫu của công ty"
              layout="vertical"
              extra="Tệp mẫu nhập Bravo của công ty (.xlsx, .xls, tối đa 2 MB). DW1 đọc hàng tiêu đề và gợi ý cột cho từng giá trị; bạn kiểm, xem thay đổi rồi gửi duyệt như mọi phiên bản."
            >
              <Upload
                accept={DRAFT_ACCEPT}
                showUploadList={false}
                maxCount={1}
                beforeUpload={(file) => {
                  void requestDraft(file);
                  return false;
                }}
              >
                <Button
                  icon={<UploadOutlined aria-hidden />}
                  loading={pending === `draft/${ruleKey}` || polled !== null}
                >
                  Tạo từ tệp mẫu
                </Button>
              </Upload>
            </Form.Item>
          ) : null}
          {draft ? (
            <DraftNotice draft={draft} stalled={draft.draft_id === unpolled} />
          ) : null}
          {/* Limited to a step, the form is the only way in: JSON would edit
              the fields drawn read-only here. */}
          {scope ? null : (
            <Segmented<Mode>
              value={mode}
              onChange={switchMode}
              options={[
                { value: "form", label: "Biểu mẫu" },
                { value: "json", label: "JSON nâng cao" },
              ]}
            />
          )}
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
                machineRead={start.draft ? machineRead(start.draft) : undefined}
                choices={start.draft ? draftChoices(start.draft) : undefined}
                only={scope?.only}
                locked={scope?.locked}
              />
            </Form>
          )}
        </div>
      </div>
    </Drawer>
  );
}

/**
 * Where a draft stands, in words: still being read, why it failed, or what
 * opened and what the person still has to settle (the template's columns no
 * value takes, why DW1's mapping was not taken, the template's headers).
 */
function DraftNotice({
  draft,
  stalled,
}: {
  draft: RuleDraft;
  /** The page stopped asking about it while it was still queued. */
  stalled: boolean;
}) {
  const title = `${DRAFT_STATUS[draft.status]}: ${draft.file_name}`;
  if (draft.status === "queued" && stalled)
    return (
      <Alert
        type="warning"
        showIcon
        role="status"
        title={DRAFT_STALLED}
        description={draft.file_name}
      />
    );
  if (draft.status === "queued")
    return (
      <Alert
        type="info"
        showIcon
        role="status"
        title={title}
        description="DW1 đọc tệp trong vùng cách ly; bản nháp tự mở ở đây khi xong."
      />
    );
  if (draft.status === "failed")
    return (
      <Alert type="error" showIcon title={title} description={draft.error} />
    );
  const template = draft.template;
  const ready = draft.status === "ready";
  return (
    <Alert
      type={ready && !draft.problems.length ? "success" : "warning"}
      showIcon
      title={title}
      description={
        <div>
          <Typography.Paragraph className="mb-2!">
            {ready
              ? "Đã mở bản nháp: mỗi trường gắn “Máy đọc” do DW1 đọc từ mẫu, kèm ô đã đọc. Kiểm từng cột trước khi xem thay đổi."
              : "Đã mở bản đang áp dụng với tên sheet của mẫu; các cột chưa đổi, không đoán. Chọn tiêu đề cho từng cột trong danh sách tiêu đề của mẫu."}
          </Typography.Paragraph>
          {draft.problems.length ? (
            <ul className="m-0 mb-2 ps-5">
              {draft.problems.map((p, i) => (
                <li key={`${p.code}-${p.field ?? ""}-${p.ref ?? ""}-${i}`}>
                  {draftProblemText(p)}
                </li>
              ))}
            </ul>
          ) : null}
          {template ? (
            <Typography.Paragraph className="mb-0!">
              Tiêu đề của mẫu (sheet {template.sheet}, hàng {template.row}):{" "}
              {template.headers.map((h) => h.text).join(" · ")}
            </Typography.Paragraph>
          ) : null}
        </div>
      }
    />
  );
}

/** "sales_kpi@1.0.1 · Riêng của công ty · Đã duyệt · đang áp dụng". */
function startLabel(option: StartOption): string {
  if (option.draft)
    return `Bản nháp từ tệp ${option.draft.file_name} · ${DRAFT_STATUS[option.draft.status]}`;
  return [
    option.ref,
    RULE_LAYER[option.layer],
    option.status ? RULE_STATUS[option.status] : null,
    option.inForce ? "đang áp dụng" : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
