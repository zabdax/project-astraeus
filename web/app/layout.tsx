import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

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
    <html lang="en">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            ASTRAEUS
          </Link>
          <nav aria-label="primary">
            {NAV.map((item) => (
              <Link key={item.href} href={item.href} className="navlink">
                {item.label}
              </Link>
            ))}
          </nav>
        </header>
        {children}
      </body>
    </html>
  );
}
