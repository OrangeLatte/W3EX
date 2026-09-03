"use client";

import { useI18n } from "@/lib/i18n";

export interface IndicatorSelection {
  ma: number[];
  ema12: boolean;
  ema26: boolean;
  boll: boolean;
  volMa: boolean;
  macd: boolean;
  rsi: boolean;
  kdj: boolean;
}

export const DEFAULT_SELECTION: IndicatorSelection = {
  ma: [5, 20],
  ema12: false,
  ema26: false,
  boll: false,
  volMa: true,
  macd: true,
  rsi: true,
  kdj: false,
};

const MA_PERIODS = [5, 10, 20, 60];
const SUBS: { key: keyof IndicatorSelection; label: string }[] = [
  { key: "macd", label: "MACD" },
  { key: "rsi", label: "RSI(14)" },
  { key: "kdj", label: "KDJ" },
];

export function IndicatorPicker({
  value,
  onChange,
}: {
  value: IndicatorSelection;
  onChange: (v: IndicatorSelection) => void;
}) {
  const { t } = useI18n();

  const toggleMa = (p: number) => {
    const has = value.ma.includes(p);
    onChange({ ...value, ma: has ? value.ma.filter((x) => x !== p) : [...value.ma, p] });
  };

  const box = (active: boolean) =>
    `flex items-center gap-1.5 rounded px-2 py-1 text-xs transition ${
      active
        ? "bg-accent/10 text-accent"
        : "text-term-muted hover:bg-term-panel2 hover:text-zinc-300"
    }`;

  const check = (active: boolean) => (
    <span
      className={`flex h-3.5 w-3.5 items-center justify-center rounded-[3px] border text-[9px] leading-none ${
        active ? "border-accent bg-accent text-black" : "border-term-muted"
      }`}
    >
      {active ? "✓" : ""}
    </span>
  );

  return (
    <div className="flex flex-wrap items-center gap-1">
      <span className="me-1 text-[10px] uppercase tracking-wider text-term-dim">
        {t("asset.main")}
      </span>
      {MA_PERIODS.map((p) => {
        const active = value.ma.includes(p);
        return (
          <button key={p} type="button" onClick={() => toggleMa(p)} className={box(active)}>
            {check(active)}MA{p}
          </button>
        );
      })}
      <button
        type="button"
        onClick={() => onChange({ ...value, ema12: !value.ema12 })}
        className={box(value.ema12)}
      >
        {check(value.ema12)}EMA(12)
      </button>
      <button
        type="button"
        onClick={() => onChange({ ...value, ema26: !value.ema26 })}
        className={box(value.ema26)}
      >
        {check(value.ema26)}EMA(26)
      </button>
      <button
        type="button"
        onClick={() => onChange({ ...value, boll: !value.boll })}
        className={box(value.boll)}
      >
        {check(value.boll)}BOLL(20,2)
      </button>
      <span className="mx-1 h-3 w-px bg-term-border" />
      <span className="me-1 text-[10px] uppercase tracking-wider text-term-dim">
        {t("asset.volume")}
      </span>
      <button
        type="button"
        onClick={() => onChange({ ...value, volMa: !value.volMa })}
        className={box(value.volMa)}
      >
        {check(value.volMa)}MA(5/10)
      </button>
      <span className="mx-1 h-3 w-px bg-term-border" />
      <span className="me-1 text-[10px] uppercase tracking-wider text-term-dim">
        {t("asset.sub")}
      </span>
      {SUBS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange({ ...value, [key]: !value[key] })}
          className={box(Boolean(value[key]))}
        >
          {check(Boolean(value[key]))}
          {label}
        </button>
      ))}
    </div>
  );
}
