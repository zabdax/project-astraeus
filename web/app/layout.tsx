import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ASTRAEUS — Investigate",
  description:
    "Minimal honest UI over the ASTRAEUS transit-search API (P2-B vertical slice).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
