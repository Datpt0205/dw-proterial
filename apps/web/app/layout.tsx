import type { Metadata } from "next";
import { Be_Vietnam_Pro } from "next/font/google";
import type { ReactNode } from "react";
import { AntdRegistry } from "@ant-design/nextjs-registry";
import { THEME_CSS_VAR_CLASS, ThemeProvider } from "@dw/ui";
import { AppFrame } from "../components/app-frame";
import { AuthProvider } from "../lib/auth/auth-context";
import "./globals.css";

export const metadata: Metadata = {
  title: "Digital Worker Platform",
  description: "Agent workspace: approvals, knowledge, memory and audit",
};

// Not a variable font on Google Fonts, so each weight in use is listed: antd's
// normal and strong (400, 600) and the app's medium and bold (500, 700).
const beVietnamPro = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    // The theme's variable class on <html>: see THEME_CSS_VAR_CLASS.
    <html lang="en" className={THEME_CSS_VAR_CLASS}>
      <body className="min-h-screen bg-background text-foreground antialiased">
        {/* `layer` puts antd's styles in `@layer antd`, which globals.css
            orders between Tailwind's base and its utilities. */}
        <AntdRegistry layer>
          <ThemeProvider fontFamily={beVietnamPro.style.fontFamily}>
            <AuthProvider>
              <AppFrame>{children}</AppFrame>
            </AuthProvider>
          </ThemeProvider>
        </AntdRegistry>
      </body>
    </html>
  );
}
