"use client";

import { Suspense } from "react";
import { ProjectOutlined } from "@ant-design/icons";
import { PageHeader } from "@dw/ui";
import { salesCrumbs } from "../_components/crumbs";
import { PipelineBoard } from "../_components/pipeline-board";
import { SCOPE } from "../_components/sales-frame";
import { ScopeGate } from "../_components/scope-gate";

/** Pipeline hồ sơ: every case by status, each person's own step lit. */
export default function PipelinePage() {
  return (
    <ScopeGate scope={SCOPE.caseRead}>
      <div className="space-y-3">
        <PageHeader
          breadcrumb={salesCrumbs("Pipeline hồ sơ")}
          icon={<ProjectOutlined />}
          title="Pipeline hồ sơ"
          help="Mỗi cột là một trạng thái, theo thứ tự hồ sơ đi qua; thẻ có viền xanh là việc đang đến lượt bạn. Giờ Việt Nam."
        />
        <Suspense>
          <PipelineBoard />
        </Suspense>
      </div>
    </ScopeGate>
  );
}
