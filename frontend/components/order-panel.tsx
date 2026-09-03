"use client";

import { useCallback, useEffect, useState } from "react";
import {
  cancelOrder,
  createOrder,
  listOrders,
  listPositions,
  type PaperOrder,
  type PaperPosition,
} from "@/lib/api";
import { Badge, Empty, ErrorPanel, Panel } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

const LEVERAGES = [1, 2, 5, 10, 20];
const OTYPES = [
  { key: "limit", label: "order.limitFull" },
  { key: "tp", label: "order.tpFull" },
  { key: "sl", label: "order.slFull" },
] as const;

const OTYPE_LABEL: Record<string, string> = {
  market: "order.market",
  limit: "order.limit",
  tp: "order.tp",
  sl: "order.sl",
};

export function OrderPanel() {
  const { t: t2 } = useI18n();
  const [marketType, setMarketType] = useState<"spot" | "perp">("spot");
  const [orderType, setOrderType] = useState<"limit" | "tp" | "sl">("limit");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [asset, setAsset] = useState("BTC");
  const [amount, setAmount] = useState("500");
  const [price, setPrice] = useState("");
  const [leverage, setLeverage] = useState(1);
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [positions, setPositions] = useState<PaperPosition[]>([]);
  const [selectedPos, setSelectedPos] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  const isProtect = orderType === "tp" || orderType === "sl";
  const pos = positions.find((p) => p.position_id === selectedPos) ?? null;
  // P0-3：保护单方向由仓位决定（多仓 → sell 平多，空仓 → buy 平空）
  const protectSide = pos ? (pos.side === "long" ? "sell" : "buy") : null;

  const refresh = useCallback(() => {
    listOrders("all")
      .then(setOrders)
      .catch(() => undefined);
    listPositions("open")
      .then(setPositions)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 5000);
    return () => clearInterval(t);
  }, [refresh]);

  const pickPosition = (id: string) => {
    setSelectedPos(id);
    const p = positions.find((x) => x.position_id === id);
    if (p) {
      setAsset(p.asset);
      setLeverage(p.leverage);
      // 默认金额 = 仓位名义的一半（可在 ≤ 上限内调整）
      setAmount(String(Math.max(1, Math.floor(Number(p.notional_usd) / 2))));
    }
  };

  const submit = () => {
    setLoading(true);
    setError(null);
    setOkMsg(null);
    createOrder({
      side: isProtect ? (protectSide ?? side) : side,
      asset,
      order_type: orderType,
      amount_usd: amount,
      market_type: isProtect ? "perp" : marketType,
      limit_price: price || null,
      leverage,
      linked_position_id: isProtect ? selectedPos : null,
    })
      .then((o) => {
        setOkMsg(
          o.status === "filled"
            ? t2("order.marketFilled").replace("{s}", o.side).replace("{q}", String(o.quantity)).replace("{a}", o.asset).replace("{p}", String(o.fill_price))
            : t2("order.orderPlaced").replace("{t}", t2(OTYPE_LABEL[o.order_type])).replace("{s}", o.side).replace("{q}", String(o.quantity)).replace("{a}", o.asset).replace("{p}", String(o.limit_price)),
        );
        refresh();
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const cancel = (id: string) =>
    cancelOrder(id)
      .then(refresh)
      .catch((e: Error) => setError(e.message));

  const posNotional = pos ? Number(pos.notional_usd) : 0;
  const valid =
    asset &&
    Number(amount) > 0 &&
    (orderType === "limit" || isProtect ? Number(price) > 0 : true) &&
    (!isProtect || (pos && Number(amount) <= posNotional));

  const inputCls =
    "num w-full border border-term-border bg-term-panel2 px-2 py-1.5 text-sm text-zinc-200 outline-none placeholder:text-term-dim focus:border-accent/50";
  const label = "text-[10px] uppercase tracking-wider text-term-dim";
  const tab = (active: boolean) =>
    `px-3 py-1.5 text-xs font-medium ${active ? "bg-term-panel2 text-zinc-100" : "text-term-muted hover:text-zinc-300"}`;

  return (
    <div className="space-y-3">
      <Panel title="Advanced Orders" subtitle={t2("order.subtitle")}>
        {/* 市场类型 + 订单类型 */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="flex border border-term-border">
            <button
              onClick={() => {
                setMarketType("spot");
                if (isProtect) setOrderType("limit");
              }}
              className={tab(marketType === "spot" && !isProtect)}
            >
              {t2("order.spot")}
            </button>
            <button onClick={() => setMarketType("perp")} className={tab(marketType === "perp" || isProtect)}>
              {t2("order.perp")}
            </button>
            <button disabled className="px-3 py-1.5 text-xs text-term-dim" title={t2("order.optionsTip")}>
              {t2("order.optionsNA")}
            </button>
          </div>
          <div className="flex border border-term-border">
            {OTYPES.map((t) => (
              <button
                key={t.key}
                onClick={() => {
                  setOrderType(t.key);
                  if (t.key !== "limit") setMarketType("perp");
                }}
                className={tab(orderType === t.key)}
              >
                {t2(t.label)}
              </button>
            ))}
          </div>
        </div>

        {/* P0-3：止盈/止损必须归属开放仓位 */}
        {isProtect ? (
          <div className="mb-3 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className={label}>{t2("order.linkedPos")}</span>
              {positions.length === 0 ? (
                <span className="text-[11px] text-down">
                  {t2("order.noPosition")}
                </span>
              ) : (
                <select
                  value={selectedPos}
                  onChange={(e) => pickPosition(e.target.value)}
                  className="num border border-term-border bg-term-panel2 px-2 py-1.5 text-xs text-zinc-200 outline-none"
                >
                  <option value="">{t2("order.pickPos")}</option>
                  {positions.map((p) => (
                    <option key={p.position_id} value={p.position_id}>
                      {p.asset} {p.side === "long" ? t2("order.longSide") : t2("order.shortSide")} {Number(p.quantity).toPrecision(6)} @{" "}
                      {p.entry_price} {p.leverage}x{t2("order.notional").replace("${n}", Number(p.notional_usd).toFixed(0))}
                    </option>
                  ))}
                </select>
              )}
              {pos && (
                <span className="text-[11px] text-term-muted">
                  {t2("order.autoSide")}{" "}
                  <b className={protectSide === "sell" ? "text-down" : "text-up"}>
                    {protectSide === "sell" ? t2("order.closeLong") : t2("order.closeShort")}
                  </b>{" "}
                  {t2("order.reduceOnlyMax").replace("{n}", posNotional.toFixed(2))}
                </span>
              )}
            </div>
          </div>
        ) : null}

        {/* 方向 */}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {!isProtect && (
            <div className="flex border border-term-border">
              {(["buy", "sell"] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setSide(s)}
                  className={`px-4 py-2 text-xs font-semibold uppercase ${
                    side === s
                      ? s === "buy"
                        ? "bg-up/15 text-up"
                        : "bg-down/15 text-down"
                      : "text-term-muted hover:text-zinc-200"
                  }`}
                >
                  {marketType === "perp" ? (s === "buy" ? t2("order.long") : t2("order.short")) : s === "buy" ? t2("order.buyIn") : t2("order.sellOut")}
                </button>
              ))}
            </div>
          )}
          <input
            value={asset}
            onChange={(e) => setAsset(e.target.value.toUpperCase())}
            placeholder="ASSET"
            disabled={isProtect}
            className={`num w-28 border border-term-border bg-term-panel2 px-2 py-2 text-sm uppercase text-zinc-200 outline-none placeholder:text-term-dim focus:border-accent/50 ${
              isProtect ? "opacity-60" : ""
            }`}
          />
          <div className="flex items-center gap-1">
            <span className={label}>{t2("order.amountUsd")}</span>
            <input value={amount} onChange={(e) => setAmount(e.target.value)} inputMode="decimal" className={`${inputCls} w-24`} />
          </div>
          <div className="flex items-center gap-1">
            <span className={label}>{isProtect ? t2("order.triggerPrice") : `${t2(OTYPE_LABEL[orderType])} ${t2("order.priceLabel")}`}</span>
            <input
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              inputMode="decimal"
              placeholder={`${t2(OTYPE_LABEL[orderType])} ${t2("order.priceLabel")}`}
              className={`${inputCls} w-28`}
            />
          </div>
          {marketType === "perp" && !isProtect && (
            <div className="flex items-center gap-1">
              <span className={label}>{t2("order.leverage")}</span>
              {LEVERAGES.map((l) => (
                <button
                  key={l}
                  onClick={() => setLeverage(l)}
                  className={`rounded px-1.5 py-1 text-[10px] ${
                    leverage === l ? "bg-accent/15 text-accent" : "text-term-muted hover:text-zinc-300"
                  }`}
                >
                  {l}x
                </button>
              ))}
            </div>
          )}
          <button onClick={submit} disabled={loading || !valid} className="btn-primary px-5 py-2 text-xs">
            {loading ? "…" : t2("order.submit").replace("{t}", t2(OTYPE_LABEL[orderType]))}
          </button>
        </div>

        <p className="text-[10px] leading-relaxed text-term-dim">
          {marketType === "perp" && !isProtect
            ? t2("order.perpNote").replace("{n}", String(leverage))
            : ""}
          {isProtect ? t2("order.protectNote") : ""}{" "}
          {t2("order.paperNote")}
        </p>

        {error && <div className="mt-2"><ErrorPanel message={error} /></div>}
        {okMsg && (
          <p className="mt-2 rounded border border-up/30 bg-up/10 px-2 py-1.5 text-[11px] text-up">{okMsg}</p>
        )}
      </Panel>

      <Panel
        title="Positions"
        subtitle={`${t2("order.positionsTitle")} ${positions.length}`}
        right={<Badge tone="ai">Paper</Badge>}
        bodyClass="p-0"
      >
        {positions.length === 0 ? (
          <Empty text={t2("order.positionsEmpty")} />
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-term-border text-left text-[10px] uppercase tracking-wider text-term-dim">
                <th className="px-3 py-1.5">{t2("order.colAsset")}</th>
                <th className="px-3 py-1.5">{t2("order.colSide")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colQty")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colEntry")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colMark")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colLeverage")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colMargin")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colPnl")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colLiq")}</th>
                <th className="px-3 py-1.5">{t2("order.colAction")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-term-border/60">
              {positions.map((p) => (
                <tr key={p.position_id} className="tbl-row">
                  <td className="num px-3 py-1.5 font-medium text-zinc-200">{p.asset}</td>
                  <td className={`px-3 py-1.5 font-medium ${p.side === "long" ? "text-up" : "text-down"}`}>
                    {p.side === "long" ? t2("order.long") : t2("order.short")}
                  </td>
                  <td className="num px-3 py-1.5 text-right text-zinc-200">{Number(p.quantity).toPrecision(6)}</td>
                  <td className="num px-3 py-1.5 text-right text-zinc-200">{p.entry_price}</td>
                  <td className="num px-3 py-1.5 text-right text-term-muted">{p.current_price ?? "—"}</td>
                  <td className="num px-3 py-1.5 text-right text-term-muted">{p.leverage}x</td>
                  <td className="num px-3 py-1.5 text-right text-zinc-200">{Number(p.margin_usd).toFixed(2)}</td>
                  <td className="num px-3 py-1.5 text-right">
                    {p.unrealized_pnl_usd ? (
                      <span className={Number(p.unrealized_pnl_usd) >= 0 ? "text-up" : "text-down"}>
                        {Number(p.unrealized_pnl_usd) >= 0 ? "+" : ""}
                        {Number(p.unrealized_pnl_usd).toFixed(2)}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="num px-3 py-1.5 text-right text-term-dim" title={t2("order.liqTip")}>
                    {p.liquidation_estimate ?? "—"}
                  </td>
                  <td className="px-3 py-1.5">
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          setOrderType("tp");
                          pickPosition(p.position_id);
                        }}
                        className="text-[11px] text-up underline"
                      >
                        {t2("order.tpBtn")}
                      </button>
                      <button
                        onClick={() => {
                          setOrderType("sl");
                          pickPosition(p.position_id);
                        }}
                        className="text-[11px] text-down underline"
                      >
                        {t2("order.slBtn")}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel
        title="Orders"
        subtitle={`${t2("order.ordersTitle")} ${orders.length}`}
        right={<Badge tone="ai">Paper</Badge>}
        bodyClass="p-0"
      >
        {orders.length === 0 ? (
          <Empty text={t2("order.ordersEmpty")} />
        ) : (
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-term-border text-left text-[10px] uppercase tracking-wider text-term-dim">
                <th className="px-3 py-1.5">{t2("order.colTime")}</th>
                <th className="px-3 py-1.5">{t2("order.colMarket")}</th>
                <th className="px-3 py-1.5">{t2("order.colType")}</th>
                <th className="px-3 py-1.5">{t2("order.colSide")}</th>
                <th className="px-3 py-1.5">{t2("order.colAsset")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colQty")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colTriggerFill")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colLeverage")}</th>
                <th className="px-3 py-1.5 text-right">{t2("order.colPnl")}</th>
                <th className="px-3 py-1.5">{t2("order.colStatus")}</th>
                <th className="px-3 py-1.5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-term-border/60">
              {orders.map((o) => (
                <tr key={o.order_id} className="tbl-row">
                  <td className="px-3 py-1.5 text-term-dim">{o.ts.slice(11, 19)}</td>
                  <td className="px-3 py-1.5 text-term-muted">{o.market_type === "perp" ? t2("order.perpM") : t2("order.spotM")}</td>
                  <td className="px-3 py-1.5 text-zinc-200">
                    {OTYPE_LABEL[o.order_type]}
                    {o.reduce_only && <span className="ml-1 text-[10px] text-accent">reduce-only</span>}
                  </td>
                  <td className={`px-3 py-1.5 font-medium ${o.side === "buy" ? "text-up" : "text-down"}`}>
                    {o.market_type === "perp" ? (o.side === "buy" ? t2("order.longSide") : t2("order.shortSide")) : o.side === "buy" ? t2("order.buyIn") : t2("order.sellOut")}
                  </td>
                  <td className="num px-3 py-1.5 text-zinc-200">{o.asset}</td>
                  <td className="num px-3 py-1.5 text-right text-zinc-200">{Number(o.quantity).toPrecision(6)}</td>
                  <td className="num px-3 py-1.5 text-right text-zinc-200">
                    {o.fill_price ?? o.limit_price ?? "—"}
                  </td>
                  <td className="num px-3 py-1.5 text-right text-term-muted">{o.leverage}x</td>
                  <td className="num px-3 py-1.5 text-right">
                    {o.unrealized_pnl_usd ? (
                      <span className={Number(o.unrealized_pnl_usd) >= 0 ? "text-up" : "text-down"}>
                        {Number(o.unrealized_pnl_usd) >= 0 ? "+" : ""}
                        {Number(o.unrealized_pnl_usd).toFixed(2)}
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-3 py-1.5">
                    <Badge tone={o.status === "filled" ? "up" : o.status === "cancelled" ? "flat" : "accent"}>
                      {o.status === "filled" ? t2("order.filled") : o.status === "cancelled" ? t2("order.cancelled") : t2("order.pending")}
                    </Badge>
                  </td>
                  <td className="px-3 py-1.5 text-right">
                    {o.status === "pending" && (
                      <button onClick={() => cancel(o.order_id)} className="text-[11px] text-term-muted underline hover:text-down">
                        {t2("order.cancel")}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
