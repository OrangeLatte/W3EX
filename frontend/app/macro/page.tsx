"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useApi } from "@/lib/useApi";
import { api, getMacroIndicator, type MacroIndicatorSeries } from "@/lib/api";
import type { MacroOverview } from "@/lib/api";
import { fmtNum, fmtPct } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { Delta, ErrorPanel, Panel, Skeleton, Sparkline } from "@/components/ui";

const METRICS = ["gdp_growth", "inflation", "unemployment", "policy_rate"] as const;
const METRIC_KEYS: Record<string, string> = {
  gdp_growth: "macro.gdp",
  inflation: "macro.inflation",
  unemployment: "macro.unemployment",
  policy_rate: "macro.policyRate",
};

/** 行内月度走势 sparkline（懒加载，/macro/history 缓存由后端 TTL 承担） */
function TrendSpark({ symbol }: { symbol: string }) {
  const [vals, setVals] = useState<number[] | null>(null);
  useEffect(() => {
    let alive = true;
    api<{ candles: { c: number }[] }>(`/macro/history/${symbol}?rng=1mo&interval=1d`)
      .then((d) => {
        if (alive) setVals(d.candles.map((c) => c.c));
      })
      .catch(() => {
        if (alive) setVals([]);
      });
    return () => {
      alive = false;
    };
  }, [symbol]);
  if (!vals || vals.length < 2) return <span className="text-term-dim">—</span>;
  return <Sparkline values={vals} height={26} width={120} fill />;
}

function GroupTable({
  title,
  subtitle,
  rows,
}: {
  title: string;
  subtitle: string;
  rows: { symbol: string; name: string; price: number; change_pct: number }[];
}) {
  const { t } = useI18n();
  return (
    <Panel title={title} subtitle={subtitle} bodyClass="p-0">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-term-border text-[10px] uppercase tracking-wider text-term-dim">
            <th className="px-3 py-2 text-start font-medium">{t("markets.symbol")}</th>
            <th className="px-3 py-2 text-end font-medium">{t("markets.price")}</th>
            <th className="px-3 py-2 text-end font-medium">{t("markets.change")}</th>
            <th className="hidden px-3 py-2 text-end font-medium sm:table-cell">1M</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="tbl-row border-b border-term-border/50">
              <td className="px-3 py-1.5">
                <Link href={`/macro/${r.symbol}`} className="group flex items-baseline">
                  <span className="font-medium text-zinc-200 group-hover:text-accent">
                    {r.symbol}
                  </span>
                  <span className="ms-2 text-term-dim">{r.name}</span>
                </Link>
              </td>
              <td className="num px-3 py-1.5 text-end text-zinc-200">{fmtNum(r.price)}</td>
              <td className="px-3 py-1.5 text-end">
                <Delta value={r.change_pct} />
              </td>
              <td className="hidden w-[130px] px-3 py-1 sm:table-cell">
                <Link href={`/macro/${r.symbol}`}>
                  <TrendSpark symbol={r.symbol} />
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length === 0 && <p className="py-8 text-center text-xs text-term-dim">—</p>}
    </Panel>
  );
}

function IndicatorCell({
  iso3,
  metric,
  value,
}: {
  iso3: string;
  metric: string;
  value: number | undefined;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [series, setSeries] = useState<MacroIndicatorSeries | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    if (series || err) {
      setOpen(!open);
      if (!series && !err) return;
    }
    setOpen(true);
    if (!series && !err) {
      getMacroIndicator(iso3, metric)
        .then(setSeries)
        .catch((e: Error) => setErr(e.message));
    }
  };

  const vals = series?.series.map((s) => s.value) ?? [];
  return (
    <td className="px-3 py-1.5 text-end">
      <button
        type="button"
        onClick={load}
        className="num text-zinc-200 hover:text-accent"
        title={t("macro.viewHistory")}
      >
        {value ? fmtPct(value) : "—"}
      </button>
      {open && (
        <div className="mt-1 w-44 border border-term-border bg-term-panel2 p-1.5 text-start">
          {err && <p className="text-[10px] text-down">{err}</p>}
          {!err && !series && <p className="text-[10px] text-term-dim">{t("common.loading")}</p>}
          {series && vals.length > 2 && <Sparkline values={vals} height={48} fill />}
          {series && (
            <p className="mt-0.5 text-[10px] text-term-dim">
              {series.indicator_name} · {series.series[0]?.year}–{series.series.at(-1)?.year}
            </p>
          )}
        </div>
      )}
    </td>
  );
}

export default function MacroPage() {
  const { t } = useI18n();
  const { data, error, loading, reload } = useApi<MacroOverview>("/macro/overview");

  if (error && !data) return <ErrorPanel message={error.message} onRetry={reload} />;
  if (!data) return <Skeleton rows={10} />;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-zinc-100">{t("macro.title")}</h1>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <GroupTable
          title={t("macro.indices")}
          subtitle={`${t("common.source")}: ${data.sources.indices}`}
          rows={data.indices}
        />
        <GroupTable
          title={t("macro.commodities")}
          subtitle={`${t("common.source")}: ${data.sources.commodities}`}
          rows={data.commodities}
        />
      </div>
      <Panel
        title={t("macro.economies")}
        subtitle={data.macro ? `${t("common.source")}: ${data.sources.macro}` : "unavailable"}
        bodyClass="p-0"
      >
        {data.macro ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-xs">
              <thead>
                <tr className="border-b border-term-border text-[10px] uppercase tracking-wider text-term-dim">
                  <th className="px-3 py-2 text-start font-medium">{t("markets.symbol")}</th>
                  {METRICS.map((m) => (
                    <th key={m} className="px-3 py-2 text-end font-medium">
                      {t(METRIC_KEYS[m])}
                    </th>
                  ))}
                  <th className="px-3 py-2 text-end font-medium">{t("macro.year")}</th>
                </tr>
              </thead>
              <tbody>
                {data.macro.countries.map((c) => (
                  <tr key={c.iso3} className="tbl-row border-b border-term-border/50">
                    <td className="px-3 py-1.5">
                      <span className="font-medium text-zinc-200">{c.name}</span>
                      <span className="ms-2 text-term-dim">{c.iso3}</span>
                    </td>
                    {METRICS.map((m) => (
                      <IndicatorCell
                        key={`${c.iso3}-${m}`}
                        iso3={c.iso3}
                        metric={m}
                        value={c.metrics[m]?.value}
                      />
                    ))}
                    <td className="num px-3 py-1.5 text-end text-term-dim">
                      {c.metrics.gdp_growth?.year ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-8 text-center text-xs text-term-dim">WorldBank unavailable</p>
        )}
      </Panel>
    </div>
  );
}
