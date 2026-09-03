from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from w3ex.api.deps import DatasetDep, ProvidersDep
from w3ex.intelligence.market import build_market_overview

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/overview")
async def market_overview(providers: ProvidersDep, ds: DatasetDep) -> dict:
    try:
        return await build_market_overview(providers.market, ds)
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_error", "message": "上游数据源暂不可用，请稍后重试"},
        ) from exc


@router.get("/tickers")
async def tickers(
    providers: ProvidersDep,
    assets: str | None = Query(default=None, description="逗号分隔 symbol，缺省返回全部"),
    response: Response = None,  # type: ignore[assignment]
) -> list[dict]:
    symbol_list = [s.strip().upper() for s in assets.split(",")] if assets else None
    try:
        tickers = await providers.market.get_tickers(symbol_list)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_error", "message": "上游数据源暂不可用，请稍后重试"},
        ) from exc
    # 评审 PDF P0 数据可信度：来源标注（真实源名 / mock）
    tick_source = getattr(providers.market, "tick_source", None)
    if tick_source:
        response.headers["X-Data-Source"] = tick_source
    else:
        response.headers["X-Data-Source"] = "mock"
        response.headers["X-Data-Quality"] = "simulated"
    return [
        {
            "symbol": t.symbol,
            "price": float(t.last),
            "change_24h_pct": round(t.change_24h_pct, 2),
            "volume_24h_usd": float(t.volume_24h),
            "high_24h": float(t.high_24h),
            "low_24h": float(t.low_24h),
        }
        for t in tickers
    ]


@router.get("/klines/{symbol}")
async def klines(
    symbol: str,
    providers: ProvidersDep,
    interval: str = Query(default="1h", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    limit: int = Query(default=168, ge=10, le=500),
) -> list[dict]:
    try:
        candles = await providers.market.get_candles(symbol.upper(), interval=interval, limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_error", "message": "上游数据源暂不可用，请稍后重试"},
        ) from exc
    return [
        {
            "ts": c.ts.isoformat(),
            "o": float(c.open),
            "h": float(c.high),
            "l": float(c.low),
            "c": float(c.close),
            "v": float(c.volume),
        }
        for c in candles
    ]


@router.get("/depth/{symbol}")
async def depth(
    symbol: str, providers: ProvidersDep, limit: int = Query(default=20, le=50)
) -> dict:
    try:
        snap = await providers.market.get_depth(symbol.upper(), limit=limit)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_error", "message": "上游数据源暂不可用，请稍后重试"},
        ) from exc
    if snap is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": f"{symbol} 无深度数据"}
        )
    return snap


@router.get("/funding")
async def funding(providers: ProvidersDep, limit: int = Query(default=15, le=50)) -> list[dict]:
    rows = await providers.market.get_funding_summary(limit=limit)
    return rows or []
