"use client";

import { useRef, useState } from "react";
import { Alert, Button, Drawer, Form, Grid, Input, Space } from "antd";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import { messageRef } from "../_lib/messages";
import {
  nextSkillVersion,
  type Skill,
  type SkillVersion,
} from "../_lib/skills";
import { useAction } from "../_lib/use-action";
import { useConfirmDiscard } from "./rule-editor";

interface ProposalForm {
  version: string;
  description: string;
  instructions: string;
}

/**
 * "Đề xuất sửa": a whole new text of one skill, sent for the head's approval
 * (ticket 40). From a mail's triage card (ticket 34, ``fromMessage``) it is
 * the mail kinds taught from that mail: the server finds the mail, with its
 * card, in the proposer's own workspace, and the worker's replay reads it
 * with the new text and without it, beside the example mails.
 */
export function ProposeSkill({
  skill,
  versions,
  fromMessage,
  onClose,
  onProposed,
}: {
  skill: Skill;
  versions: readonly SkillVersion[];
  fromMessage?: string;
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
    const body = fromMessage
      ? { ...values, from_message: fromMessage }
      : values;
    const result = await run(
      id,
      { name: skill.name, ...body },
      (key) => salesApi().proposeSkill(skill.name, body, key),
      `Đã gửi duyệt kỹ năng "${skill.name}" ${values.version}. DW1 chạy thử trên thư mẫu${fromMessage ? " và thư này" : ""}, rồi Trưởng bộ phận duyệt trên trang Duyệt.`,
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
      title={
        fromMessage
          ? `Dạy DW1 loại thư từ thư ${messageRef(fromMessage)}`
          : `Đề xuất sửa kỹ năng ${skill.name}`
      }
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
        {fromMessage ? (
          <Alert
            type="info"
            showIcon
            title="Thêm hoặc sửa một loại thư trong phần “The kinds”: một khối bắt đầu bằng “- kind:”, có route là một tuyến có sẵn và label là chữ Sales thấy."
          />
        ) : null}
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
