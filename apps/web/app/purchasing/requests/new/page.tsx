"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { Dayjs } from "dayjs";
import { Alert, App, Button, Card, DatePicker, Flex, Form, Input } from "antd";
import { SendOutlined } from "@ant-design/icons";
import { PageHeader } from "@dw/ui";
import { fromPickerDay } from "../../../../lib/dates";
import { errorMessage } from "../../../../lib/error-message";
import { useIdempotencyKeys } from "../../../../lib/idempotency";
import { purchasingApi } from "../../_lib/api";
import { SCOPE } from "../../_lib/scopes";
import {
  linesOut,
  RequestLines,
  type LineFields,
} from "../../_components/request-lines";
import { purchasingCrumbs, ScopeGate } from "../../_components/frame";

/**
 * A buyer types a request that arrived on paper or as a company form, with
 * its own number, department and requester. Received like any other: the
 * company's form rules decide whether it can be, and DW2 takes it on.
 */
export default function BuyerRequestPage() {
  return (
    <ScopeGate scope={[SCOPE.intake]}>
      <BuyerRequest />
    </ScopeGate>
  );
}

interface Fields {
  pr_no: string;
  department: string;
  requester: string;
  currency: string;
  budget_code?: string;
  need_by?: Dayjs | null;
  note?: string;
  lines: LineFields[];
}

function BuyerRequest() {
  const router = useRouter();
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [sending, setSending] = useState(false);
  const [problems, setProblems] = useState(0);

  async function send(fields: Fields) {
    const request = {
      pr_no: fields.pr_no.trim(),
      department: fields.department.trim(),
      requester: fields.requester.trim(),
      currency: fields.currency.trim().toUpperCase(),
      budget_code: fields.budget_code?.trim() || null,
      need_by: fromPickerDay(fields.need_by),
      note: fields.note?.trim() ?? "",
      lines: linesOut(fields.lines),
    };
    setSending(true);
    try {
      const change = await purchasingApi().submitForm(
        request,
        keys.keyFor("form", request),
      );
      keys.settle("form");
      message.success("Đã nhận yêu cầu mua hàng");
      router.push(`/purchasing/requests/${change.case_id}`);
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={purchasingCrumbs(
          { title: "Hồ sơ mua hàng", href: "/purchasing/requests" },
          "Nhập yêu cầu",
        )}
        title="Nhập yêu cầu mua hàng"
        help="Cho yêu cầu đến bằng giấy hoặc biểu mẫu của công ty. Quy tắc mua hàng của công ty quyết định yêu cầu nhận được hay thiếu gì."
      />
      <Card size="small">
        {problems ? (
          <Alert
            type="error"
            showIcon
            className="mb-4"
            title={`Còn ${problems} trường cần sửa`}
          />
        ) : null}
        <Form<Fields>
          layout="vertical"
          validateTrigger="onBlur"
          scrollToFirstError={{ focus: true }}
          initialValues={{ lines: [{}] }}
          onFinish={(fields) => {
            setProblems(0);
            void send(fields);
          }}
          onFinishFailed={({ errorFields }) => setProblems(errorFields.length)}
        >
          <Flex gap={12} wrap>
            <Form.Item
              name="pr_no"
              label="Số yêu cầu"
              rules={[{ required: true, message: "Ghi số yêu cầu" }]}
            >
              <Input maxLength={48} />
            </Form.Item>
            <Form.Item
              name="department"
              label="Bộ phận"
              rules={[{ required: true, message: "Ghi bộ phận" }]}
            >
              <Input maxLength={80} />
            </Form.Item>
            <Form.Item
              name="requester"
              label="Người yêu cầu"
              rules={[{ required: true, message: "Ghi người yêu cầu" }]}
            >
              <Input maxLength={120} />
            </Form.Item>
            <Form.Item
              name="currency"
              label="Loại tiền"
              rules={[{ required: true, message: "Ghi loại tiền" }]}
            >
              <Input maxLength={3} className="w-24" placeholder="VND" />
            </Form.Item>
            <Form.Item name="budget_code" label="Mã ngân sách">
              <Input maxLength={40} />
            </Form.Item>
            <Form.Item name="need_by" label="Ngày cần hàng">
              <DatePicker format="DD/MM/YYYY" />
            </Form.Item>
          </Flex>
          <RequestLines withItemCode />
          <Form.Item name="note" label="Ghi chú" className="mt-4">
            <Input.TextArea
              autoSize={{ minRows: 2, maxRows: 6 }}
              maxLength={2000}
            />
          </Form.Item>
          <Button
            type="primary"
            size="large"
            htmlType="submit"
            icon={<SendOutlined aria-hidden />}
            loading={sending}
          >
            Nhận yêu cầu
          </Button>
        </Form>
      </Card>
    </div>
  );
}
