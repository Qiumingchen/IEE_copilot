import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppShell from "./AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "IEE-Copilot",
  description: "Industrial Enzyme Engineering Copilot"
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
