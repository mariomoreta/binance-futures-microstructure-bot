import type { Metadata } from "next";
import type { ReactNode } from "react";
import { AppShell } from "@/components/shell/AppShell";
import "@/styles/tokens.css";

export const metadata: Metadata = {
  title: "Dashboard V2 — foundation",
  description:
    "Isolated Dashboard V2 foundation. Static shell; no API integration.",
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
