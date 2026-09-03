"""宏观经济模块：主要经济体指标 + 全球股指 + 大宗商品。

独立于加密行情链路（yahoo / worldbank），任一源失败优雅降级并标注。
Provider 无状态，数据缓存由 http.py TTLCache 统一承担。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from w3ex.api.deps import ProvidersDep
from w3ex.providers.worldbank.macro import WorldBankProvider
from w3ex.providers.yahoo.market import COMMODITY_SYMBOLS, INDEX_SYMBOLS, YahooProvider

router = APIRouter(prefix="/macro", tags=["macro"])

# symbol → yahoo_symbol 反查表（宏观标的 K 线与 AI 分析用）
SYMBOL_TO_YAHOO: dict[str, str] = {**INDEX_SYMBOLS, **COMMODITY_SYMBOLS}
YAHOO_TO_NAME: dict[str, str] = {v: k for k, v in SYMBOL_TO_YAHOO.items()}


@router.get("/overview")
async def macro_overview(providers: ProvidersDep) -> dict:
    yahoo, wb = YahooProvider(), WorldBankProvider()
    indices, commodities, macro = await asyncio.gather(
        yahoo.get_indices(),
        yahoo.get_commodities(),
        wb.get_macro_overview(),
        return_exceptions=True,
    )
    out_indices = None if isinstance(indices, BaseException) else indices
    out_commodities = None if isinstance(commodities, BaseException) else commodities
    out_macro = None if isinstance(macro, BaseException) else macro
    return {
        "indices": out_indices or [],
        "commodities": out_commodities or [],
        "macro": out_macro,
        "sources": {
            "indices": "yahoo" if out_indices else "unavailable",
            "commodities": "yahoo" if out_commodities else "unavailable",
            "macro": "worldbank" if out_macro else "unavailable",
        },
        "ts": datetime.now(UTC).isoformat(),
    }


MACRO_RANGES = {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"}


@router.get("/history/{symbol}")
async def macro_history(symbol: str, rng: str = "5y", interval: str = "1d") -> dict:
    """宏观标的（股指/商品）K 线，形状对齐 crypto candles 前端契约。

    默认 5y 长周期；指数类标的可用 max 跨几十年（yahoo range=max）。
    """
    if rng not in MACRO_RANGES:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "invalid_request",
                "message": f"range 须为 {sorted(MACRO_RANGES)} 之一",
            },
        )
    ys = SYMBOL_TO_YAHOO.get(symbol.upper())
    if ys is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": f"未知宏观标的：{symbol}"}
        )
    try:
        candles = await YahooProvider().get_ohlc(ys, rng, interval)
    except Exception as exc:  # noqa: BLE001 — 上游失败统一 503
        raise HTTPException(
            status_code=503,
            detail={"code": "upstream_unavailable", "message": "上游数据源暂不可用，请稍后重试"},
        ) from exc
    return {
        "symbol": symbol.upper(),
        "yahoo_symbol": ys,
        "range": rng,
        "interval": interval,
        "candles": candles,
    }


WB_COUNTRIES = {"USA", "CHN", "EMU", "JPN", "DEU", "GBR", "IND", "KOR"}


@router.get("/indicator/{iso3}/{indicator}")
async def macro_indicator(iso3: str, indicator: str) -> dict:
    """主要经济体单指标长时序（1960 起，可跨几十年），供前端点击展开。"""
    iso = iso3.upper()
    if iso not in WB_COUNTRIES:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": f"未知经济体：{iso3}"}
        )
    try:
        return await WorldBankProvider().get_indicator_series(iso, indicator)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_request", "message": str(exc)}
        ) from exc
    except Exception as exc:  # noqa: BLE001 — 上游失败统一 503
        raise HTTPException(
            status_code=503,
            detail={"code": "upstream_unavailable", "message": "上游数据源暂不可用，请稍后重试"},
        ) from exc
