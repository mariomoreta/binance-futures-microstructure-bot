import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import "@/styles/tokens.css";

export const metadata: Metadata = {
  title: "Binance Futures — Research Dashboard",
  description:
    "Market intelligence research workspace with labeled previews and recorded evidence.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
