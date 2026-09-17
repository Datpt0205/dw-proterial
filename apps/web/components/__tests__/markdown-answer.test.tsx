import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MarkdownAnswer } from "../markdown-answer";

/**
 * What an assistant answer is allowed to turn into.
 *
 * Written against the hand-rolled renderer and meant to be run UNCHANGED
 * against its replacement. That is the whole point of the file: swapping a
 * Markdown renderer silently changes what model output can do to the DOM,
 * and the only way to see it is to pin the behaviour first.
 *
 * Two of these are security claims, not formatting ones. The model writes
 * this text out of CRM notes and pasted email, which the prompt classifies
 * as untrusted, so "raw HTML stays characters" and "a javascript: href is
 * not a link" are load-bearing.
 */

describe("MarkdownAnswer", () => {
  it("renders raw HTML as characters, never as elements", () => {
    const { container } = render(
      <MarkdownAnswer
        text={`<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>`}
      />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    // The characters survive: a reader who was sent markup should see that
    // they were sent markup, rather than silently getting nothing.
    expect(container.textContent).toContain("<script>");
    expect(container.textContent).toContain("onerror");
  });

  it("does not build an anchor for a scheme it cannot vouch for", () => {
    const { container } = render(
      // eslint-disable-next-line no-script-url
      <MarkdownAnswer text={`[bấm vào đây](javascript:alert(1))`} />,
    );

    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("bấm vào đây");
  });

  it("links http and site-relative hrefs", () => {
    const { container } = render(
      <MarkdownAnswer text={`[FPT](https://fpt.com) và [audit](/audit)`} />,
    );

    const hrefs = [...container.querySelectorAll("a")].map((a) =>
      a.getAttribute("href"),
    );
    expect(hrefs).toEqual(["https://fpt.com", "/audit"]);
  });

  it("terminates on a table header whose delimiter row has not streamed yet", () => {
    // The shape that froze a tab and brought up Chrome's out-of-memory page
    // on 2026-08-19: mid-stream, the text holds a header row and nothing
    // after it, and the parser used to make no progress on that line.
    const { container } = render(
      <MarkdownAnswer text={`| Lead | Ngân sách |`} />,
    );

    expect(container.textContent).toContain("Ngân sách");
  });

  it("renders a GFM table with per-column alignment", () => {
    render(
      <MarkdownAnswer
        text={`| Lead | Giá trị |\n| :--- | ---: |\n| FPT | 1.000 |`}
      />,
    );

    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Giá trị" })).toBeTruthy();
    expect(screen.getByRole("cell", { name: "1.000" })).toBeTruthy();
  });

  it("keeps a fenced code block verbatim", () => {
    const { container } = render(
      <MarkdownAnswer text={"```\nSELECT **1** FROM t\n```"} />,
    );

    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    // The asterisks are content inside a fence, not emphasis.
    expect(pre?.textContent).toContain("**1**");
  });
});
