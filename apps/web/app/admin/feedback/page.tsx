"use client";

import { useCallback, useEffect, useState } from "react";
import { Loader2, MessageSquarePlus } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@dw/ui";
import type { FeedbackItem } from "@dw/api-client";
import { apiClient } from "../../../lib/session";
import { PageHeading } from "../../../components/page-heading";
import { EmptyState } from "../../../components/empty-state";
import { formatDateTime } from "../../../lib/dates";

/**
 * The feedback inbox (spec 003 US5), moved under Admin: what members sent,
 * newest first, each with its module, page, suggestion and screenshots. The
 * API gates it on the members-read scope; the nav item carries the same scope.
 */
export default function FeedbackInboxPage() {
  const [items, setItems] = useState<FeedbackItem[] | null>(null);

  const load = useCallback(() => {
    apiClient()
      .listFeedback()
      .then(setItems)
      .catch(() => setItems([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeading icon={MessageSquarePlus} title="Feedback inbox" />
      <Card className="mt-3">
        <CardHeader>
          <CardTitle>Phản hồi từ thành viên</CardTitle>
          <CardDescription>
            Mới nhất trước. Mỗi phản hồi ghi module, trang, mô tả, đề xuất và
            ảnh màn hình người gửi đính kèm.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {items === null ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Đang tải…
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={MessageSquarePlus}
              title="Chưa có phản hồi"
              description="Phản hồi thành viên gửi qua nút góc dưới trái sẽ hiện ở đây."
            />
          ) : (
            <ul className="space-y-3">
              {items.map((item) => (
                <li
                  key={item.id}
                  className="rounded-xl border bg-card px-4 py-3"
                >
                  <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">
                      {item.author_name}
                    </span>
                    <span>{formatDateTime(item.created_at)}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="rounded-full bg-muted px-2 py-0.5 font-semibold uppercase tracking-wide">
                      {item.module ?? item.category}
                    </span>
                    {item.page_path && (
                      <span className="truncate">{item.page_path}</span>
                    )}
                  </div>
                  <p className="mt-2 whitespace-pre-wrap text-sm">
                    {item.message}
                  </p>
                  {item.suggestion && (
                    <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">
                      <span className="font-medium text-foreground">
                        Đề xuất:
                      </span>{" "}
                      {item.suggestion}
                    </p>
                  )}
                  {item.attachments.length > 0 && (
                    <ul className="mt-3 flex flex-wrap gap-2">
                      {item.attachments.map((attachment) => (
                        <li key={attachment.id}>
                          <AttachmentImage
                            feedbackId={item.id}
                            attachmentId={attachment.id}
                          />
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * A screenshot, fetched with the session's token (the bytes sit behind the
 * inbox scope, so a plain <img src> could not carry the authorization).
 */
function AttachmentImage({
  feedbackId,
  attachmentId,
}: {
  feedbackId: string;
  attachmentId: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    let objectUrl: string | null = null;
    apiClient()
      .feedbackAttachment(feedbackId, attachmentId)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch(() => setUrl(null));
    return () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [feedbackId, attachmentId]);
  if (!url) {
    return <div className="size-24 animate-pulse rounded-lg border bg-muted" />;
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" title="Mở ảnh">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={url}
        alt="Ảnh đính kèm phản hồi"
        className="size-24 rounded-lg border object-cover"
      />
    </a>
  );
}
