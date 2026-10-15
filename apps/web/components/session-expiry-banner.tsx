"use client";

import { useState } from "react";
import { Alert, Button } from "antd";
import { useAuth } from "../lib/auth/auth-context";
import { formatDuration, formatInstant } from "../lib/dates";
import { sessionPhase, useSessionEnded } from "../lib/session-expiry";
import { useNow } from "../lib/use-now";

/**
 * The shell's word on the sign-in (ui-quality §4, WCAG 2.2.1): a few minutes
 * before it ends, how long is left and a way to stay signed in; once it has
 * ended, that it has, with the way back. It never leaves the page by itself:
 * what was being typed stays on screen until the person presses "Đăng nhập
 * lại", having copied it if they need to.
 */
export function SessionExpiryBanner() {
  const { sessionExpiresAt, extendSession, reauthenticate } = useAuth();
  const ended = useSessionEnded();
  const now = useNow(15_000);
  const [extending, setExtending] = useState(false);
  // Set when the identity provider would not move the end any later (the
  // session's longest life is reached): only signing in again helps then.
  const [refused, setRefused] = useState(false);
  const expiresAt = sessionExpiresAt ?? null;
  const phase = sessionPhase(expiresAt, now, ended);

  if (phase === "fresh") return null;

  const signInAgain = (
    // Its own key: reusing the "Tiếp tục phiên" button's instance would carry
    // that button's spinner over.
    <Button key="sign-in" size="small" onClick={reauthenticate}>
      Đăng nhập lại
    </Button>
  );

  if (phase === "ended")
    return (
      <Alert
        banner
        type="error"
        showIcon
        title="Phiên đăng nhập đã hết. Những gì bạn đang nhập vẫn còn trên trang: chép lại nếu cần, rồi đăng nhập lại để tiếp tục."
        action={signInAgain}
      />
    );

  const stay = async () => {
    setExtending(true);
    try {
      setRefused(!(await extendSession()));
    } finally {
      setExtending(false);
    }
  };
  const left = `Phiên đăng nhập sẽ hết sau ${formatDuration(
    (expiresAt ?? now) - now,
  )}, lúc ${formatInstant(expiresAt ?? now)}.`;
  return (
    <Alert
      banner
      type="warning"
      showIcon
      // Polite: the time left is rewritten every minute, and an assertive
      // region would read it out again each time.
      role="status"
      title={
        refused
          ? `${left} Không gia hạn thêm được nữa: lưu việc đang làm, rồi đăng nhập lại.`
          : `${left} Những gì bạn đang nhập vẫn giữ nguyên.`
      }
      action={
        refused ? (
          signInAgain
        ) : (
          <Button
            size="small"
            type="primary"
            loading={extending}
            onClick={stay}
          >
            Tiếp tục phiên
          </Button>
        )
      }
    />
  );
}
