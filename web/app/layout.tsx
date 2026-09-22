import type { Metadata } from "next";
import Link from "next/link";
import { Space_Grotesk, IBM_Plex_Mono } from "next/font/google";
import Nav from "../components/Nav";
import "./globals.css";

const display = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-display",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "ASTRAEUS",
  description:
    "Exoplanet transit analysis: investigate candidates, review analyses, simulate, configure.",
};

const NAV = [
  { href: "/investigate", label: "Investigate" },
  { href: "/analyses", label: "Analyses" },
  { href: "/simulate", label: "Simulate" },
  { href: "/settings", label: "Settings" },
];

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${mono.variable}`}>
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            <span className="brand-mark" aria-hidden />
            ASTRAEUS
          </Link>
          <Nav />
        </header>
        {children}
      </body>
    </html>
  );
}
