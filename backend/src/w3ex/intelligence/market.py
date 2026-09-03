"""市场总览（纯行情，Signal > Data 原则保留但只面向交易）：

全局统计 → 体制 → 指数 → 涨跌榜/成交额榜 → 资金费率 → 强平。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from w3ex.providers.base import MarketDataProvider
from w3ex.providers.mock.generator import MockDataset

MAJORS = ["BTC", "ETH", "SOL"]


def _now() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _ticker_dict(t: Any) -> dict:
    return {
        "symbol": t.symbol,
        "price": float(t.last),
        "change_24h_pct": round(t.change_24h_pct, 2),
        "volume_24h_usd": float(t.volume_24h),
        "high_24h": float(t.high_24h),
        "low_24h": float(t.low_24h),
    }


async def build_market_overview(
    market: MarketDataProvider, ds: MockDataset | None = None
) -> dict[str, Any]:
    ds = ds or MockDataset()
    # Decision Workspace 性能项：五路独立数据源并行拉取（原串行 ≈ 各源 RTT 之和）
    tickers, regime, global_stats, funding, liquidations_raw = await asyncio.gather(
        market.get_tickers(),
        market.get_market_regime(),
        market.get_global_stats(),
        market.get_funding_summary(limit=15),
        market.get_liquidations(hours=24),
        return_exceptions=True,
    )
    if isinstance(tickers, BaseException) or not tickers:
        raise RuntimeError("行情数据暂不可用") from (
            tickers if isinstance(tickers, BaseException) else None
        )
    # composite.get_tickers 会记录本次真实服务源（mock 回退时为 None）
    tick_source: str | None = getattr(market, "tick_source", None) or (
        "mock" if market.name == "mock" else None
    )
    regime = None if isinstance(regime, BaseException) else regime
    global_stats = None if isinstance(global_stats, BaseException) else global_stats
    funding = None if isinstance(funding, BaseException) else funding
    liquidations_raw = [] if isinstance(liquidations_raw, BaseException) else liquidations_raw

    # 过滤稳定币与无效报价
    stables = {"USDT", "USDC", "DAI", "FDUSD"}
    tradables = [t for t in tickers if t.symbol not in stables and float(t.last) > 0]

    by_change = sorted(tradables, key=lambda t: t.change_24h_pct, reverse=True)
    by_volume = sorted(tradables, key=lambda t: float(t.volume_24h), reverse=True)

    indices: dict[str, float] = {}
    for sym in MAJORS:
        hit = next((t for t in tradables if t.symbol == sym), None)
        indices[sym] = round(hit.change_24h_pct, 2) if hit else 0.0

    liquidations = sorted(
        liquidations_raw,
        key=lambda x: float(x.amount_usd),
        reverse=True,
    )[:12]

    return {
        "as_of": _now(),
        "global_stats": global_stats,
        "regime": regime.model_dump(),
        "indices": indices,
        "gainers": [_ticker_dict(t) for t in by_change[:10]],
        "losers": [_ticker_dict(t) for t in reversed(by_change[-10:])],
        "volume_leaders": [_ticker_dict(t) for t in by_volume[:10]],
        "funding": funding or [],
        "liquidations": [
            {
                "symbol": liq.symbol,
                "side": liq.side,
                "amount_usd": str(liq.amount_usd),
                "price": str(liq.price),
                "ts": liq.ts.isoformat(),
            }
            for liq in liquidations
        ],
        "sources": {
            # Decision Workspace 透明性：tickers 由真实源服务才标源名，
            # mock 回退时显式标注，不得冒充真实源
            "market": tick_source
            or ("mock" if market.name == "mock" else "mock（上游不可用，模拟数据）"),
            "liquidations": "mock (公开源无强平历史，模拟数据)"
            if market.name != "mock"
            else "mock",
        },
    }
