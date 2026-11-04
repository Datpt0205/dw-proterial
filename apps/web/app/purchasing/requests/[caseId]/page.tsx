"use client";

import { useCallback, useState } from "react";
import { useParams } from "next/navigation";
import {
  Alert,
  App,
  Button,
  Card,
  Descriptions,
  Flex,
  Skeleton,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import {
  DownloadOutlined,
  ExclamationCircleOutlined,
  EyeOutlined,
  FileTextOutlined,
  SendOutlined,
} from "@ant-design/icons";
import type { Approval, PurchaseCase, PurchasingSchemas } from "@dw/api-client";
import { InfoTip, PageHeader, StatusTag } from "@dw/ui";
import { LoadError } from "../../../../components/load-error";
import { formatDate, formatDateTime } from "../../../../lib/dates";
import { errorMessage } from "../../../../lib/error-message";
import { useIdempotencyKeys } from "../../../../lib/idempotency";
import { formatQuantity } from "../../../../lib/money";
import { apiClient } from "../../../../lib/session";
import { useAuth } from "../../../../lib/auth/auth-context";
import { useCachedResource } from "../../../../lib/use-cached-resource";
import { purchasingApi } from "../../_lib/api";
import { money } from "../../_lib/format";
import { BASIS, FINDING } from "../../_lib/labels";
import { usePeople } from "../../_lib/people";
import { SCOPE } from "../../_lib/scopes";
import { CaseHistory } from "../../_components/case-history";
import { DecideApproval } from "../../_components/decide-approval";
import { purchasingCrumbs, ScopeGate } from "../../_components/frame";
import { CaseStatusTag, MarkTag } from "../../_components/tags";
import { OrderFollowUp, useConfirmationMails } from "./follow-up";
import { NamedSuppliers, Sourcing } from "./sourcing";

type Check = PurchasingSchemas["CrossCheck"];

/**
 * One purchase case: what it asks for, whether it can move on and what the
 * viewer can do next (ui-quality §2), then the check, the quotes and the
 * orders, and what DW2 and each person did. Every action is the server's to
 * refuse; a button is disabled with its reason where the viewer's role or the
 * case's state does not allow it.
 */
export default function CasePage() {
  return (
    <ScopeGate scope={[SCOPE.read, SCOPE.readOwn]}>
      <CaseView />
    </ScopeGate>
  );
}

function CaseView() {
  const { caseId } = useParams<{ caseId: string }>();
  const actor = usePeople();
  const found = useCachedResource(
    `purchasing/case/${caseId}`,
    useCallback(() => purchasingApi().case(caseId), [caseId]),
  );
  const c = found.data;

  if (found.error && !c)
    return <LoadError error={found.error} onRetry={found.reload} />;
  if (!c) return <Skeleton active paragraph={{ rows: 8 }} />;

  return (
    <div className="space-y-4">
      <PageHeader
        breadcrumb={purchasingCrumbs(
          { title: "Hồ sơ mua hàng", href: "/purchasing/requests" },
          c.request.pr_no,
        )}
        title={`Yêu cầu ${c.request.pr_no}`}
        subtitle={`${c.request.department} · ${c.request.requester} · nhận ${formatDateTime(c.received_at)}`}
        tags={<CaseStatusTag status={c.status} />}
      />
      <NextStep c={c} onChanged={found.reload} />
      <Card size="small" title="Dòng hàng">
        <RequestLines c={c} />
      </Card>
      <CheckCard c={c} />
      {c.rfq || c.status === "approved" ? (
        <Sourcing c={c} onChanged={found.reload} />
      ) : null}
      {c.po ? <OrdersCard c={c} onChanged={found.reload} /> : null}
      <Card size="small" title="DW2 và mọi người đã làm gì">
        <CaseHistory c={c} actor={actor} />
      </Card>
    </div>
  );
}

// ----------------------------------------------------------- next step --

const OWN_WORDS: Record<PurchaseCase["status"], string> = {
  received:
    "Phòng Mua hàng đã nhận. DW2 đối chiếu rồi gửi người duyệt theo số tiền; bạn được báo khi có quyết định.",
  awaiting_approval: "Đang chờ người duyệt quyết định.",
  approved: "Đã duyệt. Phòng Mua hàng đang hỏi giá nhà cung cấp.",
  rejected: "Yêu cầu bị từ chối. Lý do ở phần lịch sử bên dưới.",
  rfq_drafted: "Phòng Mua hàng đang hỏi giá nhà cung cấp.",
  awaiting_reapproval:
    "Giá chọn được vượt hạn mức đã duyệt: đang chờ duyệt lại.",
  supplier_selected:
    "Đã chọn nhà cung cấp. Phòng Mua hàng đang soạn đơn đặt hàng.",
  po_drafted: "Đơn đặt hàng đã soạn; phòng Mua hàng nhập vào Bravo.",
};

/** The one thing the case waits on, and the button that does it. */
function NextStep({
  c,
  onChanged,
}: {
  c: PurchaseCase;
  onChanged: () => void;
}) {
  const { hasScope } = useAuth();
  const { message } = App.useApp();
  const keys = useIdempotencyKeys();
  const [pending, setPending] = useState<string | null>(null);
  // Why the last press was refused, kept beside the button: a refusal the
  // person must act on never lives only in a toast (ui-quality §10).
  const [refused, setRefused] = useState<string | null>(null);
  // Suppliers the buyer names per line, for a line the master data lists
  // nobody for (or one more for a line).
  const [named, setNamed] = useState<Record<number, string[]>>({});

  async function act(
    id: string,
    run: (key: string) => Promise<unknown>,
    done: string,
  ) {
    const action = `${id}:${c.case_id}:${c.case_version}`;
    setPending(id);
    setRefused(null);
    try {
      await run(keys.keyFor(action, null));
      keys.settle(action);
      message.success(done);
      onChanged();
    } catch (error) {
      setRefused(errorMessage(error));
      onChanged();
    } finally {
      setPending(null);
    }
  }

  const api = purchasingApi();
  const button = (
    id: string,
    label: string,
    scope: string,
    icon: React.ReactNode,
    run: (key: string) => Promise<unknown>,
    done: string,
  ) => {
    const why = hasScope(scope) ? null : "Vai của bạn không gồm bước này.";
    return (
      <Flex gap={8} align="center" wrap>
        <Tooltip title={why}>
          <Button
            type="primary"
            size="large"
            icon={icon}
            disabled={why !== null || (pending !== null && pending !== id)}
            loading={pending === id}
            onClick={() => void act(id, run, done)}
          >
            {label}
          </Button>
        </Tooltip>
        {why ? <Typography.Text role="note">{why}</Typography.Text> : null}
      </Flex>
    );
  };

  const reviewPending = c.review && !c.review.reviewed_at;
  // A requester follows their own request; every step on it is someone
  // else's, so they are told where it stands, never shown a button they
  // cannot ever press.
  if (!hasScope(SCOPE.read)) {
    return (
      <Card size="small" title="Yêu cầu của bạn đang ở đâu">
        <Typography.Text>{OWN_WORDS[c.status]}</Typography.Text>
      </Card>
    );
  }
  let body: React.ReactNode = null;
  let say = "";
  if (c.status === "received" && reviewPending) {
    say = c.read_from?.scanned
      ? "DW2 đọc yêu cầu này từ bản scan: so từng dòng với bản giấy."
      : "DW2 đọc yêu cầu này từ thư: xem lại các dòng hàng.";
    body = button(
      "review",
      "Đã xem, cho DW2 gửi duyệt",
      SCOPE.intake,
      <EyeOutlined aria-hidden />,
      (key) => api.review(c.case_id, c.case_version, key),
      "Đã ghi bạn xem lại yêu cầu",
    );
  } else if (c.status === "received") {
    say = "Chờ gửi duyệt.";
    body = button(
      "submit",
      "Gửi duyệt",
      SCOPE.submit,
      <SendOutlined aria-hidden />,
      (key) => api.submit(c.case_id, c.case_version, key),
      "Đã gửi duyệt",
    );
  } else if (c.status === "awaiting_approval" && c.approval) {
    return (
      <WaitingApproval
        c={c}
        approvalId={c.approval.approval_id}
        onChanged={onChanged}
        say={`Chờ ${c.approval.tier_label} duyệt. Gửi lúc ${formatDateTime(c.approval.submitted_at)}.`}
      />
    );
  } else if (c.status === "awaiting_reapproval" && c.reapproval) {
    return (
      <WaitingApproval
        c={c}
        approvalId={c.reapproval.approval.approval_id}
        onChanged={onChanged}
        say={`Nhà cung cấp đã chọn có tổng ${money(c.reapproval.selection.total, c.reapproval.selection.currency)}, vượt hạn mức đã duyệt: chờ ${c.reapproval.approval.tier_label} duyệt lại.`}
        explanation={c.reapproval.explanation ?? null}
      />
    );
  } else if (c.status === "approved") {
    say = "Đã duyệt: soạn thư hỏi giá.";
    const chosen = Object.entries(named).flatMap(([line, codes]) =>
      codes.map((code) => ({ line_no: Number(line), supplier_code: code })),
    );
    body = (
      <Flex vertical gap={8} align="start" className="w-full">
        {button(
          "rfq",
          "Soạn thư hỏi giá",
          SCOPE.rfq,
          <FileTextOutlined aria-hidden />,
          (key) => api.draftRfq(c.case_id, c.case_version, key, chosen),
          "Đã soạn thư hỏi giá",
        )}
        {hasScope(SCOPE.rfq) ? (
          <NamedSuppliers
            c={c}
            named={named}
            onChange={setNamed}
            open={refused !== null}
          />
        ) : null}
      </Flex>
    );
  } else if (c.status === "rfq_drafted") {
    say = "Ghi báo giá nhận được, rồi chọn nhà cung cấp ở bảng so sánh.";
  } else if (c.status === "supplier_selected") {
    say = "Đã chọn nhà cung cấp: soạn PO.";
    body = button(
      "po",
      "Soạn PO",
      SCOPE.po,
      <FileTextOutlined aria-hidden />,
      (key) => api.draftOrders(c.case_id, c.case_version, key),
      "Đã soạn PO nháp",
    );
  } else if (c.status === "po_drafted") {
    say = "Tải file Bravo và nhập vào Bravo.";
    body = <BravoDownload c={c} />;
  } else if (c.status === "rejected") {
    say = `Yêu cầu đã bị từ chối${c.decision?.comment ? `: ${c.decision.comment}` : "."}`;
  }

  return (
    <Card size="small" title="Bước tiếp theo">
      <Flex vertical gap={12} align="start">
        <Typography.Text>{say}</Typography.Text>
        {body}
        {refused ? <Alert type="error" showIcon title={refused} /> : null}
      </Flex>
    </Card>
  );
}

function WaitingApproval({
  c,
  approvalId,
  say,
  explanation,
  onChanged,
}: {
  c: PurchaseCase;
  approvalId: string;
  say: string;
  explanation?: string | null;
  onChanged: () => void;
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
  return (
    <Card size="small" title="Bước tiếp theo">
      <Flex vertical gap={12}>
        <Typography.Text>{say}</Typography.Text>
        {explanation ? (
          <Flex vertical gap={4}>
            <MarkTag
              mark="machine_written"
              tip="DW2 viết lý do này; mọi con số trong đó là số của hệ thống."
            />
            <Typography.Paragraph className="mb-0">
              {explanation}
            </Typography.Paragraph>
          </Flex>
        ) : null}
        {approval.data && approval.data.status === "pending" ? (
          <DecideApproval
            approval={approval.data}
            subjectVersion={c.case_version}
            what={`yêu cầu ${c.request.pr_no}`}
            onDecided={onChanged}
          />
        ) : null}
      </Flex>
    </Card>
  );
}

// --------------------------------------------------------------- lines --

function RequestLines({ c }: { c: PurchaseCase }) {
  // Only a mail's lines are the model's reading as they stand: a requester
  // pressed "Gửi" on what they saw, a form was typed.
  const read = c.source === "mail";
  const file = c.read_from?.attachment;
  const scanned = c.read_from?.scanned === true;
  return (
    <Flex vertical gap={8}>
      {read ? (
        <Flex gap={8} align="center" wrap>
          <MarkTag
            mark="machine_read"
            tip={
              scanned
                ? "DW2 đọc các dòng này từ bản scan bằng máy đọc chữ (OCR), có thể đọc sai một chữ số. Mỗi giá trị có trong bản scan."
                : "DW2 đọc các dòng này từ thư; mỗi giá trị có trong thư gốc."
            }
          />
          {scanned ? <Tag>Bản scan</Tag> : null}
          {file ? <Typography.Text>Từ tệp {file}.</Typography.Text> : null}
          <Typography.Text>
            {c.review?.reviewed_at
              ? "Đã có người xem lại."
              : "Chưa có người xem lại."}
          </Typography.Text>
        </Flex>
      ) : null}
      <Descriptions
        size="small"
        column={{ xs: 1, md: 3 }}
        items={[
          {
            key: "budget",
            label: "Mã ngân sách",
            children: c.request.budget_code ?? "Không ghi",
          },
          {
            key: "need",
            label: "Ngày cần hàng",
            children: c.request.need_by
              ? formatDate(c.request.need_by)
              : "Theo từng dòng",
          },
          { key: "currency", label: "Loại tiền", children: c.request.currency },
        ]}
      />
      {c.request.note ? (
        <Typography.Paragraph className="mb-0">
          {c.request.note}
        </Typography.Paragraph>
      ) : null}
      <Table
        rowKey="line_no"
        size="small"
        pagination={false}
        scroll={{ x: "max-content" }}
        dataSource={c.request.lines}
        columns={[
          { title: "Dòng", dataIndex: "line_no" },
          {
            title: "Mã hàng",
            key: "item",
            render: (_, l) => l.item_code ?? "Chưa có mã",
          },
          { title: "Mô tả", dataIndex: "description" },
          {
            title: "Số lượng",
            key: "q",
            align: "right",
            render: (_, l) => `${formatQuantity(l.quantity)} ${l.unit}`,
          },
          {
            title: "Ngày cần",
            key: "n",
            render: (_, l) => (l.need_by ? formatDate(l.need_by) : "Không ghi"),
          },
          {
            title: "Giá ước tính",
            key: "e",
            align: "right",
            render: (_, l) =>
              l.estimated_unit_price
                ? money(l.estimated_unit_price, c.request.currency)
                : "Không ghi",
          },
        ]}
      />
    </Flex>
  );
}

// --------------------------------------------------------------- check --

/**
 * The cross-check the case was sent with, or for a case not yet sent the
 * check a send would stamp (computed now, stored nowhere). An amount DW2
 * cannot price is "Chưa rõ", never zero.
 */
function CheckCard({ c }: { c: PurchaseCase }) {
  const { hasScope } = useAuth();
  const preview = c.check === undefined || c.check === null;
  const canPreview = preview && c.status === "received" && hasScope(SCOPE.read);
  const live = useCachedResource(
    `purchasing/check/${c.case_id}/${c.case_version}:${canPreview}`,
    useCallback(
      () =>
        canPreview ? purchasingApi().check(c.case_id) : Promise.resolve(null),
      [c.case_id, canPreview],
    ),
  );
  const check: Check | null = c.check ?? live.data?.check ?? null;
  if (!check) {
    if (live.error)
      return <LoadError error={live.error} compact onRetry={live.reload} />;
    return null;
  }
  const tier = c.approval?.tier_label ?? live.data?.tier_label;
  return (
    <Card
      size="small"
      title={
        preview
          ? "Đối chiếu (nếu gửi bây giờ)"
          : `Đối chiếu ngày ${formatDate(check.checked_on)}`
      }
    >
      <Flex vertical gap={8}>
        <Flex gap={16} wrap>
          <Typography.Text>
            Tổng theo giá tham chiếu:{" "}
            {check.amount ? (
              <Typography.Text strong>
                {money(check.amount, check.currency)}
              </Typography.Text>
            ) : (
              <StatusTag
                tone="unk"
                icon={<ExclamationCircleOutlined aria-hidden />}
              >
                Chưa rõ: có dòng chưa có giá
              </StatusTag>
            )}
          </Typography.Text>
          {tier ? <Typography.Text>Người duyệt: {tier}</Typography.Text> : null}
        </Flex>
        {check.findings.length ? (
          <Alert
            type="warning"
            showIcon
            title={`${check.findings.length} điểm cần người duyệt biết`}
            description={
              <ul className="mb-0 ps-4">
                {check.findings.map((f, i) => (
                  <li key={`${f.code}:${f.line_no ?? 0}:${i}`}>
                    {f.line_no ? `Dòng ${f.line_no}: ` : ""}
                    {FINDING[f.code]}
                  </li>
                ))}
              </ul>
            }
          />
        ) : (
          <Typography.Text>
            Không có điểm cần lưu ý{" "}
            <InfoTip label="Đối chiếu đã kiểm những gì">
              DW2 kiểm mã hàng, giá tham chiếu, loại tiền, ngày cần và ngân
              sách.
            </InfoTip>
          </Typography.Text>
        )}
        <Table
          rowKey="line_no"
          size="small"
          pagination={false}
          scroll={{ x: "max-content" }}
          dataSource={check.lines}
          columns={[
            { title: "Dòng", dataIndex: "line_no" },
            {
              title: "Giá tham chiếu",
              key: "p",
              align: "right",
              render: (_, l) =>
                l.reference_price
                  ? money(l.reference_price, check.currency)
                  : "Chưa có",
            },
            {
              title: "Căn cứ",
              key: "b",
              render: (_, l) => (l.basis ? BASIS[l.basis] : "Không có"),
            },
            {
              title: "Nhà cung cấp",
              key: "s",
              render: (_, l) => l.supplier_code ?? "Không có",
            },
            {
              title: "Thành tiền",
              key: "a",
              align: "right",
              render: (_, l) =>
                l.amount ? money(l.amount, check.currency) : "Chưa rõ",
            },
          ]}
        />
      </Flex>
    </Card>
  );
}

// -------------------------------------------------------------- orders --

function OrdersCard({
  c,
  onChanged,
}: {
  c: PurchaseCase;
  onChanged: () => void;
}) {
  const po = c.po!;
  const mails = useConfirmationMails(c);
  return (
    <Card
      size="small"
      title={`PO nháp (${po.orders.length})`}
      extra={<BravoDownload c={c} />}
    >
      <Flex vertical gap={12}>
        <Typography.Text>
          Ngày đặt hàng: {formatDate(po.order_date)}
        </Typography.Text>
        {po.layout.mock ? (
          <Alert
            type="warning"
            showIcon
            title="File Bravo dùng mẫu dựng sẵn của nền tảng"
            description="Cột và tiêu đề chưa phải mẫu nhập Bravo của công ty: chỉ dùng để thử."
          />
        ) : null}
        {po.orders.map((order) => (
          <Flex key={order.po_ref} vertical gap={4}>
            <Typography.Text strong>
              {order.po_ref} · {order.supplier_name} ({order.supplier_code}) ·{" "}
              {money(order.total, order.currency)}
            </Typography.Text>
            <Table
              rowKey="line_no"
              size="small"
              pagination={false}
              scroll={{ x: "max-content" }}
              dataSource={order.lines}
              columns={[
                { title: "Dòng", dataIndex: "line_no" },
                { title: "Mô tả", dataIndex: "description" },
                {
                  title: "Số lượng",
                  key: "q",
                  align: "right",
                  render: (_, l) => `${formatQuantity(l.quantity)} ${l.unit}`,
                },
                {
                  title: "Đơn giá",
                  key: "u",
                  align: "right",
                  render: (_, l) => money(l.unit_price, order.currency),
                },
                {
                  title: "Thành tiền",
                  key: "a",
                  align: "right",
                  render: (_, l) => money(l.amount, order.currency),
                },
              ]}
            />
            <OrderFollowUp
              c={c}
              order={order}
              mails={mails.data ?? []}
              onChanged={() => {
                mails.reload();
                onChanged();
              }}
            />
          </Flex>
        ))}
      </Flex>
    </Card>
  );
}

function BravoDownload({ c }: { c: PurchaseCase }) {
  const { hasScope } = useAuth();
  const { message } = App.useApp();
  const [pending, setPending] = useState(false);
  const why = hasScope(SCOPE.download)
    ? null
    : "Bạn chưa được cấp quyền tải file Bravo (quản trị viên cấp được).";
  async function download() {
    setPending(true);
    try {
      const { blob, filename } = await purchasingApi().bravoFile(c.case_id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      message.error(errorMessage(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <Tooltip title={why}>
      <Button
        icon={<DownloadOutlined aria-hidden />}
        disabled={why !== null}
        loading={pending}
        onClick={() => void download()}
      >
        Tải file Bravo
      </Button>
    </Tooltip>
  );
}
