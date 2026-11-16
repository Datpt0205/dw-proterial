"use client";

import { Alert, Flex, Tag, Typography } from "antd";
import { InfoTip, StatusTag } from "@dw/ui";
import {
  SKILL_LAYER,
  incompleteLine,
  replayLine,
  securityLine,
  triggerLine,
  wordsChanges,
  type Skill,
  type SkillVersion,
  type WordsLine,
} from "../_lib/skills";

/**
 * What the worker's replay of a version found, or that it has not run yet
 * (ticket 40): on `/sales/rules/skills` and under a `sales.skills` approval
 * on `/approvals`.
 */
export function SkillReplayResult({ version }: { version: SkillVersion }) {
  const replay = version.replay ?? null;
  if (!replay) {
    if (version.status !== "proposed") return null;
    return (
      <span className="flex flex-col items-start gap-1">
        <Tag color="processing">Đang chạy thử trên thư mẫu</Tag>
        <Typography.Text>
          Trưởng bộ phận chỉ duyệt được khi có kết quả.
        </Typography.Text>
      </span>
    );
  }
  const security = securityLine(replay);
  const incomplete = incompleteLine(replay);
  const taught = triggerLine(replay);
  return (
    <span className="flex flex-col items-start gap-1">
      <span className="inline-flex items-center gap-1">
        <Typography.Text>{replayLine(replay)}</Typography.Text>
        <InfoTip label="Thư mẫu nào?">
          Chạy trên thư mẫu của nền tảng (chưa có thư công ty đã kiểm): mỗi thư
          được đọc một lần với bản đề xuất và một lần với bản đang dùng.
        </InfoTip>
      </span>
      {taught ? <Typography.Text>{taught}</Typography.Text> : null}
      {incomplete ? <Alert type="warning" showIcon title={incomplete} /> : null}
      {security ? <Alert type="error" showIcon title={security} /> : null}
    </span>
  );
}

/**
 * A proposed skill version beside the version in force (ticket 40): its
 * replay, then the words it changes, line by line. A skill is words only, so
 * its description and instructions are the whole change. Drawn under the
 * approval on `/approvals`, where the head decides it.
 */
export function SkillChanges({
  skill,
  version,
}: {
  skill: Skill;
  version: SkillVersion;
}) {
  const description = wordsChanges(skill.description, version.description);
  const instructions = wordsChanges(skill.instructions, version.instructions);
  return (
    <Flex vertical gap="small">
      <SkillReplayResult version={version} />
      <Typography.Text>
        So với bản đang dùng <Typography.Text code>{skill.ref}</Typography.Text>{" "}
        ({SKILL_LAYER[skill.layer].toLowerCase()}):
      </Typography.Text>
      <Words title="Dùng khi nào" lines={description} />
      <Words title="Lời hướng dẫn" lines={instructions} />
    </Flex>
  );
}

const MARK: Record<"add" | "remove", { tag: string; tone: "ok" | "err" }> = {
  add: { tag: "Thêm", tone: "ok" },
  remove: { tag: "Bỏ", tone: "err" },
};

/** One part of the words: its changed lines, each with a word on a tag. */
function Words({
  title,
  lines,
}: {
  title: string;
  lines: readonly WordsLine[];
}) {
  const added = lines.filter((l) => l.op === "add").length;
  const removed = lines.filter((l) => l.op === "remove").length;
  return (
    <Flex vertical gap={2} aria-label={title}>
      <Typography.Text strong>
        {title}:{" "}
        {lines.length === 0
          ? "giữ nguyên"
          : `thêm ${added} dòng, bỏ ${removed} dòng`}
      </Typography.Text>
      {lines.map((line, i) =>
        line.op === "skip" ? (
          <Typography.Text key={i}>
            … {line.count} dòng giữ nguyên
          </Typography.Text>
        ) : (
          <span key={i} className="flex items-start gap-2">
            {line.op === "keep" ? (
              <span className="w-12 shrink-0" />
            ) : (
              <span className="w-12 shrink-0">
                <StatusTag tone={MARK[line.op].tone}>
                  {MARK[line.op].tag}
                </StatusTag>
              </span>
            )}
            <Typography.Text
              delete={line.op === "remove"}
              className="whitespace-pre-wrap break-words"
            >
              {line.text || " "}
            </Typography.Text>
          </span>
        ),
      )}
    </Flex>
  );
}
