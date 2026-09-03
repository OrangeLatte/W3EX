"""资产详情（纯行情视图）：价格 / K线 / 统计 / 资金费率 / 订单簿深度。"""

from __future__ import annotations

from typing import Any

from w3ex.providers.base import MarketDataProvider
from w3ex.providers.mock.generator import MockDataset


async def build_asset_detail(
    symbol: str,
    market: MarketDataProvider,
    interval: str = "1h",
    ds: MockDataset | None = None,
) -> dict[str, Any]:
    ds = ds or MockDataset()
    symbol = symbol.upper()

    quote = await market.get_price(symbol)
    candles = await market.get_candles(symbol, interval=interval, limit=168)
    meta = await market.get_asset_meta(symbol)
    funding = await market.get_funding(symbol)
    depth = await market.get_depth(symbol, limit=10)

    change_1h = None
    if len(candles) >= 2:
        prev, last = float(candles[-2].close), float(candles[-1].close)
        if prev > 0:
            change_1h = round((last / prev - 1) * 100, 2)

    return {
        "symbol": symbol,
        "name": (meta or {}).get("name") or symbol,
        "price": float(quote.price),
        "change_24h_pct": quote.change_24h_pct,
        "change_1h_pct": change_1h,
        "interval": interval,
        "candles": [
            {
                "ts": c.ts.isoformat(),
                "o": float(c.open),
                "h": float(c.high),
                "l": float(c.low),
                "c": float(c.close),
                "v": float(c.volume),
            }
            for c in candles
        ],
        "stats": {
            "market_cap": (meta or {}).get("market_cap"),
            "market_cap_rank": (meta or {}).get("market_cap_rank"),
            "volume_24h_usd": float(quote.volume_24h),
            "circulating_supply": (meta or {}).get("circulating_supply"),
            "high_24h": (meta or {}).get("high_24h"),
            "low_24h": (meta or {}).get("low_24h"),
        },
        "funding_rate": funding,
        "depth": depth,
        "sources": {
            "market": market.name,
            "meta": (meta or {}).get("source") or market.name,
        },
    }
