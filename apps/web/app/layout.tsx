import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Toaster } from "sonner";
import { THEME_ROOT_CLASS } from "@dw/ui/theme-class";
import { AppFrame } from "../components/app-frame";
import { UiRoot } from "../components/ui-root";
import { AuthProvider } from "../lib/auth/auth-context";
import "./globals.css";

export const metadata: Metadata = {
  title: "Digital Worker Platform",
  description: "Agent workspace: approvals, knowledge, memory and audit",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="vi" className={THEME_ROOT_CLASS}>
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
