"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { API_ROOT } from "@/lib/api";
import { LANGS, useI18n, type Lang } from "@/lib/i18n";

const NAV = [
  { href: "/", key: "nav.markets" },
  { href: "/markets", key: "nav.tickers" },
  { href: "/macro", key: "nav.macro" },
  { href: "/trade", key: "nav.trade" },
  { href: "/agent", key: "nav.agent" },
  { href: "/watchlist", key: "nav.watchlist" },
  { href: "/settings", key: "nav.settings" },
];

export function Navbar() {
  const pathname = usePathname();
  const { t, lang, setLang } = useI18n();
  const [health, setHealth] = useState<"up" | "down" | "pending">("pending");
  const [menuOpen, setMenuOpen] = useState(false);
  const [langOpen, setLangOpen] = useState(false);
  const langRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let alive = true;
    const check = () =>
      fetch(`${API_ROOT}/health`)
        .then((r) => alive && setHealth(r.ok ? "up" : "down"))
        .catch(() => alive && setHealth("down"));
    check();
    const timer = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (langRef.current && !langRef.current.contains(e.target as Node)) setLangOpen(false);
    };
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  const dot = health === "up" ? "bg-up" : health === "down" ? "bg-down" : "bg-term-dim animate-pulse";

  const navList = (
    <nav className="flex flex-col gap-1 md:flex-row md:items-center md:gap-1">
      {NAV.map((item) => {
        const active =
          item.href === "/"
            ? pathname === "/"
            : pathname.startsWith(item.href.split("/").slice(0, 2).join("/"));
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMenuOpen(false)}
            className={`rounded px-3 py-1.5 text-sm font-medium ${
              active ? "text-accent" : "text-term-muted hover:text-zinc-100"
            }`}
          >
            {t(item.key)}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center gap-6 border-b border-term-border bg-term-bg px-4 md:px-6">
      <Link href="/" className="flex items-center">
        <span className="text-lg font-bold tracking-[0.18em] text-zinc-100">W3EX</span>
      </Link>
      <div className="hidden md:block">{navList}</div>
      <div className="ml-auto flex items-center gap-3">
        <div className="relative" ref={langRef}>
          <button
            type="button"
            onClick={() => setLangOpen((v) => !v)}
            className="rounded border border-term-border px-2 py-1 text-xs text-term-muted hover:text-zinc-100"
          >
            {LANGS.find((l) => l.code === lang)?.label ?? "中文"}
          </button>
          {langOpen && (
            <div className="absolute end-0 top-9 z-40 w-36 rounded-md border border-term-border bg-term-panel py-1 shadow-lg">
              {LANGS.map((l) => (
                <button
                  key={l.code}
                  type="button"
                  onClick={() => {
                    setLang(l.code as Lang);
                    setLangOpen(false);
                  }}
                  className={`block w-full px-3 py-1.5 text-start text-xs ${
                    l.code === lang ? "text-accent" : "text-zinc-300 hover:bg-term-panel2"
                  }`}
                >
                  {l.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <span className="rounded border border-accent/40 bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-accent">
          {t("common.paperMode")}
        </span>
        <div className="flex items-center gap-1.5 text-xs text-term-muted">
          <span className={`inline-block h-1.5 w-1.5 rounded-full ${dot}`} />
          <span className="hidden sm:inline">{health === "up" ? "API" : "Offline"}</span>
        </div>
        <button
          type="button"
          aria-label="menu"
          onClick={() => setMenuOpen((v) => !v)}
          className="flex flex-col gap-1 md:hidden"
        >
          <span className={`h-0.5 w-5 bg-zinc-300 transition ${menuOpen ? "translate-y-1.5 rotate-45" : ""}`} />
          <span className={`h-0.5 w-5 bg-zinc-300 transition ${menuOpen ? "opacity-0" : ""}`} />
          <span className={`h-0.5 w-5 bg-zinc-300 transition ${menuOpen ? "-translate-y-1.5 -rotate-45" : ""}`} />
        </button>
      </div>
      {menuOpen && (
        <div className="absolute inset-x-0 top-14 border-b border-term-border bg-term-bg p-3 shadow-lg md:hidden">
          <div className="flex flex-col">{navList}</div>
        </div>
      )}
    </header>
  );
}
