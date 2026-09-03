"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import type { MarketOverview, Ticker } from "@/lib/api";
import { api } from "@/lib/api";
import { fmtPct, fmtUsd, timeAgo } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { Delta, Empty, ErrorPanel, Panel, Skeleton, Sparkline, StatCell } from "@/components/ui";
import { RegimeBrief } from "@/components/regime-brief";
import { RegimeGauge } from "@/components/regime-gauge";
import { MarketHeatmap } from "@/components/heatmap";
import { useI18n } from "@/lib/i18n";

type Candle = { ts: string; o: number; h: number; l: number; c: number };

function MajorCard({
  symbol,
  change,
  rows,
}: {
  symbol: string;
  change: number;
  rows: Candle[];
}) {
  const { t } = useI18n();
  const up = change >= 0;
  const last = rows.length ? rows[rows.length - 1].c : 0;
  const hi = rows.length ? Math.max(...rows.map((r) => r.h)) : 0;
  const lo = rows.length ? Math.min(...rows.map((r) => r.l)) : 0;
  const pos = hi > lo ? Math.min(Math.max((last - lo) / (hi - lo), 0), 1) : 0.5;
  return (
    <div className="rounded border border-term-border bg-term-panel2 p-2.5 transition-colors hover:border-accent/40">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold tracking-wider text-zinc-200">{symbol}</span>
        <Delta value={change} />
      </div>
      <p className="num mt-1 text-sm font-semibold text-zinc-100">
        {last ? `$${last.toLocaleString("en-US", { maximumFractionDigits: 2 })}` : "—"}
      </p>
      <Sparkline values={rows.map((r) => r.c)} height={34} fill />
      <div className="mt-1.5">
        <div className="relative h-1 rounded-full bg-term-border">
          <div
            className={`absolute -top-[3px] h-2.5 w-[3px] rounded-full ${up ? "bg-up" : "bg-down"}`}
            style={{ left: `calc(${(pos * 100).toFixed(1)}% - 1.5px)` }}
          />
        </div>
        <div className="num mt-1 flex justify-between text-[9px] text-term-dim">
          <span>{lo ? lo.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—"}</span>
          <span>{t("home.range24h")}</span>
          <span>{hi ? hi.toLocaleString("en-US", { maximumFractionDigits: 0 }) : "—"}</span>
        </div>
      </div>
    </div>
  );
}

function useMajorCandles(symbols: string[]) {
  const [candles, setCandles] = useState<Record<string, Candle[]>>({});
  useEffect(() => {
    let alive = true;
    (async () => {
      const out: Record<string, Candle[]> = {};
      await Promise.all(
        symbols.map(async (s) => {
          try {
            out[s] = await api<Candle[]>(`/market/klines/${s}?interval=1h&limit=24`);
          } catch {
            /* 单标的失败不阻塞 */
          }
        }),
      );
      if (alive) setCandles(out);
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return candles;
}

function HeatmapPanel() {
  const { t } = useI18n();
  const { data } = useApi<Ticker[]>("/market/tickers", 60_000);
  return (
    <Panel title={t("home.heatmap")} bodyClass="">
      {data ? <MarketHeatmap tickers={data} /> : <div className="h-40 animate-pulse rounded bg-term-panel2" />}
    </Panel>
  );
}

function TickerTable({
  title,
  rows,
}: {
  title: string;
  rows: MarketOverview["gainers"];
}) {
  const { t } = useI18n();
  return (
    <Panel title={title} bodyClass="">
      {rows.length === 0 ? (
        <Empty text={t("home.noData")} />
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-term-border text-left text-[10px] uppercase tracking-wider text-term-dim">
              <th className="px-3 py-1.5">{t("common.symbol")}</th>
              <th className="px-3 py-1.5 text-right">{t("common.price")}</th>
              <th className="px-3 py-1.5 text-right">{t("common.change24h")}</th>
              <th className="px-3 py-1.5 text-right">{t("common.volume")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr
                key={t.symbol}
                className="border-b border-term-border/50 last:border-0 hover:bg-term-panel2"
              >
                <td className="px-3 py-1.5">
                  <Link href={`/token/${t.symbol}`} className="font-mono text-zinc-200 hover:text-accent">
                    {t.symbol}
                  </Link>
                </td>
                <td className="num px-3 py-1.5 text-right text-zinc-300">
                  {t.price === null ? "—" : `$${t.price < 1 ? t.price.toPrecision(4) : t.price.toLocaleString("en-US", { maximumFractionDigits: 2 })}`}
                </td>
                <td className="px-3 py-1.5 text-right">
                  <Delta value={t.change_24h_pct} />
                </td>
                <td className="num px-3 py-1.5 text-right text-term-muted">{fmtUsd(t.volume_24h_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

export default function MarketOverviewPage() {
  const { t } = useI18n();
  const { data, error, reload } = useApi<MarketOverview>("/market/overview");
  const majorCandles = useMajorCandles(["BTC", "ETH", "SOL"]);

  if (error && !data) return <ErrorPanel message={error.message} onRetry={reload} />;
  if (!data) return <Skeleton rows={8} />;

  const r = data.regime;
  const regimeTone =
    r.regime === "risk_on" ? "text-up" : r.regime === "risk_off" ? "text-down" : "text-accent";

  return (
    <div className="space-y-4">
      <RegimeBrief />
      {/* Regime row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title={t("home.regime")} subtitle={data.as_of ? timeAgo(data.as_of) : undefined} className="lg:col-span-2">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className={`text-xl font-semibold ${regimeTone}`}>{r.label}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {r.drivers.map((d) => (
                  <span key={d} className="rounded border border-term-border bg-term-panel2 px-1.5 py-0.5 text-[11px] text-term-muted">
                    {d}
                  </span>
                ))}
              </div>
            </div>
            <RegimeGauge score={r.score} />
          </div>
          <div className="mt-4 grid grid-cols-3 gap-2.5 border-t border-term-border pt-4">
            <MajorCard symbol="BTC" change={r.btc_change_24h_pct} rows={majorCandles.BTC ?? []} />
            <MajorCard symbol="ETH" change={r.eth_change_24h_pct} rows={majorCandles.ETH ?? []} />
            <MajorCard symbol="SOL" change={r.sol_change_24h_pct} rows={majorCandles.SOL ?? []} />
          </div>
        </Panel>
        <Panel title={t("home.stats")}>
          {data.global_stats && (
            <div className="grid grid-cols-2 gap-x-3 gap-y-3">
              <StatCell label={t("home.totalMcap")}>{fmtUsd(data.global_stats.total_market_cap_usd)}</StatCell>
              <StatCell label={t("home.volume24h")}>{fmtUsd(data.global_stats.total_volume_24h_usd)}</StatCell>
              <StatCell label={t("home.btcDom")}>
                {data.global_stats.btc_dominance_pct.toFixed(1)}%
              </StatCell>
              <StatCell label={t("home.ethDom")}>
                {data.global_stats.eth_dominance_pct.toFixed(1)}%
              </StatCell>
              <StatCell label={t("home.mcapChange")}>
                <Delta value={data.global_stats.mcap_change_24h_pct} />
              </StatCell>
              <StatCell label={t("home.coins")}>
                {data.global_stats.active_cryptocurrencies.toLocaleString("en-US")}
              </StatCell>
            </div>
          )}
        </Panel>
      </div>

      {/* Movers */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <TickerTable title={t("home.gainers")} rows={data.gainers} />
        <TickerTable title={t("home.losers")} rows={data.losers} />
        <TickerTable title={t("home.volumeLeaders")} rows={data.volume_leaders} />
      </div>

      {/* 市场热力图 */}
      <HeatmapPanel />

      {/* Funding + Liquidations */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title={t("home.funding")} subtitle={data.sources.market}>
          {data.funding.length === 0 ? (
            <Empty text={t("home.fundingNA")} />
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-term-border text-left text-[10px] uppercase tracking-wider text-term-dim">
                  <th className="px-3 py-1.5">{t("common.symbol")}</th>
                  <th className="px-3 py-1.5 text-right">{t("common.rate8h")}</th>
                  <th className="px-3 py-1.5 text-right">{t("common.markPrice")}</th>
                </tr>
              </thead>
              <tbody>
                {data.funding.map((f) => (
                  <tr key={f.symbol} className="tbl-row border-b border-term-border/50 last:border-0">
                    <td className="px-3 py-1.5 font-mono">
                      <Link href={`/token/${f.symbol}`} className="text-zinc-200 hover:text-accent">{f.symbol}</Link>
                    </td>
                    <td className="px-3 py-1.5 text-right">
                      <Delta value={f.rate * 100} suffix="%" digits={4} />
                    </td>
                    <td className="num px-3 py-1.5 text-right text-term-muted">${Number(f.mark_price).toLocaleString("en-US", { maximumFractionDigits: 2 })}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
        <Panel title={t("home.liquidations")} subtitle={data.sources.liquidations}>
          {data.liquidations.length === 0 ? (
            <Empty text={t("home.liqNA")} />
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-term-border text-left text-[10px] uppercase tracking-wider text-term-dim">
                  <th className="px-3 py-1.5">{t("common.symbol")}</th>
                  <th className="px-3 py-1.5">{t("common.side")}</th>
                  <th className="px-3 py-1.5 text-right">{t("common.amount")}</th>
                  <th className="px-3 py-1.5 text-right">{t("common.price")}</th>
                  <th className="px-3 py-1.5 text-right">{t("common.time")}</th>
                </tr>
              </thead>
              <tbody>
                {data.liquidations.map((l, i) => (
                  <tr key={`${l.symbol}-${i}`} className="tbl-row border-b border-term-border/50 last:border-0">
                    <td className="px-3 py-1.5 font-mono">
                      <Link href={`/token/${l.symbol}`} className="text-zinc-200 hover:text-accent">{l.symbol}</Link>
                    </td>
                    <td className="px-3 py-1.5">
                      <span className={l.side === "long" ? "text-down" : "text-up"}>{l.side}</span>
                    </td>
                    <td className="num px-3 py-1.5 text-right text-zinc-300">{fmtUsd(l.amount_usd)}</td>
                    <td className="num px-3 py-1.5 text-right text-term-muted">${Number(l.price).toLocaleString("en-US", { maximumFractionDigits: 2 })}</td>
                    <td className="px-3 py-1.5 text-right text-term-dim">{timeAgo(l.ts)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>
      </div>

      <p className="px-1 text-[10px] text-term-dim">
        {t("common.sources")}: market = {data.sources.market}, liquidations = {data.sources.liquidations} · {t("home.sourcesNote")}
      </p>
    </div>
  );
}
