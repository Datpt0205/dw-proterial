"use client";

import Link from "next/link";
import { RegionState } from "@dw/ui";
import { LoadError } from "../../../components/load-error";
import { errorCode } from "../../../lib/error-message";

/** A case this person was looking at, read again after their own step. */
export const CASE_LEFT_VIEW =
  "Hồ sơ không còn chờ bạn nên không mở được ở đây nữa, thường vì bước của bạn vừa xong: người kiểm chéo và người duyệt chỉ mở hồ sơ khi hồ sơ đang chờ họ.";
/** A case id this person cannot open: never says whether it exists. */
export const CASE_NOT_FOUND =
  "Không có hồ sơ này, hoặc hồ sơ không thuộc phạm vi bạn được xem.";

/**
 * A case page that could not read its case. A case reads as not found both
 * when it does not exist and when it is outside what this person sees
 * (`visibility.sees_case`), and the server says so in English; the page
 * says it in words, with the way back to "Việc cần làm". `shown`: the page
 * had the case on screen before this read, so the person's own step (a
 * cross-check, an approval) is what took it out of their view. Any other
 * failure is drawn as everywhere else.
 */
export function CaseLoadError({
  error,
  onRetry,
  shown,
}: {
  error: unknown;
  onRetry: () => void;
  shown: boolean;
}) {
  if (errorCode(error) !== "not_found")
    return <LoadError error={error} onRetry={onRetry} />;
  return (
    <RegionState
      kind="notfound"
      title={shown ? "Hồ sơ đã rời khỏi việc của bạn" : undefined}
      description={shown ? CASE_LEFT_VIEW : CASE_NOT_FOUND}
      action={<Link href="/sales">Về Việc cần làm</Link>}
    />
  );
}
