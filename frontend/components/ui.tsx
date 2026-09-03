import type { ReactNode } from "react";
import { useI18n } from "@/lib/i18n";

export function Panel({
  title,
  subtitle,
  right,
  children,
  className = "",
  bodyClass = "",
}: {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={`rounded-md border border-term-border bg-term-panel ${className}`}>
      {(title || right) && (
        <header className="flex items-center justify-between px-4 py-2.5">
          <div className="flex items-baseline gap-2">
            {title && (
              <h2 className="text-sm font-semibold text-zinc-100">{title}</h2>
            )}
            {subtitle && <span className="text-[11px] text-term-dim">{subtitle}</span>}
          </div>
          {right}
        </header>
      )}
      <div className={bodyClass || "p-3"}>{children}</div>
    </section>
  );
}

const toneMap = {
  up: "text-up border-up/30 bg-up/10",
  down: "text-down border-down/30 bg-down/10",
  flat: "text-term-muted border-term-border bg-term-panel2",
  accent: "text-accent border-accent/30 bg-accent/10",
  ai: "text-accent border-accent/30 bg-accent/10",
  violet: "text-term-bg border-accent/50 bg-accent/20",
} as const;

export type Tone = keyof typeof toneMap;

export function Badge({ tone = "flat", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${toneMap[tone]}`}
    >
      {children}
    </span>
  );
}

export function Delta({
  value,
  suffix = "%",
  digits = 2,
  className = "",
}: {
  value: number | null | undefined;
  suffix?: string;
  digits?: number;
  className?: string;
}) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return <span className={`num text-term-dim ${className}`}>—</span>;
  }
  const tone = value > 0 ? "text-up" : value < 0 ? "text-down" : "text-term-muted";
  const sign = value > 0 ? "+" : "";
  return (
    <span className={`num ${tone} ${className}`}>
      {sign}
      {value.toFixed(digits)}
      {suffix}
    </span>
  );
}

export function Bar({
  value,
  max = 100,
  tone = "accent",
}: {
  value: number;
  max?: number;
  tone?: "up" | "down" | "accent" | "ai";
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const color = { up: "bg-up", down: "bg-down", accent: "bg-accent", ai: "bg-accent" }[tone];
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-term-panel2">
      <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Sparkline({
  values,
  width = 280,
  height = 64,
  fill = false,
}: {
  values: number[];
  width?: number;
  height?: number;
  fill?: boolean;
}) {
  if (values.length < 2) return <div style={{ height }} />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / (values.length - 1);
  const pts = values
    .map((v, i) => `${(i * step).toFixed(1)},${(height - 4 - ((v - min) / span) * (height - 8)).toFixed(1)}`)
    .join(" ");
  const rising = values[values.length - 1] >= values[0];
  const stroke = rising ? "var(--color-up)" : "var(--color-down)";
  const gid = `sg-${Math.abs(values[0] * 7919 + values.length * 31).toFixed(0)}`;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      {fill && (
        <>
          <defs>
            <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
              <stop offset="100%" stopColor={stroke} stopOpacity="0" />
            </linearGradient>
          </defs>
          <polygon points={`0,${height} ${pts} ${width},${height}`} fill={`url(#${gid})`} stroke="none" />
        </>
      )}
      <polyline points={pts} fill="none" stroke={stroke} strokeWidth="1.5" />
    </svg>
  );
}

export function StatCell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wider text-term-dim">{label}</span>
      <span className="num text-base font-medium text-zinc-100">{children}</span>
    </div>
  );
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="animate-pulse space-y-2 p-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-4 rounded bg-term-panel2" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function ErrorPanel({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-md border border-down/30 bg-down/5 p-4 text-sm text-down">
      <p className="font-semibold">数据加载失败</p>
      <p className="mt-1 text-xs text-down/80">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="btn-primary mt-3 px-4 py-1.5 text-xs"
        >
          重试
        </button>
      )}
    </div>
  );
}

export function Empty({ text }: { text: string }) {
  return <p className="py-6 text-center text-xs text-term-dim">{text}</p>;
}
