"""Binance 公开行情 Provider（无需 API Key）。

现货: 默认走官方公开行情镜像 data-api.binance.vision（与 api.binance.com 同一套
/api/v3 行情端点，部分网络环境下可达性更好），可用 W3EX_BINANCE_SPOT_BASE 覆盖。
合约: https://fapi.binance.com/fapi/v1 （仅读 funding / 标记价；不可达时由上层回退）
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from w3ex.core.schemas import Candle, LiquidationEvent, MarketRegime, PriceQuote, Ticker
from w3ex.providers.base import MarketDataProvider, ProviderUnavailable
from w3ex.providers.http import fetch_json

SPOT = os.environ.get("W3EX_BINANCE_SPOT_BASE", "https://data-api.binance.vision/api/v3")
FAPI = os.environ.get("W3EX_BINANCE_FAPI_BASE", "https://fapi.binance.com/fapi/v1")

# 稳定币对稳定币在 Binance 无可靠 USD 计价对，交给上层回退
STABLES = {"USDT", "USDC", "DAI", "FDUSD"}


def binance_symbol(asset: str) -> str:
    return f"{asset.upper()}USDT"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


class BinanceMarketProvider(MarketDataProvider):
    name = "binance"

    async def get_price(self, asset: str) -> PriceQuote:
        symbol = asset.upper()
        if symbol in STABLES:
            raise ProviderUnavailable(f"binance 不提供 {symbol} 的 USD 计价对")
        data = await fetch_json(
            f"{SPOT}/ticker/24hr", params={"symbol": binance_symbol(symbol)}, ttl=5
        )
        return PriceQuote(
            symbol=symbol,
            price=_dec(data["lastPrice"]),
            bid=_dec(data["bidPrice"]),
            ask=_dec(data["askPrice"]),
            volume_24h=_dec(data["quoteVolume"]),
            change_24h_pct=float(data["priceChangePercent"]),
            ts=_now(),
        )

    async def get_candles(self, asset: str, interval: str = "1h", limit: int = 100) -> list[Candle]:
        symbol = asset.upper()
        if symbol in STABLES:
            raise ProviderUnavailable(f"binance 不提供 {symbol} 的 USD 计价对")
        rows = await fetch_json(
            f"{SPOT}/klines",
            params={"symbol": binance_symbol(symbol), "interval": interval, "limit": limit},
            ttl=15,
        )
        out: list[Candle] = []
        for r in rows:
            out.append(
                Candle(
                    symbol=symbol,
                    ts=datetime.fromtimestamp(r[0] / 1000, tz=UTC).replace(tzinfo=None),
                    open=_dec(r[1]),
                    high=_dec(r[2]),
                    low=_dec(r[3]),
                    close=_dec(r[4]),
                    volume=_dec(r[5]),
                )
            )
        return out

    async def get_tickers(self, assets: list[str] | None = None) -> list[Ticker]:
        if assets:
            symbols = [binance_symbol(a) for a in assets if a.upper() not in STABLES]
            if not symbols:
                raise ProviderUnavailable("binance tickers: 空资产列表")
            data = await fetch_json(
                f"{SPOT}/ticker/24hr",
                params={"symbols": f"[{','.join(symbols)}]"},
                ttl=8,
                cache_key=f"binance:tickers:{','.join(symbols)}",
            )
        else:
            data = await fetch_json(f"{SPOT}/ticker/24hr", ttl=8)
        out: list[Ticker] = []
        for d in data:
            out.append(
                Ticker(
                    symbol=d["symbol"].removesuffix("USDT"),
                    last=_dec(d["lastPrice"]),
                    bid=_dec(d.get("bidPrice") or d["lastPrice"]),
                    ask=_dec(d.get("askPrice") or d["lastPrice"]),
                    high_24h=_dec(d["highPrice"]),
                    low_24h=_dec(d["lowPrice"]),
                    volume_24h=_dec(d["quoteVolume"]),
                    change_24h_pct=float(d["priceChangePercent"]),
                    funding_rate=None,
                    ts=_now(),
                )
            )
        return out

    async def get_funding(self, asset: str) -> float | None:
        symbol = asset.upper()
        if symbol in STABLES:
            raise ProviderUnavailable(f"binance 合约无 {symbol} 资金费率")
        data = await fetch_json(
            f"{FAPI}/premiumIndex", params={"symbol": binance_symbol(symbol)}, ttl=30
        )
        return float(data["lastFundingRate"])

    async def get_funding_summary(self, limit: int = 15) -> list[dict] | None:
        rows = await fetch_json(f"{FAPI}/premiumIndex", ttl=30)
        majors = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
        parsed = [
            {
                "symbol": r["symbol"].removesuffix("USDT"),
                "rate": float(r["lastFundingRate"]),
                "mark_price": float(r["markPrice"]),
                "ts": datetime.fromtimestamp(r["time"] / 1000, tz=UTC)
                .replace(tzinfo=None)
                .isoformat(),
            }
            for r in rows
            if r["symbol"].endswith("USDT")
        ]
        parsed.sort(key=lambda x: abs(x["rate"]), reverse=True)
        head = [p for p in parsed if f"{p['symbol']}USDT" in majors]
        rest = [p for p in parsed if f"{p['symbol']}USDT" not in majors]
        return (head + rest)[:limit]

    async def get_liquidations(self, hours: int = 24) -> list[LiquidationEvent]:
        # Binance 公开端点不提供历史强平数据，交给组合层回退（mock 兜底）
        raise ProviderUnavailable("binance 无公开强平历史端点")

    async def get_market_regime(self) -> MarketRegime:
        data = await fetch_json(
            f"{SPOT}/ticker/24hr",
            params={"symbols": '["BTCUSDT","ETHUSDT","SOLUSDT"]'},
            ttl=10,
            cache_key="binance:regime:tickers",
        )
        changes = {d["symbol"].removesuffix("USDT"): float(d["priceChangePercent"]) for d in data}
        btc, eth, sol = changes.get("BTC", 0.0), changes.get("ETH", 0.0), changes.get("SOL", 0.0)
        score = max(-100.0, min(100.0, btc * 5 + eth * 3 + sol * 2))
        if score >= 20:
            regime, label = "risk_on", "Risk-On: 主要资产普涨，风险偏好回升"
        elif score <= -20:
            regime, label = "risk_off", "Risk-Off: 主要资产走弱，避险情绪主导"
        else:
            regime, label = "neutral", "Neutral: 市场方向不明确"
        return MarketRegime(
            regime=regime,
            score=round(score, 2),
            btc_change_24h_pct=btc,
            eth_change_24h_pct=eth,
            sol_change_24h_pct=sol,
            label=label,
            drivers=[f"BTC {btc:+.2f}%", f"ETH {eth:+.2f}%", f"SOL {sol:+.2f}%"],
        )

    async def get_depth(self, asset: str, limit: int = 20) -> dict | None:
        symbol = asset.upper()
        if symbol in STABLES:
            raise ProviderUnavailable(f"binance 不提供 {symbol} 的 USD 计价对")
        data = await fetch_json(
            f"{SPOT}/depth", params={"symbol": binance_symbol(symbol), "limit": limit}, ttl=3
        )
        return {
            "bids": [[float(p), float(q)] for p, q in data["bids"]],
            "asks": [[float(p), float(q)] for p, q in data["asks"]],
            "ts": _now().isoformat(),
            "source": "binance",
        }

    async def book_ticker(self, asset: str) -> dict:
        """最优买卖价：供执行层计算真实成交价。"""
        symbol = asset.upper()
        if symbol in STABLES:
            raise ProviderUnavailable(f"binance 不提供 {symbol} 的 USD 计价对")
        data = await fetch_json(
            f"{SPOT}/ticker/bookTicker", params={"symbol": binance_symbol(symbol)}, ttl=3
        )
        return {
            "bid": float(data["bidPrice"]),
            "bid_qty": float(data["bidQty"]),
            "ask": float(data["askPrice"]),
            "ask_qty": float(data["askQty"]),
        }
