"use client";

import { createContext, useContext, type ReactNode } from "react";
import {
  Button,
  Card,
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
import type { RuleKey } from "../_lib/rules";
import { fieldWords, valueLabel } from "../_lib/rule-labels";
import {
  problem,
  type DocPath,
  type MapEntry,
  type RuleField,
  type RuleNode,
} from "../_lib/rule-schema";
import { placeholdersIn, unknownPlaceholders } from "../_lib/rule-templates";
import { matches } from "../../../lib/search";

/**
 * One form for every rule key (ticket 40): the key's JSON Schema, read by
 * `rule-schema.ts`, drawn field by field with antd controls. No key has a
 * form of its own; what differs between keys is the schema and the words in
 * `rule-labels.ts`.
 *
 * The form holds the document as `rule-schema.ts` `toForm` shapes it (a map
 * as a key/value list, a section that may be off as `{ on, value }`), so the
 * caller converts with `toForm`/`fromForm` at the edges.
 */

interface Ctx {
  ruleKey: RuleKey;
  form: FormInstance;
  /** The version in force, for the placeholders its templates use. */
  base: unknown;
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
}: {
  ruleKey: RuleKey;
  root: RuleNode;
  form: FormInstance;
  base: unknown;
}) {
  if (root.kind !== "object") return null;
  return (
    <RuleFormContext.Provider value={{ ruleKey, form, base }}>
      <Fields
        fields={root.fields}
        where={{ name: [], abs: [], label: "", doc: [] }}
      />
    </RuleFormContext.Provider>
  );
}

function Fields({ fields, where }: { fields: RuleField[]; where: Where }) {
  return (
    <>
      {fields.map((field) => (
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
    required: true,
    message: `Cần nhập ${label.toLowerCase()}.`,
    validateTrigger: "onSubmit",
  };
}

function NodeField({
  node,
  required,
  where,
}: {
  node: RuleNode;
  required: boolean;
  where: Where;
}) {
  const { ruleKey, base } = useCtx();
  const words = fieldWords(ruleKey, where.label);
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
            extra={words.help}
            rules={[
              ...(required && node.kind !== "switch" && node.kind !== "fixed"
                ? [requiredRule(words.label)]
                : []),
              ...checks(node),
              ...templateRules(node, where, base),
            ]}
          >
            <Control node={node} unit={words.unit} label={words.label} />
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
  return (
    values.length <= 3 && values.every((v) => valueLabel(v).length <= 28)
  );
}

function Control({
  node,
  unit,
  label,
  value,
  onChange,
  id,
}: {
  node: RuleNode;
  unit?: string;
  label: string;
  value?: unknown;
  onChange?: (value: unknown) => void;
  id?: string;
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
      const common = {
        id,
        value: (value as string | null) ?? "",
        onChange: (e: { target: { value: string } }) =>
          onChange?.(e.target.value),
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
        ? "Giá trị dùng được: "
        : "Giá trị bản đang áp dụng dùng ở trường này: "}
      {names.map((name) => (
        <Typography.Text key={name} code>
          {name}
        </Typography.Text>
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
                <Section key={field.key} title={`${item} ${index + 1}`} extra={buttons}>
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
                      <Control node={node.item} label={`${item} ${index + 1}`} />
                    </Form.Item>
                  </div>
                  <div className="pt-8">{buttons}</div>
                </Flex>
              );
            })}
            <Form.ErrorList errors={errors} />
            <Button
              icon={<PlusOutlined aria-hidden />}
              disabled={node.maxItems !== undefined && fields.length >= node.maxItems}
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
                  ? { on: false, value: emptyItem({ ...f.node, nullable: false } as RuleNode) }
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
  const { ruleKey, form } = useCtx();
  const words = fieldWords(ruleKey, where.label);
  const item = words.item ?? "Mục";
  const valueText = words.value ?? "Nội dung";
  const entries = (): MapEntry[] =>
    (form.getFieldValue(where.abs) as MapEntry[] | undefined) ?? [];
  const keyRules: FormRule[] = [
    requiredRule(`mã ${item}`),
    {
      validator: async (_, key: string | undefined) => {
        if (!key) return;
        if (node.keyPattern && !node.keyEnum) {
          const wrong = problem(
            { kind: "text", pattern: node.keyPattern, multiline: false, nullable: false },
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
          const used = new Set(entries().map((e) => e?.key));
          const free = node.keyEnum?.filter((k) => !used.has(k)) ?? [];
          return (
            <>
              {fields.map((field, index) => (
                <MapEntryRow
                  key={field.key}
                  node={node}
                  index={index}
                  fieldName={field.name}
                  where={where}
                  item={item}
                  valueLabel={valueText}
                  keyRules={keyRules}
                  onRemove={() => remove(field.name)}
                />
              ))}
              <Button
                icon={<PlusOutlined aria-hidden />}
                disabled={node.keyEnum !== undefined && free.length === 0}
                onClick={() =>
                  add({ key: free[0] ?? "", value: emptyItem(node.value) })
                }
              >
                Thêm {item.toLowerCase()}
              </Button>
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
  onRemove,
}: {
  node: Extract<RuleNode, { kind: "map" }>;
  index: number;
  fieldName: number;
  where: Where;
  item: string;
  valueLabel: string;
  keyRules: FormRule[];
  onRemove: () => void;
}) {
  const { form, base } = useCtx();
  const abs = [...where.abs, fieldName];
  const key = Form.useWatch([...abs, "key"], form) as string | undefined;
  const title = key ? valueLabel(key) : `${item} ${index + 1}`;
  const keyControl = node.keyEnum ? (
    <Select
      aria-label={`Mã ${item.toLowerCase()} ${index + 1}`}
      options={node.keyEnum.map((k) => ({ value: k, label: valueLabel(k) }))}
      showSearch={{ filterOption: viFilter }}
      className="w-full"
    />
  ) : (
    <Input aria-label={`Mã ${item.toLowerCase()} ${index + 1}`} spellCheck={false} />
  );
  const child: Where = {
    name: [fieldName, "value"],
    abs: [...abs, "value"],
    label: `${where.label}.*`,
    doc: [...where.doc, key ?? ""],
  };
  const removeButton = (
    <Button
      size="small"
      danger
      icon={<DeleteOutlined aria-hidden />}
      aria-label={`Xóa ${title}`}
      onClick={onRemove}
    />
  );
  if (node.value.kind === "object" || node.value.kind === "map")
    return (
      <Section title={title} extra={removeButton}>
        <Form.Item name={[fieldName, "key"]} label={`Mã ${item.toLowerCase()}`} rules={keyRules}>
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
        <Form.Item name={[fieldName, "key"]} label={`${item} ${index + 1}`} rules={keyRules}>
          {keyControl}
        </Form.Item>
      </div>
      <div className="min-w-48 flex-2">
        <Form.Item
          name={child.name}
          label={valueText}
          rules={[requiredRule(valueText), ...checks(node.value), ...templateRules(node.value, child, base)]}
        >
          <Control node={node.value} label={`${valueText}: ${title}`} />
        </Form.Item>
        <Placeholders node={node.value} where={child} />
      </div>
      <div className="pt-8">{removeButton}</div>
    </Flex>
  );
}
