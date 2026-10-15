// @vitest-environment node
import { describe, expect, it } from "vitest";
import { ApiError } from "@dw/api-client";
import { refusalSentences } from "../errors";

function notServed(missing: string[]): ApiError {
  return new ApiError(409, {
    code: "conflict",
    message: "chưa mở nguồn",
    details: { rule: "source_not_served", missing },
  });
}

/**
 * The 409 a quote's confirmation gets until the caller was served where the
 * value was read (ticket 29): the mail's text names no file, so it must not
 * read as a sheet.
 */
describe("refusalSentences for source_not_served", () => {
  it("names the mail's text as the mail, not as a sheet", () => {
    expect(refusalSentences(notServed(["message_text"]))).toEqual([
      "chưa mở nguồn",
      "Còn phải mở: nội dung thư.",
    ]);
  });

  it("names a file's page and sheet by their labels", () => {
    expect(
      refusalSentences(notServed(["M03-A1:page 2", "M05-A1:注文書"]))[1],
    ).toBe("Còn phải mở: trang 2, sheet 注文書.");
  });
});
