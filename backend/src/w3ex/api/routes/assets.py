from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from w3ex.api.deps import DatasetDep, ProvidersDep
from w3ex.intelligence.assets import build_asset_detail

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/{symbol}")
async def asset_detail(
    symbol: str,
    providers: ProvidersDep,
    ds: DatasetDep,
    interval: str = Query(default="1h", pattern="^(1m|5m|15m|1h|4h|1d)$"),
    response: Response = None,  # type: ignore[assignment]
) -> dict:
    try:
        detail = await build_asset_detail(symbol, providers.market, interval=interval, ds=ds)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "upstream_error", "message": "上游数据源暂不可用，请稍后重试"},
        ) from exc
    # 评审 PDF P0 数据可信度：行情来源标注
    src = (detail.get("sources") or {}).get("market") or "mock"
    response.headers["X-Data-Source"] = str(src)
    if "mock" in str(src):
        response.headers["X-Data-Quality"] = "simulated"
    return detail
