import type { Metadata, Viewport } from "next";
import PwaRegister from "@/components/PwaRegister";
import "./globals.css";

export const metadata: Metadata = {
  title: "Elevare Workforce OS",
  description: "Run your workforce, tasks, KPIs and approvals in one place.",
  applicationName: "Elevare Workforce OS",
  icons: { apple: "/icons/apple-touch-icon.png" },
  appleWebApp: { capable: true, title: "Workforce OS", statusBarStyle: "black-translucent" },
};

export const viewport: Viewport = {
  themeColor: "#0a0e1a",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
      style={{
        "--font-geist-sans":
          "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
        "--font-geist-mono":
          "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
      } as React.CSSProperties}
    >
      <body className="min-h-full flex flex-col" style={{ fontFamily: "var(--font-geist-sans)" }}>
        {children}
        <PwaRegister />
      </body>
    </html>
  );
}
