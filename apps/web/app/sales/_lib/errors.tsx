"use client";

import { Alert } from "antd";
import { formatMonth } from "../../../lib/dates";
import { errorCode, errorMessage } from "../../../lib/error-message";
import { ApiError } from "@dw/api-client";
import { FINDING_CODE, label } from "./labels";

/** A list the details carry: an array, or the API's text form "['a', 'b']". */
function list(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string" && value.startsWith("["))
    return [...value.matchAll(/'([^']*)'|"([^"]*)"|(\d+)/g)].map(
      (m) => m[1] ?? m[2] ?? m[3]!,
    );
  return [];
}

/** "quotation_missing:2" → "Không có báo giá còn hiệu lực (dòng 2)". */
export function findingKeyLabel(key: string): string {
  const [code, line] = key.split(":");
  const words = label(FINDING_CODE, code);
  return line && line !== "-" ? `${words} (dòng ${line})` : words;
}

/** "M03-A1:page 2" → "trang 2", "M05-A1:注文書" → "sheet 注文書". */
function regionLabel(region: string): string {
  const where = region.slice(region.indexOf(":") + 1);
  const page = /^page (\d+)$/.exec(where);
  return page ? `trang ${page[1]}` : `sheet ${where}`;
}

/**
 * The sentences a refusal carries, in Vietnamese. The server's own sentence
 * comes first; where its details name what blocks the step (the findings
 * still open, the pages not opened, the lines not mapped), those are spelled
 * out by their labels so the person knows what to do next.
 */
export function refusalSentences(error: unknown): string[] {
  const sentences = [errorMessage(error)];
  if (!(error instanceof ApiError)) return sentences;
  const details = error.body.details ?? {};
  const open = list(details.open_findings);
  if (open.length)
    sentences.push(
      `Còn ${open.length} cờ chưa quyết định: ${open.map(findingKeyLabel).join("; ")}.`,
    );
  const asked = list(details.ask_customer);
  if (asked.length)
    sentences.push(
      `Có ${asked.length} cờ đang chờ khách sửa: gửi yêu cầu sửa cho khách trước (${asked.map(findingKeyLabel).join("; ")}).`,
    );
  const unmapped = list(details.lines_not_mapped);
  if (unmapped.length)
    sentences.push(`Dòng ${unmapped.join(", ")} chưa có mã PRV.`);
  const missing = list(details.missing);
  if (details.rule === "source_not_served" && missing.length)
    sentences.push(`Còn phải mở: ${missing.map(regionLabel).join(", ")}.`);
  if (typeof details.latest_month === "string")
    sentences.push(
      `Chọn tháng LME làm căn cứ cho giá (tháng mới nhất đã công bố: ${formatMonth(details.latest_month)}).`,
    );
  if (details.rule === "maker_checker")
    sentences.push(
      "Bạn đã làm một phần hồ sơ này nên không tự kiểm chéo được (tách nhiệm, WIV-03-012 bước 9).",
    );
  if (details.reason === "stale_artifact")
    sentences.push(
      "Tệp này được soạn ở phiên bản hồ sơ cũ: soạn lại từ phiên bản hiện tại rồi tải.",
    );
  const waiting = list(details.lines);
  if (waiting.length)
    sentences.push(`Dòng ${waiting.join(", ")} chưa có ngày PC đồng ý.`);
  return sentences;
}

/** A refused action, drawn beside the control that was pressed. */
export function ActionError({ error }: { error: unknown }) {
  if (!error) return null;
  const code = errorCode(error);
  const title =
    code === "permission_denied"
      ? "Bạn không có quyền làm bước này"
      : code === "conflict"
        ? "Chưa làm được bước này"
        : code === "validation_failed"
          ? "Thông tin chưa đủ"
          : error instanceof ApiError
            ? "Máy chủ từ chối"
            : "Mất kết nối tới máy chủ";
  return (
    <Alert
      type={code === "conflict" ? "warning" : "error"}
      showIcon
      title={title}
      description={
        <ul className="m-0 list-none p-0">
          {refusalSentences(error).map((sentence) => (
            <li key={sentence}>{sentence}</li>
          ))}
        </ul>
      }
    />
  );
}
