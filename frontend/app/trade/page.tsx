"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  getQuote,
  postConfirm,
  postCancel,
  getReplay,
  getAccount,
  resetAccount,
  type AccountSummary,
  type Quote,
  type ExecResult,
  type ReplayResult,
  type Route,
} from "@/lib/api";
import { fmtUsd } from "@/lib/format";
import { Badge, ErrorPanel, Panel } from "@/components/ui";
import { OrderPanel } from "@/components/order-panel";
import { useI18n } from "@/lib/i18n";

const INTENTS = [
  { id: "buy_spot", label: "trade.buySpot", side: "buy", market_type: "spot" },
  { id: "sell_spot", label: "trade.sellSpot", side: "sell", market_type: "spot" },
  { id: "long_perp", label: "trade.longPerp", side: "buy", market_type: "perp" },
  { id: "short_perp", label: "trade.shortPerp", side: "sell", market_type: "perp" },
] as const;

const SLIP_PRESETS = [
  { v: 10, label: "10 bps" },
  { v: 50, label: "50 bps" },
  { v: 100, label: "100 bps" },
  { v: 0, label: "trade.unlimited" },
];
const AGE_PRESETS = [
  { v: 1000, label: "≤1s" },
  { v: 2000, label: "≤2s" },
  { v: 5000, label: "≤5s" },
  { v: 0, label: "trade.unlimited" },
];
const LEVERAGES = [1, 2, 5, 10, 20];

const KIND_LABEL: Record<string, string> = { cex: "CEX", dex: "DEX", perp: "PERP" };
const BASIS_LABEL: Record<string, string> = {
  total_cost_usd: "trade.basisCost",
  net_proceeds_usd: "trade.basisNet",
};
const STAGE_LABEL: Record<string, string> = {
  order_accepted: "stage.order_accepted",
  matched: "stage.matched",
  settled: "stage.settled",
  quote_locked: "stage.quote_locked",
  signed: "stage.signed",
  broadcast: "stage.broadcast",
  confirmed: "stage.confirmed",
  position_opened: "stage.position_opened",
};

function bps(pct: number): number {
  return Math.round(pct * 100);
}

function AgeChip({ ms }: { ms: number }) {
  const { t } = useI18n();
  const ok = ms <= 2000;
  return (
    <span className={`num text-[11px] ${ok ? "text-up" : "text-ai"}`} title={t("trade.ageTip")}>
      {ms}ms
    </span>
  );
}

function RouteCards({
  routes,
  best,
  selected,
  onPick,
  side,
}: {
  routes: Route[];
  best: number;
  selected: number;
  onPick: (i: number) => void;
  side: string;
}) {
  const { t } = useI18n();
  return (
    <div className="space-y-2 md:hidden">
      {routes.map((r, i) => (
        <button
          key={r.venue}
          onClick={() => onPick(i)}
          className={`w-full rounded-md border p-3 text-left ${
            i === best ? "border-up/50 bg-up/5" : "border-term-border bg-term-panel2"
          } ${selected === i ? "ring-1 ring-accent" : ""}`}
        >
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-zinc-200">
              {r.venue}
              {i === best && <span className="ml-1.5 text-[10px] text-up">best</span>}
            </span>
            <Badge tone={r.instrument_type === "perp" ? "violet" : "flat"}>
              {KIND_LABEL[r.kind]}
            </Badge>
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1 text-[11px]">
            <span className="text-term-dim">{t("trade.price")}</span>
            <span className="num text-right text-zinc-200">${Number(r.price).toLocaleString("en-US")}</span>
            <span className="text-term-dim">{t("trade.slippage")}</span>
            <span className="num text-right text-term-muted">{r.slippage_pct.toFixed(3)}%</span>
            <span className="text-term-dim">{t("trade.feesGas")}</span>
            <span className="num text-right text-term-muted">
              {fmtUsd(r.fees_usd)} + {fmtUsd(r.gas_usd)}
            </span>
            <span className="text-term-dim">{side === "buy" ? t("trade.basisCost") : t("trade.basisNet")}</span>
            <span className="num text-right text-zinc-200">
              {side === "buy" ? fmtUsd(r.total_cost_usd) : fmtUsd(r.net_proceeds_usd)}
            </span>
            <span className="text-term-dim">{side === "buy" ? t("trade.worstCost") : t("trade.worstReceive")}</span>
            <span className="num text-right text-ai">
              {r.worst_receive ? (side === "buy" ? fmtUsd(r.worst_receive) : fmtUsd(r.worst_receive)) : "—"}
            </span>
            <span className="text-term-dim">{t("trade.dataAge")}</span>
            <span className="text-right">
              <AgeChip ms={r.data_age_ms} />
            </span>
            {r.instrument_type === "perp" && (
              <>
                <span className="text-term-dim">{t("trade.margin")}</span>
                <span className="num text-right text-zinc-200">{fmtUsd(r.margin_required_usd)}</span>
                <span className="text-term-dim">{t("trade.liqDist")}</span>
                <span className="num text-right text-down">≈{r.liquidation_distance_pct}%</span>
              </>
            )}
          </div>
        </button>
      ))}
    </div>
  );
}

function AccountCard() {
  const { t } = useI18n();
  const [acct, setAcct] = useState<AccountSummary | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => getAccount().then(setAcct).catch(() => undefined);
  useEffect(() => {
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, []);

  const doReset = async () => {
    if (!window.confirm(t("account.resetConfirm"))) return;
    setBusy(true);
    try {
      await resetAccount();
      await load();
    } catch {
      /* 静默 */
    } finally {
      setBusy(false);
    }
  };

  const cells: [string, string][] = acct
    ? [
        [t("account.equity"), fmtUsd(acct.equity_usd)],
        [t("account.available"), fmtUsd(acct.available_usd)],
        [t("account.marginUsed"), fmtUsd(acct.margin_used_usd)],
        [t("account.realized"), fmtUsd(acct.realized_pnl_usd)],
        [t("account.unrealized"), fmtUsd(acct.unrealized_pnl_usd)],
        [t("account.positions"), String(acct.open_positions)],
        [t("account.orders"), String(acct.orders_count)],
      ]
    : [];
  return (
    <Panel
      title={t("account.title")}
      right={
        <button
          onClick={doReset}
          disabled={busy || !acct}
          className="rounded border border-down/40 px-2 py-1 text-[11px] text-down transition hover:bg-down/10 disabled:opacity-40"
        >
          {t("account.reset")} {acct ? `(${acct.reset_count})` : ""}
        </button>
      }
      bodyClass="p-3"
    >
      <div className="grid grid-cols-3 gap-3 md:grid-cols-7">
        {cells.map(([k, v]) => (
          <div key={k} className="flex flex-col gap-0.5">
            <span className="text-[10px] uppercase tracking-wider text-term-dim">{k}</span>
            <span className="num text-sm text-zinc-100">{v}</span>
          </div>
        ))}
        {!acct && <span className="text-xs text-term-dim">{t("common.loading")}</span>}
      </div>
      <p className="mt-2 text-[10px] text-term-dim">{t("account.note")}</p>
    </Panel>
  );
}

function TradeInner() {
  const { t } = useI18n();
  const sp = useSearchParams();
  const asset = (sp.get("asset") || "BTC").toUpperCase();

  const [intentId, setIntentId] = useState<string>("buy_spot");
  const intent = INTENTS.find((i) => i.id === intentId)!;
  const [amount, setAmount] = useState("1000");
  const [slip, setSlip] = useState(50);
  const [age, setAge] = useState(2000);
  const [leverage, setLeverage] = useState(1);

  const [quote, setQuote] = useState<Quote | null>(null);
  const [result, setResult] = useState<ExecResult | null>(null);
  const [replay, setReplay] = useState<ReplayResult | null>(null);
  const [selected, setSelected] = useState(0);
  const [loading, setLoading] = useState(false);
  const [stage, setStage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState(0);
  const idemKey = useRef<string>("");

  useEffect(() => {
    if (!quote?.expires_at) return;
    const exp = new Date(quote.expires_at + "Z").getTime();
    const t = setInterval(() => {
      const s = Math.max(0, Math.floor((exp - Date.now()) / 1000));
      setLeft(s);
      if (s === 0) clearInterval(t);
    }, 1000);
    return () => clearInterval(t);
  }, [quote?.expires_at]);

  const fetchQuote = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setReplay(null);
    setQuote(null);
    setStage(t("trade.stageConnect"));
    const t1 = setTimeout(() => setStage(t("trade.stageAggregate")), 500);
    const t2 = setTimeout(() => setStage(t("trade.stageCompare")), 1200);
    try {
      const q = await getQuote({
        side: intent.side,
        asset,
        amount,
        market_type: intent.market_type,
        max_slippage_bps: slip,
        max_data_age_ms: age,
        leverage: intent.market_type === "perp" ? leverage : 1,
      });
      setQuote(q);
      setSelected(Math.max(q.best_route_index, 0));
      idemKey.current = crypto.randomUUID();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      clearTimeout(t1);
      clearTimeout(t2);
      setStage("");
      setLoading(false);
    }
  };

  const confirm = async () => {
    if (!quote?.quote_id || loading) return;
    setLoading(true);
    setError(null);
    try {
      const r = await postConfirm(quote.quote_id, selected, idemKey.current);
      setResult(r);
      try {
        setReplay(await getReplay(quote.quote_id));
      } catch {
        /* 回放失败不影响成交展示 */
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const cancel = async () => {
    if (!quote?.quote_id) return;
    try {
      await postCancel(quote.quote_id);
      setQuote(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const expired = quote?.expires_at ? left === 0 : false;
  const perp = intent.market_type === "perp";

  return (
    <div className="space-y-4">
      <div className="rounded-md border border-accent/25 bg-accent/5 px-3 py-2 text-[11px] leading-relaxed text-accent">
        {t("trade.wsSubtitle")}
      </div>

      {error && <ErrorPanel message={error} onRetry={quote?.quote_id ? confirm : fetchQuote} />}

      {/* 1. 交易意图 + 约束 */}
      <Panel title="Trading Intent" subtitle={t("trade.intentSubtitle")}>
        <div className="flex flex-wrap gap-2">
          {INTENTS.map((it) => (
            <button
              key={it.id}
              onClick={() => {
                setIntentId(it.id);
                setQuote(null);
                setResult(null);
                setReplay(null);
              }}
              className={`rounded border px-3 py-1.5 text-xs font-medium transition ${
                intentId === it.id
                  ? it.market_type === "perp"
                    ? "border-violet-400/50 bg-violet-400/10 text-violet-300"
                    : "border-accent/50 bg-accent/10 text-accent"
                  : "border-term-border text-term-muted hover:bg-term-panel2"
              }`}
            >
              {t(it.label)}
            </button>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <label className="col-span-1 flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-term-dim">{t("trade.asset")}</span>
            <input
              value={asset}
              readOnly
              className="num rounded border border-term-border bg-term-panel2 px-2 py-1.5 text-sm text-zinc-200"
            />
          </label>
          <label className="col-span-1 flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-term-dim">{t("trade.amountUsd")}</span>
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputMode="decimal"
              className="num rounded border border-term-border bg-term-panel2 px-2 py-1.5 text-sm text-zinc-200"
            />
          </label>
          <div className="col-span-1 flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-term-dim">{t("trade.maxSlippage")}</span>
            <div className="flex flex-wrap gap-1">
              {SLIP_PRESETS.map((p) => (
                <button
                  key={p.v}
                  onClick={() => setSlip(p.v)}
                  className={`rounded px-1.5 py-1 text-[10px] ${
                    slip === p.v ? "bg-accent/15 text-accent" : "bg-term-panel2 text-term-muted"
                  }`}
                >
                  {t(p.label)}
                </button>
              ))}
            </div>
          </div>
          <div className="col-span-1 flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-term-dim">{t("trade.dataFreshness")}</span>
            <div className="flex flex-wrap gap-1">
              {AGE_PRESETS.map((p) => (
                <button
                  key={p.v}
                  onClick={() => setAge(p.v)}
                  className={`rounded px-1.5 py-1 text-[10px] ${
                    age === p.v ? "bg-accent/15 text-accent" : "bg-term-panel2 text-term-muted"
                  }`}
                >
                  {t(p.label)}
                </button>
              ))}
            </div>
          </div>
        </div>
        {perp && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] uppercase tracking-wider text-term-dim">{t("trade.leverage")}</span>
            {LEVERAGES.map((l) => (
              <button
                key={l}
                onClick={() => setLeverage(l)}
                className={`rounded px-2 py-1 text-[11px] ${
                  leverage === l ? "bg-violet-400/15 text-violet-300" : "bg-term-panel2 text-term-muted"
                }`}
              >
                {l}x
              </button>
            ))}
          </div>
        )}
        <button onClick={fetchQuote} disabled={loading} className="btn-primary mt-3 w-full py-2 text-sm md:w-auto md:px-6">
          {loading ? stage || t("trade.quoting") : t("trade.getQuote")}
        </button>
      </Panel>

      {/* 2. 路由对比（桌面表格 / 移动卡片） */}
      {quote && quote.quote_id === null && (
        <Panel title={t("trade.noRoute")}>
          <p className="text-sm text-down">{quote.recommendation_reason}</p>
          <div className="mt-2 space-y-1">
            {quote.filtered_routes.map((f, i) => (
              <p key={i} className="text-xs text-term-muted">
                · {f.route.venue}：{f.reason}
              </p>
            ))}
          </div>
        </Panel>
      )}

      {quote && quote.quote_id && (
        <Panel
          title="Route Comparison"
          subtitle={`${quote.side.toUpperCase()} ${fmtUsd(quote.fiat_amount)} ${quote.asset} · ${t(perp ? "trade.perpOnly" : "trade.spotOnly")}`}
          right={
            <span className="num text-[11px] text-term-muted">
              {expired ? (
                <span className="text-down">{t("trade.expired")}</span>
              ) : (
                t("trade.validFor").replace("{n}", String(left))
              )}
            </span>
          }
          bodyClass="p-0"
        >
          <p className="border-b border-term-border px-3 py-2 text-xs text-zinc-300">
            <span className="text-accent">{t("trade.recommend")}</span>
            {quote.recommendation_reason}
            {quote.constraints && (
              <span className="ml-2 text-term-dim">
                {t("trade.constraintPre")}{quote.constraints.max_slippage_bps || "∞"}{t("trade.constraintMid")}
                {quote.constraints.max_data_age_ms || "∞"}{t("trade.constraintPost")}
              </span>
            )}
          </p>

          {/* 桌面表格 */}
          <div className="hidden overflow-x-auto md:block">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-term-border text-left text-[10px] uppercase tracking-wider text-term-dim">
                  <th className="px-3 py-1.5"></th>
                  <th className="px-3 py-1.5">Venue</th>
                  <th className="px-3 py-1.5 text-right">Price</th>
                  <th className="px-3 py-1.5 text-right">Slippage</th>
                  <th className="px-3 py-1.5 text-right">Fees</th>
                  <th className="px-3 py-1.5 text-right">{quote.side === "buy" ? "Total Cost" : "Net Receive"}</th>
                  <th className="px-3 py-1.5 text-right">Worst Case</th>
                  <th className="px-3 py-1.5 text-right">Age</th>
                  {perp && (
                    <>
                      <th className="px-3 py-1.5 text-right">Margin</th>
                      <th className="px-3 py-1.5 text-right">Liq Dist</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-term-border/60">
                {quote.routes.map((r, i) => (
                  <tr
                    key={r.venue}
                    onClick={() => setSelected(i)}
                    className={`cursor-pointer transition ${
                      i === quote.best_route_index ? "bg-up/5" : "hover:bg-term-panel2"
                    } ${selected === i ? "ring-1 ring-inset ring-accent/50" : ""}`}
                  >
                    <td className="px-3 py-2">
                      <input type="radio" checked={selected === i} readOnly className="accent-accent" />
                    </td>
                    <td className="px-3 py-2 text-zinc-200">
                      {r.venue}
                      {i === quote.best_route_index && <span className="ml-1.5 text-[10px] text-up">best</span>}
                    </td>
                    <td className="num px-3 py-2 text-right text-zinc-200">
                      ${Number(r.price).toLocaleString("en-US", { maximumFractionDigits: 4 })}
                    </td>
                    <td className="num px-3 py-2 text-right text-term-muted">
                      {r.slippage_pct.toFixed(3)}% ({bps(r.slippage_pct)}bps)
                    </td>
                    <td className="num px-3 py-2 text-right text-term-muted">
                      {fmtUsd(r.fees_usd)} + {fmtUsd(r.gas_usd)}
                    </td>
                    <td className="num px-3 py-2 text-right text-zinc-200">
                      {quote.side === "buy" ? fmtUsd(r.total_cost_usd) : fmtUsd(r.net_proceeds_usd)}
                    </td>
                    <td className="num px-3 py-2 text-right text-ai">
                      {r.worst_receive ? fmtUsd(r.worst_receive) : "—"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <AgeChip ms={r.data_age_ms} />
                    </td>
                    {perp && (
                      <>
                        <td className="num px-3 py-2 text-right text-zinc-200">
                          {fmtUsd(r.margin_required_usd)}
                        </td>
                        <td className="num px-3 py-2 text-right text-down">
                          ≈{r.liquidation_distance_pct}%
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 移动卡片 */}
          <div className="p-3">
            <RouteCards
              routes={quote.routes}
              best={quote.best_route_index}
              selected={selected}
              onPick={setSelected}
              side={quote.side}
            />
          </div>

          {quote.filtered_routes.length > 0 && (
            <details className="border-t border-term-border px-3 py-2 text-xs">
              <summary className="cursor-pointer text-term-muted">
                {quote.filtered_routes.length} {t("trade.filteredCount")}
              </summary>
              <div className="mt-2 space-y-1">
                {quote.filtered_routes.map((f, i) => (
                  <p key={i} className="text-term-dim">
                    · {f.route.venue}：{f.reason}
                  </p>
                ))}
              </div>
            </details>
          )}
        </Panel>
      )}

      {/* 3. 风险确认 + 执行 */}
      {quote?.quote_id && quote.routes[selected] && !result && (
        <Panel title="Pre-Trade Risk" subtitle={t("trade.riskSubtitle")}>
          {(() => {
            const r = quote.routes[selected];
            return (
              <div className="space-y-2 text-xs">
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-term-dim">{t("trade.route")}</p>
                    <p className="text-sm text-zinc-200">
                      {r.venue} · {KIND_LABEL[r.kind]}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-term-dim">
                      {t("trade.worstCase")}{quote.side === "buy" ? t("trade.basisCost") : t("trade.basisNet")}
                    </p>
                    <p className="num text-sm text-ai">
                      {r.worst_receive ? fmtUsd(r.worst_receive) : "—"}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-term-dim">{t("trade.feeBreakdown")}</p>
                    <p className="num text-sm text-zinc-200">
                      {t("trade.feeLabel")} {fmtUsd(r.fees_usd)} + {t("trade.gasLabel")} {fmtUsd(r.gas_usd)}
                    </p>
                  </div>
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-term-dim">{t("trade.dataAge")}</p>
                    <p className="num text-sm">
                      <AgeChip ms={r.data_age_ms} />
                    </p>
                  </div>
                </div>
                {perp && (
                  <div className="grid grid-cols-3 gap-2 rounded border border-violet-400/25 bg-violet-400/5 p-2">
                    <div>
                      <p className="text-[10px] text-term-dim">{t("trade.marginReq")}</p>
                      <p className="num text-sm text-violet-300">{fmtUsd(r.margin_required_usd)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-term-dim">{t("trade.fundingRateLabel")}</p>
                      <p className="num text-sm text-zinc-200">
                        {r.funding_rate !== null ? `${(r.funding_rate * 100).toFixed(4)}%` : "—"}
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] text-term-dim">{t("trade.liqDistEst")}</p>
                      <p className="num text-sm text-down">≈{r.liquidation_distance_pct}%</p>
                    </div>
                  </div>
                )}
                <div className="flex items-center justify-between pt-1">
                  <p className="text-[10px] text-term-dim">
                    {t("trade.basisNote")}: {t(BASIS_LABEL[r.comparison_basis] ?? r.comparison_basis)} · {t("trade.quoteTtl")}
                    {quote.expires_at} UTC
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={cancel}
                      className="rounded border border-term-border px-3 py-1.5 text-xs text-term-muted hover:text-down"
                    >
                      {t("trade.cancelQuote")}
                    </button>
                    <button
                      onClick={confirm}
                      disabled={loading || expired}
                      className="rounded bg-up px-4 py-1.5 text-xs font-semibold text-black transition hover:brightness-110 disabled:opacity-40"
                    >
                      {loading ? t("trade.executing") : `${t("trade.confirmExec")} · ${quote.asset}`}
                    </button>
                  </div>
                </div>
              </div>
            );
          })()}
        </Panel>
      )}

      {/* 4. 分阶段完成状态 */}
      {result && (
        <Panel title="Execution Status" right={<Badge tone="ai">PAPER SIMULATED</Badge>}>
          <div className="flex flex-wrap items-center gap-2">
            {(result.execution_stages ?? []).map((s, i) => (
              <span key={s.stage} className="flex items-center gap-2">
                <span className="flex items-center gap-1 rounded border border-up/30 bg-up/10 px-2 py-1 text-[11px] text-up">
                  <span className="h-1.5 w-1.5 rounded-full bg-up" />
                  {STAGE_LABEL[s.stage] ? t(STAGE_LABEL[s.stage]) : s.label}
                  {s.simulated && <span className="text-[9px] text-up/60">sim</span>}
                </span>
                {i < (result.execution_stages?.length ?? 0) - 1 && (
                  <span className="text-term-dim">→</span>
                )}
              </span>
            ))}
          </div>
          <div className="mt-3 space-y-1 text-xs text-zinc-200">
            <p>
              {t("trade.statusLabel")}<span className="text-up">{result.status}</span> · {result.selected_route.venue} @{" "}
              <span className="num">{result.selected_route.price}</span> · {t("trade.costLabel")}{" "}
              <span className="num">{fmtUsd(result.selected_route.total_cost_usd)}</span>
              {result.leverage != null && result.leverage > 1 && (
                <>
                  {" "}· {t("trade.leverageLabel")}{" "}
                  <span className="num text-ai">{result.leverage}x</span>
                </>
              )}
            </p>
            {result.idempotent_replay && (
              <p className="text-term-dim">{t("trade.idemReplay")}</p>
            )}
          </div>
        </Panel>
      )}

      {/* 5. 回放与反事实 */}
      {replay && (
        <Panel title="Replay & Counterfactual" subtitle={t("trade.replaySubtitle")}>
          <div className="space-y-1 text-xs text-zinc-200">
            <p>
              {t("trade.actualFill")}<span className="text-up">{replay.actual?.status}</span>
              {replay.actual?.filled?.price !== undefined && (
                <span className="num ml-2">
                  @{String(replay.actual.filled.price)} · receive {String(replay.actual.filled.receive)}
                </span>
              )}
            </p>
            <p className="text-term-dim">
              {t("trade.quoteAt")} {replay.created_at}{t("trade.snapshotRoutes").replace("{n}", String(replay.snapshot_routes.length))}{" "}
              {replay.selected_venue}
            </p>
          </div>
          {replay.counterfactual.length > 0 && (
            <div className="mt-3 space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-term-dim">
                {t("trade.counterfactual")}
              </p>
              {replay.counterfactual.map((cf) => (
                <div
                  key={cf.venue}
                  className="flex items-center justify-between rounded border border-term-border bg-term-panel2 px-2 py-1.5 text-xs"
                >
                  <span className="text-zinc-200">{cf.venue}</span>
                  <span className={cf.would_be_better ? "text-up" : "text-term-muted"}>
                    {cf.diff_pct > 0 ? t("trade.more") : t("trade.less")}
                    {Math.abs(cf.diff_pct).toFixed(3)}%
                    {cf.would_be_better && <span className="ml-1 text-[10px] text-up">{t("trade.better")}</span>}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      )}

      <OrderPanel />
    </div>
  );
}

export default function TradePage() {
  return (
    <div className="space-y-4">
      <AccountCard />
      <Suspense>
        <TradeInner />
      </Suspense>
    </div>
  );
}
