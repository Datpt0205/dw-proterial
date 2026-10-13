"use client";

import { useRouter } from "next/navigation";
import { Alert, Button } from "antd";
import { formatDateTime } from "../lib/dates";
import { supportBanner } from "../lib/support/registry";
import {
  endSupportGrant,
  useSupportGrant,
  type OpenSupportGrant,
} from "../lib/support/session";

/**
 * The shell's support slot (support-access ticket 03): while a grant is open,
 * an always-on strip under the bar names it and its end, with the way out. A
 * context that ships its own banner (`SupportHost.Banner`) draws it instead;
 * the words of a context's banner are the context's.
 */
export function SupportBannerSlot() {
  const grant = useSupportGrant();
  const router = useRouter();
  if (!grant) return null;
  const exit = () => {
    endSupportGrant();
    router.push("/support");
  };
  const Banner = supportBanner(grant) ?? PlatformSupportBanner;
  return <Banner grant={grant} onExit={exit} />;
}

function PlatformSupportBanner({
  grant,
  onExit,
}: {
  grant: OpenSupportGrant;
  onExit: () => void;
}) {
  return (
    <Alert
      banner
      type="warning"
      role="status"
      title={`Bạn đang làm việc qua quyền hỗ trợ ${grant.code}, hết hạn ${formatDateTime(grant.expiresAt)}. Mọi thao tác được ghi nhật ký với mã quyền.`}
      action={
        <Button size="small" onClick={onExit}>
          Thoát quyền hỗ trợ
        </Button>
      }
    />
  );
}
