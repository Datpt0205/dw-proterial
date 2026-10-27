import { describe, expect, it } from "vitest";
import { messageRef } from "../messages";

describe("messageRef", () => {
  it("shows a stored mail by the first 8 digits of its file's hash", () => {
    expect(messageRef(`eml-4e77a96d${"0".repeat(56)}`)).toBe("eml-4e77a96d");
  });

  it("shows any other id as it is", () => {
    expect(messageRef("M01")).toBe("M01");
    expect(messageRef("eml-not-a-hash")).toBe("eml-not-a-hash");
  });
});
