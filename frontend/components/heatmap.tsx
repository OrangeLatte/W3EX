"use client";

import Link from "next/link";

import type { Ticker } from "@/lib/api";
import { fmtUsd } from "@/lib/format";

function heatColor(chg: number): { bg: string; text: string } {
  // -6% .. +6% 映射到红/绿强度
  const t = Math.max(-1, Math.min(1, chg / 6));
  const a = 0.14 + Math.abs(t) * 0.55;
  if (t >= 0) return { bg: `rgba(34, 229, 161, ${a.toFixed(2)})`, text: "#baf5df" };
  return { bg: `rgba(255, 77, 103, ${a.toFixed(2)})`, text: "#ffd4da" };
}

/** 市场热力图：按成交量取头部标的，色块=24h 涨跌强度，点击跳详情 */
export function MarketHeatmap({ tickers, limit = 42 }: { tickers: Ticker[]; limit?: number }) {
  const rows = [...tickers]
    .filter((t) => t.price !== null)
    .sort((a, b) => Number(b.volume_24h_usd ?? 0) - Number(a.volume_24h_usd ?? 0))
    .slice(0, limit);
  if (rows.length === 0) return null;
  return (
    <div className="grid grid-cols-4 gap-1.5 sm:grid-cols-6 lg:grid-cols-7">
      {rows.map((t) => {
        const { bg, text } = heatColor(t.change_24h_pct);
        const hot = Math.abs(t.change_24h_pct) >= 5;
        return (
          <Link
            key={t.symbol}
            href={`/token/${t.symbol}`}
            title={`${t.symbol}  ${t.change_24h_pct >= 0 ? "+" : ""}${t.change_24h_pct.toFixed(2)}%  Vol ${fmtUsd(t.volume_24h_usd)}`}
            className={`group rounded border px-1.5 py-2 text-center transition-transform hover:z-10 hover:scale-[1.06] ${
              hot ? "border-term-muted" : "border-transparent"
            } hover:border-accent`}
            style={{ backgroundColor: bg }}
          >
            <div className="truncate text-[11px] font-semibold" style={{ color: text }}>
              {t.symbol}
            </div>
            <div className="num text-[10px]" style={{ color: text }}>
              {t.change_24h_pct >= 0 ? "+" : ""}
              {t.change_24h_pct.toFixed(2)}%
            </div>
          </Link>
        );
      })}
    </div>
  );
}
