"use client";

import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createChart,
  type UTCTimestamp,
} from "lightweight-charts";
import type { Candle } from "@/lib/api";
import { boll, ema, kdj, macd, rsi, sma } from "@/lib/indicators";
import { useI18n } from "@/lib/i18n";
import type { IndicatorSelection } from "@/components/indicator-picker";

const T = (ts: string): UTCTimestamp =>
  (new Date(ts + "Z").getTime() / 1000) as unknown as UTCTimestamp;

const UP = "#0ecb81";
const DOWN = "#f6465d";
const GRID = "#1e2329";
const TEXT = "#848e9c";

const MA_COLORS: Record<number, string> = { 5: "#fcd535", 10: "#e37cf5", 20: "#4aa8ff", 60: "#7cd992" };

/**
 * 全量重建式图表：candles 或指标选择变化时整体 remove() 后重建。
 * 规避 v5 空 pane 残留导致的「指标无法撤回」问题（确定性修复）。
 */
export function CandleChart({
  candles,
  selection,
}: {
  candles: Candle[];
  selection: IndicatorSelection;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const { t } = useI18n();
  const legendRef = useRef<HTMLDivElement>(null);
  const selRef = useRef(selection);
  selRef.current = selection;

  useEffect(() => {
    const box = boxRef.current;
    if (!box || candles.length === 0) return;
    const sel = selRef.current;

    const chart = createChart(box, {
      autoSize: true,
      layout: {
        background: { color: "transparent" },
        textColor: TEXT,
        panes: { separatorColor: GRID },
      },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      crosshair: { mode: 1 },
      timeScale: { timeVisible: true, borderColor: GRID },
      rightPriceScale: { borderColor: GRID },
    });

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: UP,
      downColor: DOWN,
      borderUpColor: UP,
      borderDownColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
    });
    // yahoo 宏观 K 线可能乱序/重复（跳空、结算 bar），v5 严格要求升序唯一 → 统一归一化
    const seen = new Set<number>();
    const rows = candles
      .map((c) => ({ c, time: T(c.ts) }))
      .filter((r) => Number.isFinite(r.time) && !seen.has(r.time) && seen.add(r.time))
      .sort((a, b) => a.time - b.time);
    const cs = rows.map((r) => r.c);
    const timeToIdx = new Map<number, number>();
    rows.forEach((r, i) => timeToIdx.set(r.time, i));

    // OKX 式图例：crosshair 悬停时更新 OHLC/涨跌幅/叠加指标值（DOM 直写，避免 React 重渲）
    const fmt = (v: number): string =>
      Math.abs(v) >= 1000
        ? v.toLocaleString("en-US", { maximumFractionDigits: 2 })
        : String(Number(v.toPrecision(6)));
    const legend = legendRef.current;
    const valMap = (pts: { time: string; value: number }[]) =>
      new Map<number, number>(pts.map((p) => [T(p.time), p.value]));
    const overlayDefs: { label: string; color: string; map: Map<number, number> }[] = [];
    for (const p of sel.ma) {
      overlayDefs.push({ label: `MA${p}`, color: MA_COLORS[p] ?? "#9aa5b1", map: valMap(sma(cs, p)) });
    }
    if (sel.ema12 && !sel.boll) {
      overlayDefs.push({ label: "EMA12", color: "#9aa5b1", map: valMap(ema(cs, 12)) });
    }
    if (sel.ema26 && !sel.boll) {
      overlayDefs.push({ label: "EMA26", color: "#ff9f43", map: valMap(ema(cs, 26)) });
    }
    if (sel.boll) {
      const b = boll(cs);
      overlayDefs.push({ label: "BOLL", color: "#4aa8ff", map: valMap(b.mid) });
    }
    const vmaMaps = sel.volMa
      ? [
          { label: "VOL MA5", color: "#fcd535", map: valMap(sma(cs, 5, "v")) },
          { label: "VOL MA10", color: "#4aa8ff", map: valMap(sma(cs, 10, "v")) },
        ]
      : [];
    const setLegend = (time?: unknown) => {
      if (!legend || rows.length === 0) return;
      const raw =
        typeof time === "number" && timeToIdx.has(time) ? (timeToIdx.get(time) as number) : rows.length - 1;
      const idx = Math.min(Math.max(raw, 0), rows.length - 1);
      const c = rows[idx].c;
      const chg = ((c.c - c.o) / c.o) * 100;
      const color = c.c >= c.o ? UP : DOWN;
      const parts = overlayDefs.map(({ label, color: col, map }) => {
        const v = map.get(rows[idx].time);
        return `<span style="color:${col}">${label} ${v == null ? "—" : fmt(v)}</span>`;
      });
      parts.push(`<span style="color:${TEXT}">VOL ${fmt(c.v)}</span>`);
      for (const { label, color: col, map } of vmaMaps) {
        const v = map.get(rows[idx].time);
        parts.push(`<span style="color:${col}">${label} ${v == null ? "—" : fmt(v)}</span>`);
      }
      legend.innerHTML =
        `<span style="color:${color}">O ${fmt(c.o)}  H ${fmt(c.h)}  L ${fmt(c.l)}  C ${fmt(c.c)}  ` +
        `${chg >= 0 ? "+" : ""}${chg.toFixed(2)}%</span>` +
        `<span style="color:${TEXT}">  ·  </span>` +
        parts.join(`<span style="color:${TEXT}"> · </span>`);
    };
    setLegend();

    const data = rows.map((r) => ({
      time: r.time,
      open: r.c.o,
      high: r.c.h,
      low: r.c.l,
      close: r.c.c,
    }));
    candle.setData(data);

    const vol = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceScaleId: "vol" },
      1,
    );
    vol.setData(
      rows.map((r) => ({
        time: r.time,
        value: r.c.v,
        color: r.c.c >= r.c.o ? "rgba(14,203,129,0.45)" : "rgba(246,70,93,0.45)",
      })),
    );
    chart.panes()[1].setHeight(70);

    const addLine = (color: string, pane: number, width: 1 | 2 = 1) =>
      chart.addSeries(
        LineSeries,
        { color, lineWidth: width, priceLineVisible: false, lastValueVisible: false },
        pane,
      );

    // 主图叠加：MA / EMA / BOLL
    for (const p of sel.ma) {
      const color = MA_COLORS[p] ?? "#9aa5b1";
      addLine(color, 0, 2).setData(sma(cs, p).map((pt) => ({ time: T(pt.time), value: pt.value })));
    }
    if (sel.ema12 && !sel.boll) {
      addLine("#9aa5b1", 0).setData(ema(cs, 12).map((pt) => ({ time: T(pt.time), value: pt.value })));
    }
    if (sel.boll) {
      const { mid, upper, lower } = boll(cs);
      addLine("#4aa8ff", 0).setData(mid.map((pt) => ({ time: T(pt.time), value: pt.value })));
      for (const pts of [upper, lower]) {
        addLine("rgba(252,213,53,0.6)", 0).setData(pts.map((pt) => ({ time: T(pt.time), value: pt.value })));
      }
    }
    if (sel.ema26 && sel.boll) {
      addLine("#ff9f43", 0).setData(ema(cs, 26).map((pt) => ({ time: T(pt.time), value: pt.value })));
    }

    // 成交量均线（VOL pane 内，参照 OKX）
    if (sel.volMa) {
      addLine("#fcd535", 1).setData(sma(cs, 5, "v").map((pt) => ({ time: T(pt.time), value: pt.value })));
      addLine("#4aa8ff", 1).setData(sma(cs, 10, "v").map((pt) => ({ time: T(pt.time), value: pt.value })));
    }

    chart.subscribeCrosshairMove((param) => setLegend(param.time));

    // 副图指标（顺序 pane：2,3,4…）
    if (sel.macd) {
      const pane = chart.panes().length;
      const m = macd(cs);
      const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, pane);
      hist.setData(
        m.map((pt) => ({
          time: T(pt.time),
          value: pt.hist,
          color: pt.hist >= 0 ? "rgba(14,203,129,0.6)" : "rgba(246,70,93,0.6)",
        })),
      );
      addLine("#fcd535", pane).setData(m.map((pt) => ({ time: T(pt.time), value: pt.macd })));
      addLine("#4aa8ff", pane).setData(m.map((pt) => ({ time: T(pt.time), value: pt.signal })));
      chart.panes()[pane].setHeight(80);
    }
    if (sel.rsi) {
      const pane = chart.panes().length;
      const s = addLine("#e37cf5", pane);
      s.setData(rsi(cs).map((pt) => ({ time: T(pt.time), value: pt.value })));
      s.createPriceLine({ price: 70, color: DOWN, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "70" });
      s.createPriceLine({ price: 30, color: UP, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "30" });
      chart.panes()[pane].setHeight(70);
    }
    if (sel.kdj) {
      const pane = chart.panes().length;
      const { k, d, j } = kdj(cs);
      addLine("#fcd535", pane).setData(k.map((pt) => ({ time: T(pt.time), value: pt.value })));
      addLine("#4aa8ff", pane).setData(d.map((pt) => ({ time: T(pt.time), value: pt.value })));
      addLine("#e37cf5", pane).setData(j.map((pt) => ({ time: T(pt.time), value: pt.value })));
      chart.panes()[pane].setHeight(70);
    }

    chart.timeScale().fitContent();

    return () => {
      chart.remove();
    };
  }, [candles, selection]);

  const wrapRef = useRef<HTMLDivElement>(null);
  const [isFull, setIsFull] = useState(false);

  const toggleFullscreen = () => {
    const el = wrapRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen();
    } else {
      void el.requestFullscreen();
    }
  };

  useEffect(() => {
    const onChange = () => setIsFull(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  return (
    <div ref={wrapRef} className={`relative bg-term-bg ${isFull ? "flex h-full flex-col justify-center p-4" : ""}`}>
      <button
        type="button"
        onClick={toggleFullscreen}
        title={isFull ? t("asset.exitFullscreen") : t("asset.fullscreen")}
        className="absolute right-2 top-1 z-20 rounded border border-term-border bg-term-panel/80 px-1.5 py-0.5 text-[10px] text-term-muted hover:text-accent"
      >
        {isFull ? "⤡" : "⛶"}
      </button>
      <div
        ref={legendRef}
        className="num pointer-events-none absolute left-2 top-1 z-10 max-w-full truncate text-[11px]"
      />
      <div ref={boxRef} className={isFull ? "h-[82vh] w-full" : "h-[440px] w-full"} />
    </div>
  );
}
