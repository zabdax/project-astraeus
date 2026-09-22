"use client";

import Link from "next/link";
import { Flask, FolderOpen, SlidersHorizontal, MagnifyingGlass } from "@phosphor-icons/react";

const NAV = [
  { href: "/investigate", label: "Investigate", icon: MagnifyingGlass },
  { href: "/analyses", label: "Analyses", icon: FolderOpen },
  { href: "/simulate", label: "Simulate", icon: Flask },
  { href: "/settings", label: "Settings", icon: SlidersHorizontal },
];

export default function Nav() {
  return (
    <nav aria-label="primary">
      {NAV.map((item) => (
        <Link key={item.href} href={item.href} className="navlink">
          <item.icon size={15} weight="duotone" aria-hidden style={{ verticalAlign: "-2px", marginRight: 6 }} />
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
