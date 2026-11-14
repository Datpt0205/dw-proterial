"use client";

import { Alert, Flex, Table, Tag, Typography } from "antd";
import { StatusTag } from "@dw/ui";
import {
  DIFFERENCE_PROBLEM,
  DIFFERENCE_SOURCE,
  EXAMPLE_PROBLEM,
  EXAMPLE_STATUS,
  leftForPerson,
  replaySummary,
  ruleWords,
  type CellDifference,
  type SalesOrderExample,
} from "../_lib/salesorder-examples";

/**
 * What a worked example came to (ticket 38): its status, why a proposal was
 * refused, and the replay of the customer's rules on the example's PO,
 * compared with the PIC's file cell by cell: every cell that came out
 * otherwise, with what was expected, what came out and what produced it.
 * Shown on the customer's screen and on the approval, so the head decides
 * on what was replayed, not on the rules alone. The rules are the model's
 * proposal: tagged so ("Máy đề xuất") until a person approves them.
 */
export function SalesOrderReplay({ example }: { example: SalesOrderExample }) {
  const replay = example.replay;
  const status = EXAMPLE_STATUS[example.status];
  return (
    <Flex vertical gap="small">
      <Flex wrap gap="small" align="center">
        <StatusTag
          tone={
            example.submittable || example.status === "submitted"
              ? "ok"
              : example.status === "queued"
                ? "gray"
                : "warn"
          }
        >
          {status}
        </StatusTag>
        {replay ? (
          <Typography.Text role="status">
            {replaySummary(replay)}
          </Typography.Text>
        ) : null}
        {example.rules ? <Tag>Máy đề xuất</Tag> : null}
      </Flex>
      {example.error ? (
        <Alert type="error" showIcon title={example.error} />
      ) : null}
      {example.problems.length ? (
        <Alert
          type="warning"
          showIcon
          title="Lý do"
          description={
            <ul className="m-0 ps-4">
              {example.problems.map((p, i) => (
                <li key={`${p.code}-${p.column ?? ""}-${i}`}>
                  {EXAMPLE_PROBLEM[p.code]}
                  {p.column ? ` (cột ${p.column})` : ""}
                </li>
              ))}
            </ul>
          }
        />
      ) : null}
      {example.rules ? (
        <ul className="m-0 ps-4" aria-label="Quy tắc từng cột">
          {example.rules.columns.map((rule) => (
            <li key={rule.column}>{ruleWords(rule)}</li>
          ))}
        </ul>
      ) : null}
      {replay && replay.differences.length ? (
        <Table<CellDifference>
          size="small"
          rowKey={(d) => `${d.cell}-${d.column ?? ""}-${d.problem}`}
          dataSource={replay.differences}
          pagination={false}
          scroll={{ x: "max-content" }}
          footer={() =>
            replay.differences_total > replay.differences.length
              ? `${replay.differences.length}/${replay.differences_total} ô khác đầu tiên`
              : `${replay.differences_total} ô khác`
          }
          columns={[
            { title: "Ô (tệp PIC)", dataIndex: "cell" },
            {
              title: "Cột",
              key: "header",
              render: (_, d) => d.header ?? "",
            },
            {
              title: "Tệp PIC",
              key: "expected",
              render: (_, d) => d.expected ?? "(trống)",
            },
            {
              title: "DW ra",
              key: "got",
              render: (_, d) => d.got ?? "(trống)",
            },
            {
              title: "Do",
              key: "source",
              render: (_, d) =>
                `${DIFFERENCE_SOURCE[d.source]}${d.step ? `, bước ${d.step}` : ""}: ${DIFFERENCE_PROBLEM[d.problem]}`,
            },
          ]}
        />
      ) : null}
      {replay && leftForPerson(replay).length ? (
        <Typography.Text>
          Để trống cho người dán (DW không điền):{" "}
          {leftForPerson(replay).join("; ")}
        </Typography.Text>
      ) : null}
    </Flex>
  );
}
