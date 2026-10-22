"use client";

import { createContext, useContext, type ReactNode } from "react";
import {
  AutoComplete,
  Button,
  Card,
  ConfigProvider,
  Flex,
  Form,
  Input,
  InputNumber,
  Segmented,
  Select,
  Space,
  Switch,
  Typography,
} from "antd";
import type { FormInstance, FormRule } from "antd";
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  PlusOutlined,
} from "@ant-design/icons";
import type { MachineRead, RuleKey } from "../_lib/rules";
import {
  fieldWords,
  placeholderLabel,
  SYSTEM_FIELDS,
  valueLabel,
  VERSION_FIELDS,
} from "../_lib/rule-labels";
import {
  drawsPath,
  holdsPath,
  problem,
  withinPath,
  type DocPath,
  type MapEntry,
  type RuleField,
  type RuleNode,
} from "../_lib/rule-schema";
import { placeholdersIn, unknownPlaceholders } from "../_lib/rule-templates";
import { matches } from "../../../lib/search";
import { ValueStateTag } from "./tags";

/**
 * One form for every rule key (ticket 40): the key's JSON Schema, read by
 * `rule-schema.ts`, drawn field by field with antd controls. No key has a
 * form of its own; what differs between keys is the schema and the words in
 * `rule-labels.ts`.
 *
 * The form holds the document as `rule-schema.ts` `toForm` shapes it (a map
 * as a key/value list, a section that may be off as `{ on, value }`), so the
 * caller converts with `toForm`/`fromForm` at the edges.
 *
 * `only` draws one process step's fields and the sections on the way to them
 * (`drawsPath`); the store still holds the whole document. An entry of a map
 * the step holds only part of keeps its key: the step edits its value, never
 * which entries the map has. `locked` fields are drawn disabled, with why.
 */

/** A field drawn but not edited, and why (the process page's locks). */
export interface LockedField {
  path: DocPath;
  reason: string;
}

interface Ctx {
  ruleKey: RuleKey;
  form: FormInstance;
  /** The version in force, for the placeholders its templates use. */
  base: unknown;
  /** What a draft's machine filled, by document path ("columns.0.header"). */
  machineRead?: Record<string, MachineRead>;
  /** Values a text field offers, by label path ("columns[].header"). */
  choices?: Record<string, string[]>;
  /** The document paths drawn; every field when absent. */
  only?: readonly DocPath[];
  locked?: readonly LockedField[];
}

const RuleFormContext = createContext<Ctx | null>(null);

function useCtx(): Ctx {
  const ctx = useContext(RuleFormContext);
  if (!ctx) throw new Error("RuleFields outside RuleFormContext");
  return ctx;
}

/** The value at a document path, if the document has one there. */
function at(document: unknown, path: DocPath): unknown {
  let current = document;
  for (const step of path) {
    if (current === null || typeof current !== "object") return undefined;
    current = (current as Record<string | number, unknown>)[step];
  }
  return current;
}

/** Labels are looked up with map keys as `*` and list positions as `[]`. */
type Where = {
  /** Name relative to the enclosing Form.List, as antd wants it. */
  name: (string | number)[];
  /** Absolute name in the form, to read what is typed. */
  abs: (string | number)[];
  /** Label path (`emails.*.*.subject`). */
  label: string;
  /** Document path with the real keys, for the version in force. */
  doc: DocPath;
};

function join(label: string, step: string): string {
  return label ? `${label}.${step}` : step;
}

/** Every field of a key's root object, in schema order. */
export function RuleFields({
  ruleKey,
  root,
  form,
  base,
  machineRead,
  choices,
  only,
  locked,
}: {
  ruleKey: RuleKey;
  root: RuleNode;
  form: FormInstance;
  base: unknown;
  machineRead?: Record<string, MachineRead>;
  choices?: Record<string, string[]>;
  /** Draw only these document paths (one process step's), each with its subtree. */
  only?: readonly DocPath[];
  /** Fields drawn disabled, each with why. */
  locked?: readonly LockedField[];
}) {
  if (root.kind !== "object") return null;
  const top = { name: [], abs: [], label: "", doc: [] };
  const system = root.fields.filter((f) => SYSTEM_FIELDS.has(f.name));
  const version = root.fields.filter((f) => VERSION_FIELDS.has(f.name));
  const content = root.fields.filter(
    (f) => !SYSTEM_FIELDS.has(f.name) && !VERSION_FIELDS.has(f.name),
  );
  return (
    <RuleFormContext.Provider
      value={{ ruleKey, form, base, machineRead, choices, only, locked }}
    >
      {/* Set by the system: kept in the document, never a control. */}
      {system.map((f) => (
        <Form.Item key={f.name} name={[f.name]} hidden>
          <Input />
        </Form.Item>
      ))}
      <Fields fields={content} where={top} />
      {/* Every proposal names its number and its note, whatever it edits. */}
      {version.length ? (
        <Section title="Phiên bản">
          <Fields fields={version} where={top} every />
        </Section>
      ) : null}
    </RuleFormContext.Provider>
  );
}

function Fields({
  fields,
  where,
  every,
}: {
  fields: RuleField[];
  where: Where;
  /** Draw every field, whatever `only` says. */
  every?: boolean;
}) {
  const { only } = useCtx();
  const drawn = every
    ? fields
    : fields.filter((f) => drawsPath(only, [...where.doc, f.name]));
  return (
    <>
      {drawn.map((field) => (
        <NodeField
          key={field.name}
          node={field.node}
          required={field.required}
          where={{
            name: [...where.name, field.name],
            abs: [...where.abs, field.name],
            label: join(where.label, field.name),
            doc: [...where.doc, field.name],
          }}
        />
      ))}
    </>
  );
}

/** The schema's checks on what was typed, asked on blur. */
function checks(node: RuleNode): FormRule[] {
  return [
    {
      validator: async (_, value: unknown) => {
        const wrong = problem(node, value);
        if (wrong) throw new Error(wrong);
      },
    },
  ];
}

/** "Bắt buộc" on submit only, never when someone tabs past (ui-quality §9). */
function requiredRule(label: string): FormRule {
  return {
    // A validator, not async-validator's own required check: that one reads
    // every value as a string and refuses a number it holds.
    required: true,
    validateTrigger: "onSubmit",
    validator: async (_, value: unknown) => {
      if (value === null || value === undefined || value === "")
        throw new Error(`Cần nhập ${label.toLowerCase()}.`);
    },
  };
}

/** A field, disabled with its reason where a lock starts. */
function NodeField(props: { node: RuleNode; required: boolean; where: Where }) {
  const { locked } = useCtx();
  const lock = locked?.find(
    (l) =>
      l.path.length === props.where.doc.length &&
      withinPath(props.where.doc, l.path),
  );
  if (!lock) return <NodeControl {...props} />;
  return (
    <ConfigProvider componentDisabled>
      <Typography.Paragraph className="mb-2!">
        <Typography.Text strong>Chỉ xem ở trang này.</Typography.Text>{" "}
        {lock.reason}
      </Typography.Paragraph>
      <NodeControl {...props} />
    </ConfigProvider>
  );
}

function NodeControl({
  node,
  required,
  where,
}: {
  node: RuleNode;
  required: boolean;
  where: Where;
}) {
  const { ruleKey, base, machineRead, choices } = useCtx();
  const words = fieldWords(ruleKey, where.label);
  const read = machineRead?.[where.doc.join(".")];
  if (node.nullable && node.kind !== "text")
    return <Toggle node={node} words={words} where={where} />;
  switch (node.kind) {
    case "object":
      return (
        <Section title={words.label} help={words.help}>
          <Fields fields={node.fields} where={where} />
        </Section>
      );
    case "list":
      return <ListField node={node} where={where} />;
    case "map":
      return <MapField node={node} where={where} />;
    default:
      return (
        <>
          <Form.Item
            name={where.name}
            label={words.label}
            extra={
              read ? (
                <>
                  {words.help}
                  <MachineReadMark abs={where.abs} read={read} />
                </>
              ) : (
                words.help
              )
            }
            rules={[
              ...(required && node.kind !== "switch" && node.kind !== "fixed"
                ? [requiredRule(words.label)]
                : []),
              ...checks(node),
              ...templateRules(node, where, base),
            ]}
          >
            <Control
              node={node}
              unit={words.unit}
              label={words.label}
              choices={choices?.[where.label]}
            />
          </Form.Item>
          <Placeholders node={node} where={where} />
        </>
      );
  }
}

function Section({
  title,
  help,
  extra,
  children,
}: {
  title: ReactNode;
  help?: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  return (
    <Card size="small" title={title} extra={extra} className="mb-4">
      {help ? <Typography.Paragraph>{help}</Typography.Paragraph> : null}
      {children}
    </Card>
  );
}

/** A section the document may leave out (null): a switch, then its fields. */
function Toggle({
  node,
  words,
  where,
}: {
  node: RuleNode;
  words: { label: string; help?: string };
  where: Where;
}) {
  const inner = { ...node, nullable: false } as RuleNode;
  return (
    <Section title={words.label} help={words.help}>
      <Form.Item
        name={[...where.name, "on"]}
        label={`Dùng ${words.label.toLowerCase()}`}
        valuePropName="checked"
      >
        <Switch />
      </Form.Item>
      <Form.Item noStyle dependencies={[[...where.abs, "on"]]}>
        {({ getFieldValue }) =>
          getFieldValue([...where.abs, "on"]) ? (
            inner.kind === "object" ? (
              <Fields
                fields={inner.fields}
                where={{
                  ...where,
                  name: [...where.name, "value"],
                  abs: [...where.abs, "value"],
                }}
              />
            ) : (
              <NodeField
                node={inner}
                required
                where={{
                  ...where,
                  name: [...where.name, "value"],
                  abs: [...where.abs, "value"],
                }}
              />
            )
          ) : null
        }
      </Form.Item>
    </Section>
  );
}

/** Segmented for a short choice, Select for a long one. */
function shortChoice(values: string[]): boolean {
  return values.length <= 3 && values.every((v) => valueLabel(v).length <= 28);
}

function Control({
  node,
  unit,
  label,
  value,
  onChange,
  onBlur,
  id,
  choices,
}: {
  node: RuleNode;
  unit?: string;
  label: string;
  value?: unknown;
  onChange?: (value: unknown) => void;
  /** Form.Item's: a field is checked when it is left (`validateTrigger="onBlur"`). */
  onBlur?: () => void;
  id?: string;
  /** Values a text field offers (a template's headers), still free to type. */
  choices?: string[];
}) {
  switch (node.kind) {
    case "switch":
      return (
        <Switch
          id={id}
          checked={Boolean(value)}
          onChange={(checked) => onChange?.(checked)}
          checkedChildren="Bật"
          unCheckedChildren="Tắt"
        />
      );
    case "choice":
      return shortChoice(node.values) ? (
        <Segmented
          value={value as string}
          onChange={(v) => onChange?.(v)}
          options={node.values.map((v) => ({ value: v, label: valueLabel(v) }))}
        />
      ) : (
        <Select
          id={id}
          aria-label={label}
          value={value as string}
          onChange={(v) => onChange?.(v)}
          onBlur={onBlur}
          options={node.values.map((v) => ({ value: v, label: valueLabel(v) }))}
          className="w-full"
          showSearch={{ filterOption: viFilter }}
        />
      );
    case "number":
      return (
        <InputNumber
          id={id}
          value={value as string | number | null}
          onChange={(v) => onChange?.(v)}
          onBlur={onBlur}
          aria-label={label}
          // No min, max or precision here: InputNumber would change what was
          // typed on blur without a word; the schema's check says it instead.
          step={node.integer ? 1 : node.decimal ? "0.01" : 0.01}
          stringMode={node.decimal}
          decimalSeparator=","
          parser={(text) => (text ?? "").replace(/\s/g, "").replace(",", ".")}
          suffix={unit}
          className="w-full max-w-xs"
        />
      );
    case "fixed":
      return (
        <Typography.Text id={id} code>
          {String(node.value)}
        </Typography.Text>
      );
    case "text": {
      if (choices?.length && !node.multiline)
        return (
          <AutoComplete
            id={id}
            aria-label={label}
            value={(value as string | null) ?? ""}
            onChange={(v: string) => onChange?.(v)}
            onBlur={onBlur}
            options={choices.map((c) => ({ value: c, label: c }))}
            showSearch={{ filterOption: viFilter }}
            className="w-full"
          />
        );
      const common = {
        id,
        value: (value as string | null) ?? "",
        onChange: (e: { target: { value: string } }) =>
          onChange?.(e.target.value),
        onBlur,
        maxLength: node.maxLength,
        spellCheck: true,
      };
      return node.multiline ? (
        <Input.TextArea {...common} autoSize={{ minRows: 2, maxRows: 16 }} />
      ) : (
        <Input {...common} />
      );
    }
    default:
      return null;
  }
}

/**
 * "Máy đọc · Đọc từ Mẫu!C3": a value a draft's machine filled, for as long as
 * the field still holds it. Edited, it is the person's and the mark goes.
 */
function MachineReadMark({
  abs,
  read,
}: {
  abs: (string | number)[];
  read: MachineRead;
}) {
  const { form } = useCtx();
  const value: unknown = Form.useWatch(abs, form);
  if (value !== read.value) return null;
  return (
    <span className="ms-2 inline-flex flex-wrap items-center gap-1">
      <ValueStateTag state="dw" />
      <Typography.Text type="secondary">Đọc từ {read.evidence}</Typography.Text>
    </span>
  );
}

/** "ha noi" finds "Hà Nội" (ui-quality §8), by label or by code. */
function viFilter(
  input: string,
  option?: { label?: unknown; value?: unknown },
): boolean {
  return matches(input, [
    String(option?.label ?? ""),
    String(option?.value ?? ""),
  ]);
}

// ----------------------------------------------------------- templates --

/** What a template field may name: the schema's own list, else what the version in force uses. */
function templateRules(
  node: RuleNode,
  where: Where,
  base: unknown,
): FormRule[] {
  if (node.kind !== "text") return [];
  return [
    {
      // A placeholder the schema does not list is refused by the server; say so first.
      validator: async (_, value: unknown) => {
        if (!node.placeholders || typeof value !== "string") return;
        const wrong = unknownPlaceholders(value, node.placeholders, "braces");
        if (wrong.length)
          throw new Error(
            `Mẫu này không có giá trị ${wrong.join(", ")}. Dùng một trong: ${node.placeholders.join(" ")}.`,
          );
      },
    },
    {
      warningOnly: true,
      validator: async (_, value: unknown) => {
        if (node.placeholders || typeof value !== "string") return;
        const known = placeholdersHere(base, where);
        if (!known) return;
        const wrong = unknownPlaceholders(value, known, "dollar");
        if (wrong.length)
          throw new Error(
            `Bản đang áp dụng không dùng ${wrong.join(", ")} ở trường này: nếu hồ sơ không có giá trị đó, tài liệu sẽ không tạo được.`,
          );
      },
    },
  ];
}

function placeholdersHere(base: unknown, where: Where): string[] | null {
  const text = at(base, where.doc);
  return typeof text === "string" ? placeholdersIn(text) : null;
}

/** The names a template may use, under the field. */
function Placeholders({ node, where }: { node: RuleNode; where: Where }) {
  const { base } = useCtx();
  if (node.kind !== "text") return null;
  const names = node.placeholders ?? placeholdersHere(base, where);
  if (!names?.length) return null;
  return (
    <Typography.Paragraph className="-mt-3! mb-4!">
      {node.placeholders
        ? "Giá trị dùng được (bấm biểu tượng để chép, rồi dán vào nội dung): "
        : "Giá trị bản đang áp dụng dùng ở trường này: "}
      {names.map((name) => (
        <span key={name} className="me-3 inline-block">
          {placeholderLabel(name)}{" "}
          <Typography.Text
            code
            copyable={{
              text: name,
              tooltips: [`Chép ${name}`, "Đã chép"],
            }}
          >
            {name}
          </Typography.Text>
        </span>
      ))}
    </Typography.Paragraph>
  );
}

// --------------------------------------------------------------- lists --

function moveButtons(
  index: number,
  count: number,
  move: (from: number, to: number) => void,
  remove: (index: number) => void,
  what: string,
  removable: boolean,
) {
  return (
    <Space size={4}>
      <Button
        size="small"
        icon={<ArrowUpOutlined aria-hidden />}
        aria-label={`Chuyển ${what} lên`}
        disabled={index === 0}
        onClick={() => move(index, index - 1)}
      />
      <Button
        size="small"
        icon={<ArrowDownOutlined aria-hidden />}
        aria-label={`Chuyển ${what} xuống`}
        disabled={index === count - 1}
        onClick={() => move(index, index + 1)}
      />
      <Button
        size="small"
        danger
        icon={<DeleteOutlined aria-hidden />}
        aria-label={`Xóa ${what}`}
        disabled={!removable}
        onClick={() => remove(index)}
      />
    </Space>
  );
}

function ListField({
  node,
  where,
}: {
  node: Extract<RuleNode, { kind: "list" }>;
  where: Where;
}) {
  const { ruleKey } = useCtx();
  const words = fieldWords(ruleKey, where.label);
  const item = words.item ?? "Mục";
  const itemLabel = `${where.label}[]`;
  return (
    <Section title={words.label} help={words.help}>
      <Form.List
        name={where.name}
        rules={[
          {
            validator: async (_, value: unknown[]) => {
              const wrong = problem(node, value ?? []);
              if (wrong) throw new Error(wrong);
            },
          },
        ]}
      >
        {(fields, { add, remove, move }, { errors }) => (
          <>
            {fields.map((field, index) => {
              const what = `${item.toLowerCase()} ${index + 1}`;
              const buttons = moveButtons(
                index,
                fields.length,
                move,
                remove,
                what,
                fields.length > (node.minItems ?? 0),
              );
              const child: Where = {
                name: [field.name],
                abs: [...where.abs, field.name],
                label: itemLabel,
                doc: [...where.doc, index],
              };
              return node.item.kind === "object" ? (
                <Section
                  key={field.key}
                  title={`${item} ${index + 1}`}
                  extra={buttons}
                >
                  <Fields fields={node.item.fields} where={child} />
                </Section>
              ) : (
                <Flex key={field.key} gap="small" align="start">
                  <div className="min-w-0 flex-1">
                    <Form.Item
                      name={[field.name]}
                      label={`${item} ${index + 1}`}
                      rules={[requiredRule(item), ...checks(node.item)]}
                    >
                      <Control
                        node={node.item}
                        label={`${item} ${index + 1}`}
                      />
                    </Form.Item>
                  </div>
                  <div className="pt-8">{buttons}</div>
                </Flex>
              );
            })}
            <Form.ErrorList errors={errors} />
            <Button
              icon={<PlusOutlined aria-hidden />}
              disabled={
                node.maxItems !== undefined && fields.length >= node.maxItems
              }
              onClick={() => add(emptyItem(node.item))}
            >
              Thêm {item.toLowerCase()}
            </Button>
          </>
        )}
      </Form.List>
    </Section>
  );
}

/** What an added item starts as. */
function emptyItem(node: RuleNode): unknown {
  switch (node.kind) {
    case "object":
      return Object.fromEntries(
        node.fields.map((f) => [
          f.name,
          f.node.kind === "fixed"
            ? f.node.value
            : f.node.kind === "map" || f.node.kind === "list"
              ? []
              : f.node.kind === "switch"
                ? false
                : f.node.nullable && f.node.kind !== "text"
                  ? {
                      on: false,
                      value: emptyItem({
                        ...f.node,
                        nullable: false,
                      } as RuleNode),
                    }
                  : (f.default ?? (f.node.kind === "text" ? "" : null)),
        ]),
      );
    case "text":
      return "";
    case "switch":
      return false;
    default:
      return null;
  }
}

// ---------------------------------------------------------------- maps --

function MapField({
  node,
  where,
}: {
  node: Extract<RuleNode, { kind: "map" }>;
  where: Where;
}) {
  const { ruleKey, form, only } = useCtx();
  const words = fieldWords(ruleKey, where.label);
  const item = words.item ?? "Mục";
  const valueText = words.value ?? "Nội dung";
  // A step that holds only some entries edits their values, never the set.
  const whole = holdsPath(only, where.doc);
  const entries = (): MapEntry[] =>
    (form.getFieldValue(where.abs) as MapEntry[] | undefined) ?? [];
  const keyRules: FormRule[] = [
    requiredRule(`mã ${item}`),
    {
      validator: async (_, key: string | undefined) => {
        if (!key) return;
        if (node.keyPattern && !node.keyEnum) {
          const wrong = problem(
            {
              kind: "text",
              pattern: node.keyPattern,
              multiline: false,
              nullable: false,
            },
            key,
          );
          if (wrong) throw new Error(wrong);
        }
        if (entries().filter((e) => e?.key === key).length > 1)
          throw new Error(`Mã ${key} đã có ở mục khác.`);
      },
    },
  ];
  return (
    <Section title={words.label} help={words.help}>
      <Form.List name={where.name}>
        {(fields, { add, remove }) => {
          const all = entries();
          const used = new Set(all.map((e) => e?.key));
          const free = node.keyEnum?.filter((k) => !used.has(k)) ?? [];
          const drawn = whole
            ? fields
            : fields.filter((field) =>
                drawsPath(only, [...where.doc, all[field.name]?.key ?? ""]),
              );
          return (
            <>
              {drawn.map((field, index) => (
                <MapEntryRow
                  key={field.key}
                  node={node}
                  index={index}
                  fieldName={field.name}
                  where={where}
                  item={item}
                  valueLabel={valueText}
                  keyRules={keyRules}
                  fixedKey={!whole}
                  onRemove={() => remove(field.name)}
                />
              ))}
              {whole ? (
                <Button
                  icon={<PlusOutlined aria-hidden />}
                  disabled={node.keyEnum !== undefined && free.length === 0}
                  onClick={() =>
                    add({ key: free[0] ?? "", value: emptyItem(node.value) })
                  }
                >
                  Thêm {item.toLowerCase()}
                </Button>
              ) : null}
            </>
          );
        }}
      </Form.List>
    </Section>
  );
}

function MapEntryRow({
  node,
  index,
  fieldName,
  where,
  item,
  valueLabel: valueText,
  keyRules,
  fixedKey,
  onRemove,
}: {
  node: Extract<RuleNode, { kind: "map" }>;
  index: number;
  fieldName: number;
  where: Where;
  item: string;
  valueLabel: string;
  keyRules: FormRule[];
  /** The entry's key is kept as it is: no key control, no remove. */
  fixedKey: boolean;
  onRemove: () => void;
}) {
  const { form, base } = useCtx();
  const abs = [...where.abs, fieldName];
  const watched = Form.useWatch([...abs, "key"], form) as string | undefined;
  // Before the first watch settles, the store already knows the key.
  const key =
    watched ?? (form.getFieldValue([...abs, "key"]) as string | undefined);
  const title = key ? valueLabel(key) : `${item} ${index + 1}`;
  const keyControl = node.keyEnum ? (
    <Select
      aria-label={`Mã ${item.toLowerCase()} ${index + 1}`}
      options={node.keyEnum.map((k) => ({ value: k, label: valueLabel(k) }))}
      showSearch={{ filterOption: viFilter }}
      className="w-full"
    />
  ) : (
    <Input
      aria-label={`Mã ${item.toLowerCase()} ${index + 1}`}
      spellCheck={false}
    />
  );
  const child: Where = {
    name: [fieldName, "value"],
    abs: [...abs, "value"],
    label: `${where.label}.*`,
    doc: [...where.doc, key ?? ""],
  };
  const removeButton = fixedKey ? null : (
    <Button
      size="small"
      danger
      icon={<DeleteOutlined aria-hidden />}
      aria-label={`Xóa ${title}`}
      onClick={onRemove}
    />
  );
  if (fixedKey && node.value.kind !== "object" && node.value.kind !== "map")
    return (
      <>
        <Form.Item
          name={child.name}
          label={title}
          rules={[
            requiredRule(valueText),
            ...checks(node.value),
            ...templateRules(node.value, child, base),
          ]}
        >
          <Control node={node.value} label={`${valueText}: ${title}`} />
        </Form.Item>
        <Placeholders node={node.value} where={child} />
      </>
    );
  if (node.value.kind === "object" || node.value.kind === "map")
    return (
      <Section title={title} extra={removeButton}>
        <Form.Item
          name={[fieldName, "key"]}
          label={`Mã ${item.toLowerCase()}`}
          rules={keyRules}
          hidden={fixedKey}
        >
          {keyControl}
        </Form.Item>
        {node.value.kind === "object" ? (
          <Fields fields={node.value.fields} where={child} />
        ) : (
          <NodeField node={node.value} required where={child} />
        )}
      </Section>
    );
  return (
    <Flex gap="small" align="start" wrap>
      <div className="min-w-48 flex-1">
        <Form.Item
          name={[fieldName, "key"]}
          label={`${item} ${index + 1}`}
          rules={keyRules}
        >
          {keyControl}
        </Form.Item>
      </div>
      <div className="min-w-48 flex-2">
        <Form.Item
          name={child.name}
          label={valueText}
          rules={[
            requiredRule(valueText),
            ...checks(node.value),
            ...templateRules(node.value, child, base),
          ]}
        >
          <Control node={node.value} label={`${valueText}: ${title}`} />
        </Form.Item>
        <Placeholders node={node.value} where={child} />
      </div>
      <div className="pt-8">{removeButton}</div>
    </Flex>
  );
}
