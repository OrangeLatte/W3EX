"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getTickers, type Ticker } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const MAJORS = "BTC,ETH,SOL,BNB,XRP,DOGE,ADA,LINK,AVAX,TRX,DOT,LTC";

export function TickerStrip() {
  const { t } = useI18n();
  const [tickers, setTickers] = useState<Ticker[]>([]);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getTickers(MAJORS)
        .then((t) => alive && setTickers(t))
        .catch(() => undefined);
    load();
    const t = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return (
    <div className="fixed inset-x-0 top-14 z-20 flex h-10 items-center gap-6 overflow-x-auto border-b border-term-border bg-term-panel px-4 md:px-6 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {tickers.length === 0 && <span className="text-xs text-term-dim">{t("ticker.loading")}</span>}
      {tickers.map((t) => (
        <Link key={t.symbol} href={`/token/${t.symbol}`} className="flex shrink-0 items-center gap-2">
          <span className="text-xs font-medium text-term-muted">{t.symbol}</span>
          <span className="num text-xs text-zinc-200">{t.price?.toLocaleString("en-US", { maximumFractionDigits: 2 })}</span>
          <span className={`num text-xs ${t.change_24h_pct >= 0 ? "text-up" : "text-down"}`}>
            {t.change_24h_pct >= 0 ? "+" : ""}
            {t.change_24h_pct.toFixed(2)}%
          </span>
        </Link>
      ))}
    </div>
  );
}
