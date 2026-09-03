import type { Candle } from "./api";

export interface LinePoint {
  time: string;
  value: number;
}

export interface MacdPoint {
  time: string;
  macd: number;
  signal: number;
  hist: number;
}

export function sma(
  candles: Candle[],
  period: number,
  key: "c" | "v" = "c",
): LinePoint[] {
  const out: LinePoint[] = [];
  let sum = 0;
  for (let i = 0; i < candles.length; i++) {
    sum += candles[i][key];
    if (i >= period) sum -= candles[i - period][key];
    if (i >= period - 1) out.push({ time: candles[i].ts, value: sum / period });
  }
  return out;
}

export function ema(candles: Candle[], period: number, key: "c" = "c"): LinePoint[] {
  const k = 2 / (period + 1);
  const out: LinePoint[] = [];
  let prev = 0;
  for (let i = 0; i < candles.length; i++) {
    const v = candles[i][key];
    prev = i === 0 ? v : v * k + prev * (1 - k);
    if (i >= period - 1) out.push({ time: candles[i].ts, value: prev });
  }
  return out;
}

export function boll(candles: Candle[], period = 20, mult = 2) {
  const mid: LinePoint[] = [];
  const upper: LinePoint[] = [];
  const lower: LinePoint[] = [];
  for (let i = period - 1; i < candles.length; i++) {
    const win = candles.slice(i - period + 1, i + 1);
    const mean = win.reduce((s, c) => s + c.c, 0) / period;
    const variance = win.reduce((s, c) => s + (c.c - mean) ** 2, 0) / period;
    const sd = Math.sqrt(variance);
    mid.push({ time: candles[i].ts, value: mean });
    upper.push({ time: candles[i].ts, value: mean + mult * sd });
    lower.push({ time: candles[i].ts, value: mean - mult * sd });
  }
  return { mid, upper, lower };
}

export function macd(candles: Candle[], fast = 12, slow = 26, signalPeriod = 9): MacdPoint[] {
  const emaFast = emaMap(candles, fast);
  const emaSlow = emaMap(candles, slow);
  const macdLine: LinePoint[] = [];
  for (let i = 0; i < candles.length; i++) {
    if (emaFast.has(i) && emaSlow.has(i)) {
      macdLine.push({ time: candles[i].ts, value: emaFast.get(i)! - emaSlow.get(i)! });
    }
  }
  // signal = EMA(macdLine, 9)
  const k = 2 / (signalPeriod + 1);
  const out: MacdPoint[] = [];
  let prevSig = 0;
  for (let i = 0; i < macdLine.length; i++) {
    const m = macdLine[i].value;
    prevSig = i === 0 ? m : m * k + prevSig * (1 - k);
    if (i >= signalPeriod - 1) {
      out.push({
        time: macdLine[i].time,
        macd: m,
        signal: prevSig,
        hist: m - prevSig,
      });
    }
  }
  return out;
}

function emaMap(candles: Candle[], period: number): Map<number, number> {
  const k = 2 / (period + 1);
  const m = new Map<number, number>();
  let prev = 0;
  for (let i = 0; i < candles.length; i++) {
    const v = candles[i].c;
    prev = i === 0 ? v : v * k + prev * (1 - k);
    if (i >= period - 1) m.set(i, prev);
  }
  return m;
}

export function rsi(candles: Candle[], period = 14): LinePoint[] {
  const out: LinePoint[] = [];
  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 1; i < candles.length; i++) {
    const diff = candles[i].c - candles[i - 1].c;
    const gain = Math.max(diff, 0);
    const loss = Math.max(-diff, 0);
    if (i <= period) {
      avgGain += gain / period;
      avgLoss += loss / period;
    } else {
      avgGain = (avgGain * (period - 1) + gain) / period;
      avgLoss = (avgLoss * (period - 1) + loss) / period;
    }
    if (i >= period) {
      const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
      out.push({ time: candles[i].ts, value: 100 - 100 / (1 + rs) });
    }
  }
  return out;
}

export function kdj(candles: Candle[], period = 9): { k: LinePoint[]; d: LinePoint[]; j: LinePoint[] } {
  const k: LinePoint[] = [];
  const d: LinePoint[] = [];
  const j: LinePoint[] = [];
  let prevK = 50;
  let prevD = 50;
  for (let i = period - 1; i < candles.length; i++) {
    const win = candles.slice(i - period + 1, i + 1);
    const high = Math.max(...win.map((c) => c.h));
    const low = Math.min(...win.map((c) => c.l));
    const rsv = high === low ? 50 : ((candles[i].c - low) / (high - low)) * 100;
    prevK = (2 / 3) * prevK + (1 / 3) * rsv;
    prevD = (2 / 3) * prevD + (1 / 3) * prevK;
    k.push({ time: candles[i].ts, value: prevK });
    d.push({ time: candles[i].ts, value: prevD });
    j.push({ time: candles[i].ts, value: 3 * prevK - 2 * prevD });
  }
  return { k, d, j };
}
