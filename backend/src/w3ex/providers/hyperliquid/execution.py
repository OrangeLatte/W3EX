"""Hyperliquid Perp 通道：公开 allMids 中间价，paper 成交（无 API Key）。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from w3ex.core.schemas import ExecutionQuoteResult, ExecutionRoute
from w3ex.providers.base import ExecutionProvider, ProviderUnavailable
from w3ex.providers.http import fetch_json

INFO_URL = "https://api.hyperliquid.xyz/info"

TAKER_FEE_RATE = 0.00045  # taker 0.045%
SLIP_EST_PCT = 0.05

STABLES = {"USDT", "USDC", "DAI"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def all_mids() -> dict[str, float]:
    data = await fetch_json(
        INFO_URL,
        method="POST",
        json_body={"type": "allMids"},
        ttl=5,
        cache_key="hyperliquid:allMids",
    )
    return {k: float(v) for k, v in data.items() if k not in ("dayNtlVlm", "ctx")}


class HyperliquidExecutionProvider(ExecutionProvider):
    name = "hyperliquid"
    venue_prefix = "hyperliquid"

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
        if market_type != "perp":
            raise ProviderUnavailable("hyperliquid 仅提供永续报价")
        if symbol in STABLES:
            raise ProviderUnavailable("hyperliquid 无稳定币中间价")
        mids = await all_mids()
        if symbol not in mids:
            raise ProviderUnavailable(f"hyperliquid 未上市 {symbol}")
        mid = mids[symbol]
        if mid <= 0:
            raise ProviderUnavailable(f"hyperliquid {symbol} 中间价异常")
        amount = float(fiat_amount)
        # 买入按 ask 方向偏移，卖出按 bid 方向偏移（估算）
        px = mid * (1 + SLIP_EST_PCT / 100) if side == "buy" else mid * (1 - SLIP_EST_PCT / 100)
        fees = amount * TAKER_FEE_RATE
        if side == "buy":
            receive = amount / px
            total_cost = amount + fees
        else:
            receive = amount * (1 - SLIP_EST_PCT / 100) - fees
            total_cost = fees
        route = ExecutionRoute(
            venue="hyperliquid_perp",
            kind="perp",
            price=Decimal(str(round(px, 8))),
            slippage_pct=SLIP_EST_PCT,
            fees_usd=Decimal(str(round(fees, 2))),
            gas_usd=Decimal("0"),
            total_cost_usd=Decimal(str(round(total_cost, 2))),
            estimated_receive=Decimal(str(round(receive, 8))),
            confidence=0.96,
            notes=[
                "真实中间价（Hyperliquid allMids）",
                "永续合约通道：支持做空与杠杆，注意资金费率与强平风险",
                "非现货交割，paper 模式按名义价值模拟",
            ],
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
