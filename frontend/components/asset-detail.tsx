"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import type { AssetDetail } from "@/lib/api";
import { fmtNum, fmtUsd } from "@/lib/format";
import { ageLabel, useApi } from "@/lib/useApi";
import { useI18n } from "@/lib/i18n";
import { Delta, ErrorPanel, Panel, Skeleton, StatCell } from "@/components/ui";
import { DataBadge } from "@/components/data-badge";
import { CandleChart } from "@/components/candle-chart";
import { DEFAULT_SELECTION, IndicatorPicker, type IndicatorSelection } from "@/components/indicator-picker";
import { AiChatPanel } from "@/components/ai-chat-panel";

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;

function DepthBars({ depth }: { depth: NonNullable<AssetDetail["depth"]> }) {
  const bids = depth.bids.slice(0, 8);
  const asks = depth.asks.slice(0, 8).reverse();
  const maxQty = Math.max(...bids.map(([, q]) => q), ...asks.map(([, q]) => q), 1e-9);
  const row = (p: number, q: number, side: "bid" | "ask") => (
    <div key={`${side}-${p}`} className="relative flex justify-between px-2 py-0.5 text-[11px]">
      <div
        className={`absolute inset-y-0 ${side === "bid" ? "left-0 bg-up/15" : "right-0 bg-down/15"}`}
        style={{ width: `${(q / maxQty) * 100}%` }}
      />
      <span className={`num relative ${side === "bid" ? "text-up" : "text-down"}`}>
        ${p.toLocaleString("en-US", { maximumFractionDigits: 2 })}
      </span>
      <span className="num relative text-term-muted">{fmtNum(q)}</span>
    </div>
  );
  return (
    <div className="grid grid-cols-2 gap-2">
      <div>{asks.map(([p, q]) => row(p, q, "ask"))}</div>
      <div>{bids.map(([p, q]) => row(p, q, "bid"))}</div>
    </div>
  );
}

export function AssetDetailView({ symbol }: { symbol: string }) {
  const { t } = useI18n();
  const [interval, setInterval] = useState<string>("1h");
  const [selection, setSelection] = useState<IndicatorSelection>(DEFAULT_SELECTION);
  const { data, error, loading, stale, fetchedAt, reload } = useApi<AssetDetail>(
    `/assets/${symbol}?interval=${interval}`,
  );
  // P0/P1：切周期或刷新时保留旧图，界面永不空白
  const lastData = useRef<AssetDetail | null>(null);
  if (data) lastData.current = data;
  const view = data ?? lastData.current;
  const refreshing = loading && !!view;

  const hi = view ? Number(view.stats.high_24h) : null;
  const lo = view ? Number(view.stats.low_24h) : null;
  const amplitude = view && hi && lo && lo > 0 && Number.isFinite(hi) && Number.isFinite(lo)
    ? ((hi - lo) / lo) * 100
    : null;

  if (error && !view) return <ErrorPanel message={error.message} onRetry={reload} />;
  if (!view)
    return (
      <div className="space-y-4">
        <Panel bodyClass="p-4">
          <h1 className="text-2xl font-bold text-zinc-100">{symbol}</h1>
          <Skeleton rows={4} />
        </Panel>
        <Skeleton rows={8} />
      </div>
    );

  return (
    <div className="space-y-4">
      <Panel bodyClass="p-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-3">
              <h1 className="text-2xl font-bold text-zinc-100">{view.symbol}</h1>
              <span className="text-sm text-term-muted">{view.name}</span>
              <DataBadge />
            </div>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="num text-3xl font-semibold text-zinc-100">
                {view.price === null
                  ? "—"
                  : `$${view.price.toLocaleString("en-US", { maximumFractionDigits: view.price < 1 ? 6 : 2 })}`}
              </span>
              <Delta value={view.change_24h_pct} className="text-base" />
              {view.change_1h_pct !== null && (
                <span className="text-xs text-term-dim">
                  1h <Delta value={view.change_1h_pct} />
                </span>
              )}
            </div>
          </div>
          <Link
            href={`/trade?asset=${view.symbol}`}
            className="rounded border border-accent/40 bg-accent/10 px-4 py-2 text-sm font-medium text-accent hover:bg-accent/20"
          >
            Trade {view.symbol} →
          </Link>
        </div>
        <div className="mt-4 grid grid-cols-3 gap-3 border-t border-term-border pt-3 md:grid-cols-6">
          <StatCell label={t("asset.mcap")}>{fmtUsd(view.stats.market_cap)}</StatCell>
          <StatCell label={t("asset.rank")}>
            {view.stats.market_cap_rank !== null ? `#${view.stats.market_cap_rank}` : "—"}
          </StatCell>
          <StatCell label={t("asset.volume")}>{fmtUsd(view.stats.volume_24h_usd)}</StatCell>
          <StatCell label={t("asset.amplitude")}>
            {amplitude === null ? "—" : `${amplitude.toFixed(2)}%`}
          </StatCell>
          <StatCell label={t("asset.high")}>{fmtUsd(view.stats.high_24h)}</StatCell>
          <StatCell label={t("asset.low")}>{fmtUsd(view.stats.low_24h)}</StatCell>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel
          title={`${view.symbol} · ${t("markets.detail")}`}
          subtitle={`${view.candles.length} candles · ${interval === "1m" ? t("asset.minute") : interval}`}
          className="xl:col-span-2"
          right={
            <div className="flex items-center gap-2">
              {refreshing && <span className="text-[10px] text-term-dim">{t("common.refreshing")}</span>}
              {stale && !refreshing && (
                <span className="text-[10px] text-ai">{t("common.cachedAgo").replace("{n}", ageLabel(fetchedAt))}</span>
              )}
              {!stale && !refreshing && fetchedAt && (
                <span className="text-[10px] text-term-dim">{ageLabel(fetchedAt)}</span>
              )}
              <div className="flex gap-1">
                {INTERVALS.map((iv) => (
                  <button
                    key={iv}
                    onClick={() => setInterval(iv)}
                    className={`rounded px-2 py-0.5 text-[11px] ${
                      interval === iv ? "bg-accent/15 text-accent" : "text-term-muted hover:bg-term-panel2"
                    }`}
                  >
                    {iv === "1m" ? t("asset.minute") : iv}
                  </button>
                ))}
              </div>
            </div>
          }
        >
          <div className="mb-2">
            <IndicatorPicker value={selection} onChange={setSelection} />
          </div>
          {view.candles.length > 2 ? (
            <CandleChart candles={view.candles} selection={selection} />
          ) : (
            <p className="py-10 text-center text-xs text-term-dim">{t("asset.chartNA")}</p>
          )}
          <p className="mt-2 text-[10px] text-term-dim">
            {t("common.source")}: {view.sources.market} · {view.sources.meta}
          </p>
        </Panel>

        <div className="space-y-4">
          <Panel title={t("asset.orderbook")} subtitle={view.depth ? view.depth.source : "unavailable"}>
            {view.depth ? (
              <DepthBars depth={view.depth} />
            ) : (
              <p className="py-6 text-center text-xs text-term-dim">{t("asset.depthNone")}</p>
            )}
            {view.funding_rate !== null && (
              <div className="mt-3 border-t border-term-border pt-2 text-xs">
                <span className="text-term-dim">{t("asset.funding")} (8h): </span>
                <Delta value={view.funding_rate * 100} suffix="%" digits={4} />
              </div>
            )}
          </Panel>
          <Panel title={`${t("asset.aiChat")} · ${view.symbol}`} bodyClass="p-3 flex-1">
            <AiChatPanel symbol={view.symbol} interval={interval} />
          </Panel>
        </div>
      </div>
    </div>
  );
}
