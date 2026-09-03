"""Jupiter DEX 聚合通道：真实聚合报价（Solana 生态资产），paper 成交。"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from w3ex.core.schemas import ExecutionQuoteResult, ExecutionRoute
from w3ex.providers.base import ExecutionProvider, ProviderUnavailable
from w3ex.providers.http import fetch_json

QUOTE_URL = "https://quote-api.jup.ag/v6/quote"

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"

# symbol → (mint, decimals)
SOLANA_MINTS: dict[str, tuple[str, int]] = {
    "SOL": ("So11111111111111111111111111111111111111112", 9),
    "USDC": (USDC, 6),
    "USDT": (USDT, 6),
    "JUP": ("JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 6),
    "BONK": ("DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", 5),
    "WIF": ("EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 6),
    "JTO": ("jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL", 9),
    "PYTH": ("HZ1JogNi34yYBMn3ZQkWvvpL3NzcubkqwzS4TbKQDkUT", 6),
    "RAY": ("4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", 6),
    "JLP": ("27G8MtK7VtTcCHkpASjSDdkWWYfoqT6ggEuKidVJidD4", 6),
}

STABLES = {"USDT", "USDC", "DAI"}
FEE_EST_RATE = 0.0004  # 路由 LP fee 估算
GAS_EST_USD = 0.02


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class JupiterExecutionProvider(ExecutionProvider):
    name = "jupiter"
    venue_prefix = "jupiter"

    async def _binance_mid(self, symbol: str) -> float | None:
        """卖出时需要先估算资产数量；用 Binance 中间价（若不可达返回 None）。"""
        try:
            data = await fetch_json(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": f"{symbol}USDT"},
                ttl=5,
                cacheable=True,
            )
            return float(data["price"])
        except Exception:
            return None

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
            raise ProviderUnavailable("jupiter 仅提供现货兑换报价")
        if symbol in STABLES or symbol not in SOLANA_MINTS:
            raise ProviderUnavailable(f"jupiter 不支持 {symbol}")
        mint, decimals = SOLANA_MINTS[symbol]
        amount = float(fiat_amount)

        if side == "buy":
            input_mint, output_mint = USDC, mint
            raw_amount = str(int(amount * 1e6))
        else:
            input_mint, output_mint = mint, USDC
            mid = await self._binance_mid(symbol)
            if mid is None or mid <= 0:
                raise ProviderUnavailable("卖出报价需要外部中间价估算数量")
            raw_amount = str(int(amount / mid * 10**decimals))

        data = await fetch_json(
            QUOTE_URL,
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": raw_amount,
                "slippageBps": "50",
                "restrictIntermediateTokens": "true",
            },
            ttl=5,
            cacheable=False,  # 报价必须实时
        )
        out_raw = float(data["outAmount"])
        out_qty = out_raw / 10**decimals
        in_qty = float(data["inAmount"]) / (1e6 if side == "buy" else 10**decimals)
        if in_qty <= 0 or out_qty <= 0:
            raise ProviderUnavailable("jupiter 报价数量异常")
        price = (float(fiat_amount) / out_qty) if side == "buy" else (out_qty / in_qty)
        slip_pct = float(data.get("priceImpactPct") or 0) * 100
        fees = amount * FEE_EST_RATE

        if side == "buy":
            receive = out_qty
            total_cost = amount + fees + GAS_EST_USD
        else:
            receive = out_qty - fees - GAS_EST_USD
            total_cost = fees + GAS_EST_USD

        route = ExecutionRoute(
            venue="jupiter_dex",
            kind="dex",
            price=Decimal(str(round(price, 8))),
            slippage_pct=round(max(slip_pct, 0.01), 4),
            fees_usd=Decimal(str(round(fees, 4))),
            gas_usd=Decimal(str(GAS_EST_USD)),
            total_cost_usd=Decimal(str(round(total_cost, 4))),
            estimated_receive=Decimal(str(round(receive, 8))),
            confidence=0.94,
            notes=[
                f"Jupiter 实时聚合报价（{data.get('routePlan', []).__len__()} 路由）",
                "链上 Gas 估算 ~$0.02（Solana）",
                "滑点容忍 50bps",
            ],
        )
        return ExecutionQuoteResult(
            side=side,
            asset_symbol=symbol,
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            routes=[route],
            best_route_index=0,
            expires_in_seconds=20,
            ts=_now(),
        )
