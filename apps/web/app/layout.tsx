import type { Metadata } from "next";
import { Be_Vietnam_Pro, JetBrains_Mono } from "next/font/google";
import type { ReactNode } from "react";
import { Toaster } from "sonner";
import { THEME_ROOT_CLASS } from "@dw/ui/theme-class";
import { AppFrame } from "../components/app-frame";
import { UiRoot } from "../components/ui-root";
import { AuthProvider } from "../lib/auth/auth-context";
import "./globals.css";

/**
 * The type the theme names (`FONT_VARIABLE` in @dw/ui): next/font downloads
 * them at build time and serves them from this app, so no page asks Google
 * for anything. The variable names are literals because next/font accepts
 * nothing else; `components/__tests__/theme.test.ts` compares them with the
 * theme's.
 */
const sans = Be_Vietnam_Pro({
  subsets: ["vietnamese", "latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-dw-sans",
});
const mono = JetBrains_Mono({
  subsets: ["vietnamese", "latin"],
  weight: ["400", "500"],
  display: "swap",
  variable: "--font-dw-mono",
});

export const metadata: Metadata = {
  title: "Digital Worker Platform",
  description: "Agent workspace: approvals, knowledge, memory and audit",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="vi"
      className={`${THEME_ROOT_CLASS} ${sans.variable} ${mono.variable}`}
    >
      <body className="min-h-screen bg-background antialiased">
        <UiRoot>
          <AuthProvider>
            <AppFrame>{children}</AppFrame>
          </AuthProvider>
        </UiRoot>
        <Toaster richColors position="bottom-right" />
      </body>
    </html>
  );
}
