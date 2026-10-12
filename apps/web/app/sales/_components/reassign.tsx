"use client";

import { useCallback, useState } from "react";
import { Button, Form, Modal, Select } from "antd";
import { UserSwitchOutlined } from "@ant-design/icons";
import { salesApi } from "../_lib/api";
import { ActionError } from "../_lib/errors";
import type { Viewer } from "../_lib/order-actions";
import { useAction } from "../_lib/use-action";
import { useResource } from "../_lib/use-resource";
import { SCOPE } from "./sales-frame";

/** The Select's value for "nobody": a case every PIC may pick up. */
const NOBODY = "__nobody__";

/**
 * "Phân công lại" (ticket 17): the head gives the case to another member who
 * works this kind of case here, or to nobody. Shown only to a holder of
 * `sales.case.assign`, as the ticket asks; the API refuses everyone else
 * anyway (403), and refuses an assignee it did not offer (422). The list is
 * the API's (`GET .../assignees`), read when the dialog opens, never a roster
 * filtered here. The press carries the case version and an idempotency key.
 */
export function ReassignButton({
  kind,
  caseId,
  caseVersion,
  assignedTo,
  viewer,
  onDone,
}: {
  kind: "order" | "quote";
  caseId: string;
  caseVersion: number;
  assignedTo: string | null;
  viewer: Viewer;
  onDone: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [form] = Form.useForm<{ assignee: string }>();
  const { run, pending } = useAction();
  const candidates = useResource(
    `sales/${kind}/${caseId}/assignees`,
    useCallback(() => salesApi().assignees(kind, caseId), [kind, caseId]),
    { enabled: open },
  );
  if (!viewer.hasScope(SCOPE.assign)) return null;

  const submit = async ({ assignee }: { assignee: string }) => {
    const body = {
      assignee: assignee === NOBODY ? null : assignee,
      case_version: caseVersion,
    };
    const result = await run(
      "reassign",
      body,
      (key) => salesApi().reassign(kind, caseId, body, key),
      body.assignee
        ? "Đã phân công lại hồ sơ"
        : "Đã bỏ phân công: mọi PIC nhận được hồ sơ",
    );
    if (result.ok) {
      setError(null);
      setOpen(false);
      onDone();
    } else setError(result.error);
  };

  return (
    <>
      <Button
        icon={<UserSwitchOutlined aria-hidden />}
        onClick={() => setOpen(true)}
      >
        Phân công lại
      </Button>
      <Modal
        open={open}
        title="Phân công lại hồ sơ"
        okText="Phân công"
        cancelText="Hủy"
        okButtonProps={{ loading: pending === "reassign" }}
        onCancel={() => setOpen(false)}
        onOk={() => form.submit()}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          validateTrigger="onBlur"
          initialValues={{ assignee: assignedTo ?? NOBODY }}
          onFinish={submit}
        >
          <Form.Item
            name="assignee"
            label="Giao cho"
            extra="Chỉ những người làm loại hồ sơ này trong không gian làm việc."
            rules={[
              {
                required: true,
                message: "Chọn người nhận",
                validateTrigger: "onSubmit",
              },
            ]}
          >
            <Select
              loading={candidates.loading}
              showSearch
              optionFilterProp="label"
              options={[
                { value: NOBODY, label: "Không giao ai (mọi PIC nhận được)" },
                ...(candidates.data ?? []).map((m) => ({
                  value: m.user_id,
                  label: m.display_name,
                })),
              ]}
            />
          </Form.Item>
        </Form>
        <ActionError error={candidates.error ?? error} />
      </Modal>
    </>
  );
}
