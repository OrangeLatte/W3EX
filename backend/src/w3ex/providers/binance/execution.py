"""Binance CEX 执行通道：真实 bookTicker + 深度推演滑点，paper 成交。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from w3ex.core.schemas import ExecutionQuoteResult, ExecutionRoute
from w3ex.providers.base import ExecutionProvider, ProviderUnavailable
from w3ex.providers.binance.market import SPOT, STABLES
from w3ex.providers.http import fetch_json

TAKER_FEE_RATE = 0.001  # 现货 taker 0.1%


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def depth_walk(symbol: str, side: str, fiat_amount: float) -> dict:
    """沿订单簿推演 $N 市价单的平均成交价与滑点。"""
    data = await fetch_json(f"{SPOT}/depth", params={"symbol": f"{symbol}USDT", "limit": 50}, ttl=3)
    levels = data["asks"] if side == "buy" else data["bids"]
    remaining = fiat_amount
    filled_qty = 0.0
    filled_usd = 0.0
    for price_s, qty_s in levels:
        price, qty = float(price_s), float(qty_s)
        level_usd = price * qty
        take_usd = min(remaining, level_usd)
        filled_usd += take_usd
        filled_qty += take_usd / price
        remaining -= take_usd
        if remaining <= 0:
            break
    if filled_usd <= 0:
        raise ProviderUnavailable(f"深度不足: {symbol}")
    avg_price = filled_usd / filled_qty
    # 未吃满深度视为不可执行，交给回退链
    if remaining > fiat_amount * 0.01:
        raise ProviderUnavailable(f"{symbol} 深度不足以吃单 ${fiat_amount:,.0f}")
    return {"avg_price": avg_price, "filled_qty": filled_qty, "filled_usd": filled_usd}


class BinanceExecutionProvider(ExecutionProvider):
    name = "binance"
    venue_prefix = "binance"

    async def get_quote(
        self,
        side: str,
        asset: str,
        fiat_amount: Decimal,
        fiat_currency: str = "USD",
        market_type: str = "spot",
        constraints: dict[str, int] | None = None,
    ) -> ExecutionQuoteResult:
        symbol = asset.upper()
        if market_type != "spot":
            raise ProviderUnavailable("binance_cex 仅提供现货报价")
        if symbol in STABLES:
            raise ProviderUnavailable("稳定币兑换请使用 DEX 通道")
        book = await fetch_json(
            f"{SPOT}/ticker/bookTicker", params={"symbol": f"{symbol}USDT"}, ttl=3
        )
        mid = (float(book["bidPrice"]) + float(book["askPrice"])) / 2
        walk = await depth_walk(symbol, side, float(fiat_amount))
        avg_price = walk["avg_price"]
        slip = abs(avg_price - mid) / mid * 100
        fees = float(fiat_amount) * TAKER_FEE_RATE
        if side == "buy":
            receive = walk["filled_qty"] * (1 - TAKER_FEE_RATE)
            total_cost = float(fiat_amount) + fees
        else:
            receive = walk["filled_usd"] * (1 - TAKER_FEE_RATE)
            total_cost = fees
        route = ExecutionRoute(
            venue="binance_cex",
            kind="cex",
            price=Decimal(str(round(avg_price, 8))),
            slippage_pct=round(slip, 4),
            fees_usd=Decimal(str(round(fees, 2))),
            gas_usd=Decimal("0"),
            total_cost_usd=Decimal(str(round(total_cost, 2))),
            estimated_receive=Decimal(str(round(receive, 8))),
            confidence=0.99,
            notes=["真实订单簿深度推演", "taker 手续费 0.1%", "无链上 Gas"],
        )
        return ExecutionQuoteResult(
            side=side,
            asset_symbol=symbol,
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            routes=[route],
            best_route_index=0,
            expires_in_seconds=30,
            ts=_now(),
        )
