"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getTickers, type Ticker } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { AssetDetailView } from "@/components/asset-detail";
import { DataBadge } from "@/components/data-badge";
import { Delta, ErrorPanel, Skeleton } from "@/components/ui";

function LeftList({
  rows,
  active,
  onPick,
  query,
  setQuery,
}: {
  rows: Ticker[];
  active: string;
  onPick: (s: string) => void;
  query: string;
  setQuery: (q: string) => void;
}) {
  const { t } = useI18n();
  const filtered = useMemo(() => {
    const q = query.trim().toUpperCase();
    const seen = new Set<string>();
    return rows.filter((r) => {
      if (seen.has(r.symbol)) return false;
      seen.add(r.symbol);
      return !q || r.symbol.includes(q);
    });
  }, [rows, query]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-term-border p-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`${t("common.search")}…`}
          className="w-full rounded border border-term-border bg-term-bg px-2 py-1.5 text-xs text-zinc-200 outline-none focus:border-accent/50"
        />
      </div>
      <div className="flex-1 overflow-y-auto" style={{ maxHeight: "calc(100vh - 260px)" }}>
        {filtered.map((r) => (
          <button
            key={r.symbol}
            type="button"
            onClick={() => onPick(r.symbol)}
            className={`tbl-row flex w-full items-center justify-between px-3 py-1.5 text-start text-xs ${
              r.symbol === active ? "bg-accent/10 text-accent" : "text-zinc-300"
            }`}
          >
            <span className="font-medium">{r.symbol}</span>
            <span className="flex items-baseline gap-2">
              <span className="num">{fmtNum(r.price)}</span>
              <Delta value={r.change_24h_pct} digits={1} className="w-14 text-end" />
            </span>
          </button>
        ))}
        {filtered.length === 0 && (
          <p className="py-8 text-center text-xs text-term-dim">—</p>
        )}
      </div>
      <div className="border-t border-term-border px-3 py-1.5 text-[10px] text-term-dim">
        {filtered.length} / {rows.length}
      </div>
    </div>
  );
}

function MarketsInner() {
  const { t } = useI18n();
  const router = useRouter();
  const sp = useSearchParams();
  const initial = (sp.get("symbol") ?? "BTC").toUpperCase();
  const [symbol, setSymbol] = useState(initial);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<Ticker[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // 全量行情列表：静态一次拉取（TTL 缓存 60s），点击行切换右侧详情（URL 同步）
  useEffect(() => {
    let alive = true;
    getTickers()
      .then((r) => {
        if (!alive) return;
        const seen = new Set<string>();
        setRows(r.filter((x) => (seen.has(x.symbol) ? false : (seen.add(x.symbol), true))));
        setErr(null);
      })
      .catch((e) => alive && setErr(e instanceof Error ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);

  const pick = (s: string) => {
    setSymbol(s);
    router.replace(`/markets?symbol=${s}`, { scroll: false });
  };

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[280px_1fr]">
      <aside className="rounded-md border border-term-border bg-term-panel">
        <div className="border-b border-term-border flex items-center justify-between gap-2 px-3 py-2">
          <h2 className="text-sm font-semibold text-zinc-100">{t("markets.title")}</h2>
          <DataBadge />
        </div>
        {err && <ErrorPanel message={err} />}
        {!rows && !err && <Skeleton rows={10} />}
        {rows && (
          <LeftList rows={rows} active={symbol} onPick={pick} query={query} setQuery={setQuery} />
        )}
      </aside>
      <section className="min-w-0">
        <AssetDetailView symbol={symbol} />
      </section>
    </div>
  );
}

export default function MarketsPage() {
  return (
    <Suspense fallback={<Skeleton rows={10} />}>
      <MarketsInner />
    </Suspense>
  );
}
