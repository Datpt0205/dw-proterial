"use client";

import { Collapse, Typography } from "antd";
import { SUBFLOW, SUBFLOW_STEP } from "../_lib/labels";
import type { Lane } from "../_lib/process-graph";
import { baCodes, BaSteps } from "./process-map";

type Subflow = Lane["subflows"][number];

/** A flow step's words; a step the API adds shows as its code. */
function stepWords(flow: string, step: string): string {
  return (SUBFLOW_STEP as Record<string, string>)[`${flow}.${step}`] ?? step;
}

/**
 * The flows beside a lane's statuses (ticket 35): the talk before the PO, the
 * wait on PC, a change asked by mail and the update loop. Each is a panel
 * that opens on click (Đạt, 2026-11-01: detail on click), its steps in order,
 * each with the BA's steps, the statuses a case is in meanwhile, and where it
 * goes next. Everything drawn is the server's (`process_settings.SUBFLOWS`,
 * read from the domain), so a step or a move added there is drawn here
 * without a change.
 */
export function ProcessSubflows({
  subflows,
  statusLabel,
}: {
  subflows: Subflow[];
  statusLabel: (status: string) => string;
}) {
  if (!subflows.length) return null;
  return (
    <section className="space-y-2">
      <Typography.Title level={5} className="mb-0!">
        Luồng bên cạnh các trạng thái
      </Typography.Title>
      <Collapse
        items={subflows.map((flow) => {
          const codes = baCodes(flow.steps.flatMap((s) => s.ba_steps));
          return {
            key: flow.key,
            label: (
              <span className="flex flex-wrap gap-x-2">
                <span>{SUBFLOW[flow.key] ?? flow.key}</span>
                {codes ? <span>BA {codes}</span> : null}
              </span>
            ),
            children: (
              <ol className="m-0 flex flex-col gap-3 ps-5">
                {flow.steps.map((step) => (
                  <li
                    key={step.step}
                    data-subflow-step={`${flow.key}.${step.step}`}
                  >
                    <span className="flex flex-col items-start gap-1">
                      <Typography.Text strong>
                        {stepWords(flow.key, step.step)}
                      </Typography.Text>
                      <BaSteps steps={step.ba_steps} />
                      <span>
                        {step.statuses.length
                          ? `Hồ sơ đang ở: ${step.statuses.map(statusLabel).join(", ")}`
                          : "Trước khi có hồ sơ"}
                      </span>
                      {step.next.length ? (
                        <span>
                          Tiếp theo:{" "}
                          {step.next
                            .map((next) => stepWords(flow.key, next))
                            .join(", ")}
                        </span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ol>
            ),
          };
        })}
      />
    </section>
  );
}
