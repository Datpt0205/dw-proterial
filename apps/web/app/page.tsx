"use client";

import { Suspense } from "react";
import Link from "next/link";
import { Card, Flex, Typography } from "antd";
import { HomeOutlined } from "@ant-design/icons";
import { PageHeader, RegionState } from "@dw/ui";
import { useAuth } from "../lib/auth/auth-context";
import { NAV_ITEMS } from "../lib/nav/registry";
import { isNavItemVisible } from "../lib/nav/visibility";
import { PipelineBoard } from "./sales/_components/pipeline-board";

/**
 * The platform landing page.
 *
 * A bounded context owns its own home screen; this one only points at the
 * platform areas the signed-in person can actually reach, read from the same
 * nav registry and the same filter the navbar uses — so a page added to the
 * registry appears here too, and nothing here can offer a link the navbar
 * would hide.
 *
 * Someone who works Sales cases (`sales.case.read`) lands on their pipeline
 * instead (Đạt, 2026-10-20: a page of cards is not the process): the cases by
 * status, their own steps lit. The pages stay in the bar and its menus.
 */
export default function HomePage() {
  const auth = useAuth();
  const { displayName, active } = auth;

  const destinations = NAV_ITEMS.filter(
    (item) => item.href !== "/" && isNavItemVisible(item, auth),
  );
  const greeting = displayName ? `Xin chào, ${displayName}` : "Xin chào";

  if (active && auth.hasScope("sales.case.read"))
    return (
      <div className="space-y-3">
        <PageHeader
          icon={<HomeOutlined />}
          title={greeting}
          subtitle={`Pipeline hồ sơ của ${active.workspaceName}: mỗi cột là một trạng thái, thẻ viền xanh là việc đang đến lượt bạn. Giờ Việt Nam.`}
        />
        <Suspense>
          <PipelineBoard />
        </Suspense>
      </div>
    );

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        icon={<HomeOutlined />}
        title={greeting}
        subtitle={
          active
            ? `Bạn đang làm việc trong ${active.workspaceName}. Mọi lượt chạy, quyết định và thao tác ở đây đều thuộc workspace này.`
            : "Hãy chọn một workspace để bắt đầu."
        }
      />
      {destinations.length === 0 && (
        <RegionState
          kind="empty"
          title="Chưa có mục nào cho bạn"
          description="Vai của bạn chưa có quyền ở khu vực nào của workspace này. Hãy nhờ quản trị viên cấp quyền."
        />
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {destinations.map((item) => {
          const Icon = item.icon;
          return (
            <Link key={item.href} href={item.href} className="block">
              <Card hoverable size="small" className="h-full">
                <Flex vertical gap={6}>
                  <Typography.Text strong>
                    <Icon aria-hidden /> {item.label}
                  </Typography.Text>
                  <Typography.Text type="secondary">
                    {item.hint}
                  </Typography.Text>
                </Flex>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
