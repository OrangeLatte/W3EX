"use client";

import { useEffect, useMemo, useState } from "react";
import { getWatchlist, getTickers, putWatchlist, type Ticker } from "@/lib/api";
import { fmtUsd } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { Delta, ErrorPanel, Panel, Skeleton } from "@/components/ui";

export default function WatchlistPage() {
  const { t } = useI18n();
  const [symbols, setSymbols] = useState<string[] | null>(null);
  const [tickers, setTickers] = useState<Ticker[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [input, setInput] = useState("");

  useEffect(() => {
    Promise.all([getWatchlist(), getTickers()])
      .then(([wl, tk]) => {
        setSymbols(wl);
        setTickers(tk);
      })
      .catch((e) => setError(e.message));
  }, []);

  const bySymbol = useMemo(() => new Map(tickers.map((t) => [t.symbol, t])), [tickers]);
  const [toast, setToast] = useState<{ kind: "ok" | "warn"; text: string } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  async function add(symbol: string) {
    const s = symbol.trim().toUpperCase();
    if (!s) return;
    if (!/^[A-Z0-9]{1,10}$/.test(s)) {
      setToast({ kind: "warn", text: t("watchlist.invalidMsg").replace("{s}", s) });
      return;
    }
    if (!symbols) return;
    if (symbols.includes(s)) {
      setToast({ kind: "warn", text: t("watchlist.dupMsg").replace("{s}", s) });
      return;
    }
    if (tickers.length > 0 && !bySymbol.has(s)) {
      setToast({ kind: "warn", text: t("watchlist.notFoundMsg").replace("{s}", s) });
      return;
    }
    const next = [...symbols, s];
    setSymbols(next);
    try {
      const saved = await putWatchlist(next);
      setSymbols(saved);
      setToast({ kind: "ok", text: t("watchlist.addedMsg").replace("{s}", s) });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(symbol: string) {
    if (!symbols) return;
    const next = symbols.filter((s) => s !== symbol);
    setSymbols(next);
    try {
      const saved = await putWatchlist(next);
      setSymbols(saved);
      setToast({ kind: "ok", text: t("watchlist.removedMsg").replace("{s}", symbol) });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (error && !symbols) return <ErrorPanel message={error} />;
  if (!symbols) return <Skeleton rows={5} />;

  return (
    <Panel
      title={t("watchlist.title")}
      subtitle={t("watchlist.count").replace("{n}", String(symbols.length))}
      right={
        <form
          onSubmit={(e) => {
            e.preventDefault();
            add(input);
            setInput("");
          }}
          className="flex gap-1.5"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("watchlist.placeholder")}
            className="w-44 rounded border border-term-border bg-term-panel2 px-2 py-1 text-xs text-zinc-200 outline-none placeholder:text-term-dim focus:border-accent/50"
          />
          <button
            type="submit"
            disabled={
              !/^[A-Z0-9]{1,10}$/.test(input.trim().toUpperCase()) ||
              (!!symbols && symbols.includes(input.trim().toUpperCase()))
            }
            title={
              !input.trim()
                ? t("watchlist.placeholder")
                : symbols?.includes(input.trim().toUpperCase())
                  ? t("watchlist.duplicate")
                  : undefined
            }
            className="rounded border border-accent/40 bg-accent/10 px-2.5 py-1 text-xs text-accent hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {t("watchlist.add")}
          </button>
        </form>
      }
      bodyClass=""
    >
      {symbols.length === 0 ? (
        <p className="py-6 text-center text-xs text-term-dim">{t("watchlist.empty")}</p>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-term-border text-left text-[10px] uppercase tracking-wider text-term-dim">
              <th className="px-3 py-1.5">{t("markets.symbol")}</th>
              <th className="px-3 py-1.5 text-right">{t("markets.price")}</th>
              <th className="px-3 py-1.5 text-right">{t("markets.change")}</th>
              <th className="px-3 py-1.5 text-right">{t("markets.volume")}</th>
              <th className="px-3 py-1.5">{t("order.colAction")}</th>
            </tr>
          </thead>
          <tbody>
            {symbols.map((s) => {
              const tick = bySymbol.get(s);
              return (
                <tr key={s} className="border-b border-term-border/50 last:border-0 hover:bg-term-panel2">
                  <td className="px-3 py-1.5">
                    <a href={`/token/${s}`} className="font-mono font-medium text-zinc-200 hover:text-accent">
                      {s}
                    </a>
                    {!tick && <span className="ml-2 text-[10px] text-term-dim">{t("watchlist.noTicker")}</span>}
                  </td>
                  <td className="num px-3 py-1.5 text-right text-zinc-300">
                    {tick?.price == null ? "—" : `$${tick.price.toLocaleString("en-US", { maximumFractionDigits: tick.price < 1 ? 6 : 2 })}`}
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {tick ? <Delta value={tick.change_24h_pct} /> : "—"}
                  </td>
                  <td className="num px-3 py-1.5 text-right text-term-muted">{tick ? fmtUsd(tick.volume_24h_usd) : "—"}</td>
                  <td className="px-3 py-1.5 text-right">
                    <div className="flex justify-end gap-1.5">
                      <a href={`/trade?asset=${s}`} className="text-[11px] text-accent hover:underline">
                        {t("nav.trade")}
                      </a>
                      <button onClick={() => remove(s)} className="text-[11px] text-down/80 hover:text-down">
                        {t("watchlist.remove")}
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {error && <p className="px-3 py-2 text-[11px] text-down">{error}</p>}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 rounded border px-4 py-2 text-xs shadow-lg ${
            toast.kind === "ok"
              ? "border-up/40 bg-up/10 text-up"
              : "border-ai/40 bg-ai/10 text-ai"
          }`}
        >
          {toast.text}
        </div>
      )}
    </Panel>
  );
}
