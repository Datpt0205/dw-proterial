"use client";

import type { ReactNode } from "react";
import { Button, Result, Skeleton } from "antd";
import { ApiError } from "@dw/api-client";
import { errorCode, errorMessage } from "../lib/error-message";

/**
 * The one mapping from a failed call to the state a region draws
 * (ui-quality §4): forbidden is a 403 saying why and where to go, not found is
 * a 404, a change under the viewer is a conflict that offers a reload, a
 * network failure is offline, and anything else is the server's own sentence
 * with its request id and "Thử lại". A screen passes the error it got and
 * never writes this table again.
 */
export function RegionState({
  error,
  onRetry,
  forbidden,
}: {
  error: unknown;
  onRetry?: () => void;
  /** Where to send someone who may not open this: a link or a sentence. */
  forbidden?: ReactNode;
}) {
  const code = errorCode(error);
  const retry = onRetry ? (
    <Button type="primary" onClick={onRetry}>
      Thử lại
    </Button>
  ) : null;

  if (code === "permission_denied") return <Forbidden extra={forbidden} />;
  if (code === "entitlement_denied")
    return (
      <Result
        status="info"
        title="Gói dịch vụ của tổ chức chưa gồm mục này"
        subTitle={errorMessage(error)}
      />
    );
  if (code === "not_found")
    return (
      <Result
        status="404"
        title="Không tìm thấy"
        subTitle="Không có mục này trong không gian làm việc của bạn, hoặc liên kết đã cũ."
      />
    );
  if (code === "conflict")
    return (
      <Result
        status="warning"
        title="Hồ sơ vừa thay đổi"
        subTitle={errorMessage(error)}
        extra={
          onRetry ? (
            <Button type="primary" onClick={onRetry}>
              Tải lại
            </Button>
          ) : null
        }
      />
    );
  if (!(error instanceof ApiError))
    return (
      <Result
        status="warning"
        title="Mất kết nối tới máy chủ"
        subTitle="Dữ liệu đã tải vẫn xem được. Thao tác ghi mở lại khi có mạng."
        extra={retry}
      />
    );
  const requestId = error.body.request_id;
  return (
    <Result
      status="500"
      title="Không tải được dữ liệu"
      subTitle={
        <>
          {errorMessage(error)}
          {requestId ? (
            <>
              <br />
              Mã yêu cầu: <code>{requestId}</code>
            </>
          ) : null}
        </>
      }
      extra={retry}
    />
  );
}

/** The 403 state: what is refused, and where the person can go instead. */
export function Forbidden({ extra }: { extra?: ReactNode }) {
  return (
    <Result
      status="403"
      title="Bạn không có quyền mở mục này"
      subTitle="Quyền của bạn trong không gian làm việc này không gồm trang này. Máy chủ cũng từ chối nếu mở thẳng bằng liên kết."
      extra={extra}
    />
  );
}

/** A loading region shaped roughly like what will fill it. */
export function RegionLoading({ rows = 6 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Đang tải">
      <Skeleton active paragraph={{ rows }} />
    </div>
  );
}
