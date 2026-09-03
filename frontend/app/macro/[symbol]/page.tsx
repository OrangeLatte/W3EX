"use client";

import { use, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { getMacroHistory, postAssetChat, type AiChatReply } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { Badge, Delta, ErrorPanel, Panel, Skeleton } from "@/components/ui";
import { CandleChart } from "@/components/candle-chart";
import { IndicatorPicker, DEFAULT_SELECTION, type IndicatorSelection } from "@/components/indicator-picker";
import type { Candle } from "@/lib/api";

const RANGES = ["5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"] as const;
const INTERVALS = ["1d", "1h", "15m", "5m"] as const;

const MACRO_NAMES: Record<string, string> = {
  SPX: "S&P 500", NDX: "Nasdaq 100", DJI: "Dow Jones", DAX: "DAX",
  FTSE: "FTSE 100", N225: "Nikkei 225", HSI: "恒生指数",
  XAU: "黄金", XAG: "白银", WTI: "WTI 原油", BRENT: "布伦特原油",
  NATGAS: "天然气", COPPER: "铜",
};

export default function MacroDetailPage({ params }: { params: Promise<{ symbol: string }> }) {
  const { symbol: raw } = use(params);
  const symbol = raw.toUpperCase();
  const { t } = useI18n();
  const [range, setRange] = useState<string>("5y");
  const [interval, setInterval] = useState<string>("1d");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState<IndicatorSelection>(DEFAULT_SELECTION);
  const lastDataRef = useRef<Candle[]>([]);

  useEffect(() => {
    let alive = true;
    if (lastDataRef.current.length > 0) setRefreshing(true);
    setLoading((prev) => prev || lastDataRef.current.length === 0);
    setError(null);
    getMacroHistory(symbol, range, interval)
      .then((h) => {
        if (!alive) return;
        setCandles(h.candles);
        lastDataRef.current = h.candles;
      })
      .catch((e) => alive && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => {
        if (!alive) return;
        setLoading(false);
        setRefreshing(false);
      });
    return () => {
      alive = false;
    };
  }, [symbol, range, interval]);

  // ---------- AI 对话（macro 标的，消耗模型 API） ----------
  const [messages, setMessages] = useState<{ role: string; content: string; source?: string }[]>([]);
  const [input, setInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);

  const sendChat = async () => {
    const text = input.trim();
    if (!text || chatBusy) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setChatBusy(true);
    try {
      const history = messages.slice(-20).map((m) => ({ role: m.role, content: m.content }));
      const reply: AiChatReply = await postAssetChat(symbol, {
        message: text,
        interval: interval === "15m" ? "15m" : "1h",
        range,
        history,
      });
      setMessages((m) => [...m, { role: "assistant", content: reply.reply, source: reply.source }]);
    } catch (e) {
      setMessages((m) => [
        ...m,
        { role: "assistant", content: e instanceof Error ? e.message : String(e), source: "error" },
      ]);
    } finally {
      setChatBusy(false);
    }
  };

  const view = candles.length > 0 ? candles : lastDataRef.current;
  const last = view.length > 0 ? view[view.length - 1].c : null;
  const prev = view.length > 1 ? view[view.length - 2].c : null;
  const changePct = last !== null && prev ? ((last - prev) / prev) * 100 : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-baseline gap-3">
          <Link href="/macro" className="text-xs text-term-muted hover:text-zinc-200">
            ← {t("nav.macro")}
          </Link>
          <h1 className="text-lg font-bold text-zinc-100">
            {symbol} <span className="text-sm font-normal text-term-muted">{MACRO_NAMES[symbol] ?? ""}</span>
          </h1>
          {last !== null && <span className="num text-xl text-zinc-100">{fmtNum(last)}</span>}
          <Delta value={changePct} />
          <Badge tone="accent">Yahoo Finance</Badge>
        </div>
        {refreshing && <span className="text-xs text-term-dim">{t("common.refreshing")}</span>}
      </div>

      <Panel bodyClass="p-3" title={t("asset.chart")}>
        <div className="mb-2 flex flex-wrap items-center gap-3">
          <div className="flex gap-1">
            {RANGES.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setRange(r)}
                className={`rounded px-2 py-0.5 text-[11px] ${range === r ? "bg-accent/15 text-accent" : "text-term-muted hover:text-zinc-200"}`}
              >
                {r}
              </button>
            ))}
          </div>
          <div className="flex gap-1 border-s border-term-border ps-3">
            {INTERVALS.map((iv) => (
              <button
                key={iv}
                type="button"
                onClick={() => setInterval(iv)}
                className={`rounded px-2 py-0.5 text-[11px] ${interval === iv ? "bg-accent/15 text-accent" : "text-term-muted hover:text-zinc-200"}`}
              >
                {iv}
              </button>
            ))}
          </div>
          <div className="ms-auto">
            <IndicatorPicker value={selection} onChange={setSelection} />
          </div>
        </div>
        {loading && view.length === 0 ? (
          <Skeleton rows={5} />
        ) : error && view.length === 0 ? (
          <ErrorPanel message={error} />
        ) : view.length > 2 ? (
          <CandleChart candles={view} selection={selection} />
        ) : (
          <p className="py-6 text-center text-xs text-term-dim">{t("common.noData")}</p>
        )}
      </Panel>

      <Panel title={`AI · ${symbol}`} bodyClass="p-3">
        <div className="flex max-h-80 flex-col gap-2 overflow-y-auto">
          {messages.length === 0 && (
            <p className="py-4 text-center text-xs text-term-dim">{t("asset.chatHint")}</p>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              className={`rounded border p-2 text-xs ${
                m.role === "user"
                  ? "border-accent/20 bg-accent/5 text-zinc-200"
                  : "border-term-border bg-term-panel2 text-zinc-300"
              }`}
            >
              {m.source === "error" && <Badge tone="down">error</Badge>}
              <p className="whitespace-pre-wrap">{m.content}</p>
            </div>
          ))}
          {chatBusy && <p className="text-xs text-term-dim">{t("common.loading")}</p>}
        </div>
        <div className="mt-2 flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.nativeEvent.isComposing) void sendChat();
            }}
            placeholder={t("asset.chatPlaceholder")}
            className="flex-1 rounded border border-term-border bg-term-bg px-3 py-1.5 text-xs text-zinc-200 outline-none focus:border-accent/50"
          />
          <button type="button" onClick={() => void sendChat()} disabled={chatBusy || !input.trim()} className="btn-primary px-4 text-xs">
            {t("asset.chatSend")}
          </button>
        </div>
        <p className="mt-2 text-[10px] text-term-dim">{t("common.disclaimer")}</p>
      </Panel>
    </div>
  );
}
