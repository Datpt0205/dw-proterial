import type { MetadataRoute } from "next";
import { PAGE_BACKGROUND, PRIMARY_COLOR } from "@dw/ui/theme-class";

/**
 * Installs the portal as an app (Edge or Chrome: "Install this site as an
 * app"): its own window and taskbar icon, updated with the server. On
 * premises this stands in for a desktop build (infra/onprem/README.md); it
 * needs HTTPS, which Caddy gives the LAN host.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Digital Worker",
    short_name: "Digital Worker",
    description:
      "Không gian làm việc của worker: duyệt, tri thức, bộ nhớ và nhật ký kiểm toán",
    lang: "vi",
    start_url: "/",
    scope: "/",
    display: "standalone",
    background_color: PAGE_BACKGROUND,
    theme_color: PRIMARY_COLOR,
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
      {
        src: "/icons/icon-maskable-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "maskable",
      },
    ],
  };
}
