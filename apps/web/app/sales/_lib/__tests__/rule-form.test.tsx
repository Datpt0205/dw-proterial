import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Button, Form } from "antd";
import { UiProvider } from "@dw/ui";
import { RuleFields } from "../../_components/rule-form";
import { fromForm, readSchema, toForm, type JsonSchema } from "../rule-schema";

/**
 * The renderer, over a schema with one of each shape Pydantic emits for the
 * rule keys (ticket 40). Field names the label table knows for `sales_kpi`
 * read in Vietnamese; the others show their humanised name.
 */
const SCHEMA: JsonSchema = {
  type: "object",
  $defs: {
    Limits: {
      type: "object",
      properties: { max_pages: { type: "integer", minimum: 1 } },
      required: ["max_pages"],
    },
  },
  properties: {
    order_confirmation_target_hours: {
      type: "integer",
      exclusiveMinimum: 0,
      maximum: 720,
    },
    enabled: { type: "boolean" },
    mode: { type: "string", enum: ["warn", "block_confirmation", "error"] },
    basis: { type: "string", enum: ["fixed", "lme_band"] },
    margin: {
      anyOf: [
        { type: "number", minimum: 0, exclusiveMaximum: 1 },
        { type: "string", pattern: "^[0-9.]+$" },
      ],
    },
    note: { type: "string", minLength: 1, maxLength: 60 },
    body: { type: "string", maxLength: 4000 },
    limits: { $ref: "#/$defs/Limits" },
    band: { anyOf: [{ $ref: "#/$defs/Limits" }, { type: "null" }] },
    mailboxes: { type: "array", items: { type: "string" }, maxItems: 3 },
    per_step: {
      type: "object",
      additionalProperties: { type: "integer" },
      propertyNames: { type: "string", enum: ["O1", "O2"] },
    },
  },
  required: [
    "order_confirmation_target_hours",
    "enabled",
    "mode",
    "basis",
    "margin",
    "note",
    "body",
    "limits",
    "band",
    "mailboxes",
    "per_step",
  ],
};

const DOCUMENT = {
  order_confirmation_target_hours: 8,
  enabled: true,
  mode: "warn",
  basis: "lme_band",
  margin: "0.18",
  note: "ghi chú",
  body: "Dòng 1\nDòng 2",
  limits: { max_pages: 20 },
  band: null,
  mailboxes: ["a@x.example", "b@x.example"],
  per_step: { O1: 5 },
};

const root = readSchema(SCHEMA);

function Harness({
  onDone,
  onFailed = () => {},
}: {
  onDone: (document: unknown) => void;
  onFailed?: (count: number) => void;
}) {
  const [form] = Form.useForm();
  return (
    <UiProvider>
      <Form
        form={form}
        layout="vertical"
        validateTrigger="onBlur"
        initialValues={toForm(root, DOCUMENT) as Record<string, unknown>}
        onFinish={() => onDone(fromForm(root, form.getFieldsValue(true)))}
        onFinishFailed={({ errorFields }) => onFailed(errorFields.length)}
      >
        <RuleFields ruleKey="sales_kpi" root={root} form={form} base={DOCUMENT} />
        <Button htmlType="submit">Gửi</Button>
      </Form>
    </UiProvider>
  );
}

const SLOW = 20_000;

afterEach(() => cleanup());

describe("the schema-driven rules form (ticket 40)", () => {
  it(
    "draws each schema type as its control, with the label table's words or a humanised name",
    () => {
      render(<Harness onDone={() => {}} />);
      const hours = screen.getByRole("spinbutton", {
        name: "Mục tiêu xác nhận đơn hàng",
      }) as HTMLInputElement;
      expect(hours.value).toBe("8");
      expect(screen.getByText("giờ")).toBeTruthy();
      expect(screen.getByRole("switch", { name: "Enabled" })).toBeTruthy();
      // A long choice is a Select, a short one a Segmented, each value in words.
      expect(screen.getByRole("combobox", { name: "Mode" })).toBeTruthy();
      expect(screen.getByText("Cảnh báo, xác nhận được sau khi ghi nhận")).toBeTruthy();
      expect(screen.getByText("Giá cố định")).toBeTruthy();
      expect(screen.getByText("Theo mức LME")).toBeTruthy();
      expect(
        (screen.getByRole("spinbutton", { name: "Margin" }) as HTMLInputElement).value,
      ).toBe("0,18");
      expect(screen.getByRole("textbox", { name: "Note" }).tagName).toBe("INPUT");
      expect(screen.getByRole("textbox", { name: "Body" }).tagName).toBe("TEXTAREA");
      // A nested object is a section; a section that may be off is a switch.
      expect(screen.getByText("Limits")).toBeTruthy();
      expect(screen.getAllByRole("spinbutton", { name: "Max pages" })).toHaveLength(1);
      expect(screen.getByRole("switch", { name: "Dùng band" })).toBeTruthy();
      // A list and a map, with their items.
      expect(screen.getByRole("textbox", { name: "Mục 2" })).toBeTruthy();
      expect(screen.getByRole("combobox", { name: "Mã mục 1" })).toBeTruthy();
      expect(screen.getByText("Đơn hàng, bước 1 (O1)")).toBeTruthy();
    },
    SLOW,
  );

  it(
    "sends the document back as the schema shapes it, decimals as text",
    async () => {
      const done = vi.fn();
      render(<Harness onDone={done} />);
      const margin = screen.getByRole("spinbutton", { name: "Margin" });
      fireEvent.change(margin, { target: { value: "0,25" } });
      fireEvent.blur(margin);
      fireEvent.click(screen.getByRole("switch", { name: "Dùng band" }));
      const pages = await waitFor(() => {
        const both = screen.getAllByRole("spinbutton", { name: "Max pages" });
        expect(both).toHaveLength(2);
        return both[1]!;
      });
      fireEvent.change(pages, { target: { value: "5" } });
      fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
      await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
      expect(done.mock.calls[0]![0]).toEqual({
        ...DOCUMENT,
        margin: "0.25",
        band: { max_pages: 5 },
      });
    },
    SLOW,
  );

  it(
    "checks min and max on blur, and says what is required only on submit",
    async () => {
      const done = vi.fn();
      const failed = vi.fn();
      render(<Harness onDone={done} onFailed={failed} />);
      // Tab past an emptied required field first: nothing is said yet.
      const note = screen.getByRole("textbox", { name: "Note" });
      fireEvent.change(note, { target: { value: "" } });
      fireEvent.blur(note);

      const hours = screen.getByRole("spinbutton", {
        name: "Mục tiêu xác nhận đơn hàng",
      });
      fireEvent.change(hours, { target: { value: "800" } });
      fireEvent.blur(hours);
      expect(await screen.findByText("Không được lớn hơn 720.")).toBeTruthy();
      fireEvent.change(hours, { target: { value: "0" } });
      fireEvent.blur(hours);
      expect(await screen.findByText("Phải lớn hơn 0.")).toBeTruthy();
      // The note's blur was checked before the hours' two: it said nothing.
      await act(() => new Promise((settle) => setTimeout(settle, 500)));
      expect(screen.queryByText("Cần nhập note.")).toBeNull();

      fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
      expect(await screen.findByText("Cần nhập note.")).toBeTruthy();
      await waitFor(() => expect(failed).toHaveBeenCalledWith(2));
      expect(done).not.toHaveBeenCalled();
    },
    SLOW,
  );

  it(
    "adds, removes and reorders list items, within the schema's bounds",
    async () => {
      const done = vi.fn();
      render(<Harness onDone={done} />);
      const list = screen.getByText("Mailboxes").closest(".ant-card") as HTMLElement;
      fireEvent.click(within(list).getByRole("button", { name: "Chuyển mục 2 lên" }));
      fireEvent.click(within(list).getByRole("button", { name: "Thêm mục" }));
      const third = await within(list).findByRole("textbox", { name: "Mục 3" });
      fireEvent.change(third, { target: { value: "c@x.example" } });
      // maxItems 3: no fourth.
      expect(
        (within(list).getByRole("button", { name: "Thêm mục" }) as HTMLButtonElement)
          .disabled,
      ).toBe(true);
      fireEvent.click(within(list).getByRole("button", { name: "Xóa mục 2" }));
      fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
      await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
      expect((done.mock.calls[0]![0] as typeof DOCUMENT).mailboxes).toEqual([
        "b@x.example",
        "c@x.example",
      ]);
    },
    SLOW,
  );

  it(
    "edits a map as key/value rows: a closed key set offers only the keys left",
    async () => {
      const done = vi.fn();
      render(<Harness onDone={done} />);
      const map = screen.getByText("Per step").closest(".ant-card") as HTMLElement;
      fireEvent.click(within(map).getByRole("button", { name: "Thêm mục" }));
      const minutes = await within(map).findAllByRole("spinbutton");
      expect(minutes).toHaveLength(2);
      fireEvent.change(minutes[1]!, { target: { value: "7" } });
      // Both keys of the closed set are used: nothing more to add.
      expect(
        (within(map).getByRole("button", { name: "Thêm mục" }) as HTMLButtonElement)
          .disabled,
      ).toBe(true);
      fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
      await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
      expect((done.mock.calls[0]![0] as typeof DOCUMENT).per_step).toEqual({
        O1: 5,
        O2: 7,
      });

      fireEvent.click(
        within(map).getByRole("button", { name: "Xóa Đơn hàng, bước 1 (O1)" }),
      );
      fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
      await waitFor(() => expect(done).toHaveBeenCalledTimes(2));
      expect((done.mock.calls[1]![0] as typeof DOCUMENT).per_step).toEqual({ O2: 7 });
    },
    SLOW,
  );
});
