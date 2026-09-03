"""AI 模块：模型 API 绑定（自动识别模型/校验）+ Regime 简报 + 标的对话。"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from w3ex.api.deps import DBSession, ProvidersDep
from w3ex.api.routes.macro import SYMBOL_TO_YAHOO
from w3ex.db.models import AiBinding
from w3ex.intelligence.ai import (
    asset_chat,
    binding_status,
    client_from_binding,
    get_active_binding,
    regime_brief,
)
from w3ex.intelligence.assets import build_asset_detail
from w3ex.intelligence.market import build_market_overview
from w3ex.providers.llm.client import LLMClient

router = APIRouter(prefix="/ai", tags=["ai"])


# ---------- 绑定 ----------


class BindRequest(BaseModel):
    provider: str = Field(pattern="^(openai_compatible|anthropic)$")
    base_url: str = Field(min_length=8, max_length=255)
    api_key: str = Field(min_length=8, max_length=255)
    model: str | None = Field(default=None, max_length=96)
    label: str = Field(default="", max_length=64)


@router.get("/status")
async def status(session: DBSession) -> dict:
    return await binding_status(session)


@router.post("/bind")
async def bind(req: BindRequest, session: DBSession) -> dict:
    """绑定模型 API：自动识别模型列表并校验连通性，结果落库。"""
    client = LLMClient(req.provider, req.base_url, req.api_key, req.model)
    check = await client.validate()
    if not check["ok"]:
        raise HTTPException(
            status_code=422,
            detail={"code": "bind_failed", "message": f"绑定校验失败：{check['error']}"},
        )
    b = AiBinding(
        provider=req.provider,
        label=req.label,
        base_url=req.base_url.rstrip("/"),
        api_key=req.api_key,
        model=req.model or (check["models"][0] if check["models"] else None),
        status="active",
        last_checked_at=datetime.utcnow(),
        meta={"models_count": len(check["models"])},
    )
    session.add(b)
    await session.commit()
    await session.refresh(b)
    return {
        "bound": True,
        "provider": b.provider,
        "model": b.model,
        "models": check["models"][:200],
        "status": b.status,
        "api_key_masked": _mask(b.api_key),
    }


@router.delete("/bind")
async def unbind(session: DBSession) -> dict:
    b = await get_active_binding(session)
    if b is not None:
        await session.delete(b)
        await session.commit()
    return {"bound": False}


@router.get("/models")
async def list_models(session: DBSession) -> dict:
    """根据已绑定 API 自动识别可用模型（前端下拉选择）。"""
    b = await get_active_binding(session)
    if b is None:
        raise HTTPException(
            status_code=404, detail={"code": "not_bound", "message": "尚未绑定模型 API"}
        )
    client = client_from_binding(b)
    try:
        models = await client.list_models()
    except Exception as exc:  # noqa: BLE001 — LLMError → 502
        raise HTTPException(
            status_code=502,
            detail={"code": "models_failed", "message": f"模型列表获取失败：{exc}"},
        ) from exc
    return {"provider": b.provider, "models": models[:200]}


def _mask(key: str) -> str:
    return f"{key[:4]}***{key[-4:]}" if len(key) > 8 else "***"


# ---------- Regime 简报 ----------


@router.post("/regime-brief")
async def ai_regime_brief(session: DBSession, providers: ProvidersDep) -> dict:
    """基于主要交易货币数据生成体制技术分析简报（消耗模型 API，未绑定时规则引擎）。"""
    overview = await build_market_overview(providers.market)
    ctx = {
        "regime_label": overview["regime"]["label"],
        "regime_score": overview["regime"]["score"],
        "majors": overview["indices"],
        "gainers": overview["gainers"][:5],
        "losers": overview["losers"][:5],
        "funding_extremes": sorted(
            overview.get("funding") or [], key=lambda f: abs(float(f["rate"])), reverse=True
        )[:3],
        "macro_headline": None,
    }
    return await regime_brief(session, ctx)


# ---------- 标的对话 ----------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    interval: str = Field(default="1h", pattern="^(1m|5m|15m|1h|4h|1d)$")
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)

    # 宏观标的参数（symbol 属于股指/商品映射时生效）
    range: str = Field(default="1mo", pattern="^(5d|1mo|3mo|6mo|1y)$")


async def _yahoo_snapshot(symbol: str, rng: str, interval: str) -> dict | None:
    """宏观标的（股指/商品）AI 快照；非 yahoo 标的返回 None 走 crypto 链路。"""
    ys = SYMBOL_TO_YAHOO.get(symbol.upper())
    if ys is None:
        return None
    from w3ex.providers.yahoo.market import NAME_ZH, YahooProvider

    candles = await YahooProvider().get_ohlc(ys, rng, interval)
    if not candles:
        return None
    closes = [c["c"] for c in candles]
    win = candles[-24:] if len(candles) >= 24 else candles
    hi = max(c["h"] for c in win)
    lo = min(c["l"] for c in win)
    prev = candles[-25]["c"] if len(candles) >= 25 else candles[0]["c"]
    return {
        "symbol": symbol.upper(),
        "name": NAME_ZH.get(symbol.upper(), symbol.upper()),
        "market": "macro",
        "price": closes[-1],
        "change_24h_pct": round((closes[-1] - prev) / prev * 100, 2) if prev else 0.0,
        "stats": {
            "open": prev,
            "high": hi,
            "low": lo,
            "amplitude_pct": round((hi - lo) / lo * 100, 2) if lo else None,
        },
        "indicators": _indicator_snapshot(closes),
    }


@router.post("/asset-chat/{symbol}")
async def ai_asset_chat(
    symbol: str, req: ChatRequest, session: DBSession, providers: ProvidersDep
) -> dict:
    """标的实时技术分析对话（消耗模型 API）。上下文：OHLC/振幅/指标快照。

    symbol 属于股指/商品映射（SPX/XAU 等）时走 yahoo K 线快照，否则走 crypto 详情。
    """
    snap = await _yahoo_snapshot(symbol, req.range, req.interval)
    if snap is not None:
        return await asset_chat(session, snap["symbol"], req.message, snap, req.history)
    detail = await build_asset_detail(symbol, providers.market, interval=req.interval)
    snapshot = _asset_snapshot(detail)
    return await asset_chat(session, detail["symbol"], req.message, snapshot, req.history)


@router.post("/asset-chat/{symbol}/stream")
async def ai_asset_chat_stream(
    symbol: str, req: ChatRequest, session: DBSession, providers: ProvidersDep
) -> StreamingResponse:
    """SSE 流式标的对话：step→delta→done|error 事件（卡住容错在 intelligence 层）。"""
    import json as _json

    from w3ex.intelligence.ai import asset_chat_stream

    snap = await _yahoo_snapshot(symbol, req.range, req.interval)
    if snap is None:
        detail = await build_asset_detail(symbol, providers.market, interval=req.interval)
        snap = _asset_snapshot(detail)

    async def gen():
        async for event in asset_chat_stream(
            session, symbol.upper(), req.message, snap, req.history
        ):
            yield f"data: {_json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def _asset_snapshot(detail: dict) -> dict:
    """从资产详情提取 AI 上下文：价格 / OHLC / 振幅 / 指标现值。"""
    candles = detail.get("candles") or []
    snap: dict = {
        "price": detail.get("price"),
        "change_24h_pct": detail.get("change_24h_pct") or 0.0,
        "stats": {},
        "indicators": {},
    }
    if not candles:
        return snap
    win = candles[-24:] if len(candles) >= 24 else candles
    hi = max(c["h"] for c in win)
    lo = min(c["l"] for c in win)
    prev = candles[-25]["c"] if len(candles) >= 25 else candles[0]["c"]
    snap["stats"] = {
        "open": prev,
        "high": hi,
        "low": lo,
        "amplitude_pct": round((hi - lo) / lo * 100, 2) if lo else None,
    }
    closes = [c["c"] for c in candles]
    snap["indicators"] = _indicator_snapshot(closes)
    # 一致性防护：K 线回退 mock（瞬时上游失败）时与真实现价量级不符，
    # 显式标注让模型知道并保守表述，避免混拽数据被当作事实
    price = detail.get("price")
    if price and closes and abs(closes[-1] / float(price) - 1) > 0.3:
        snap["data_quality"] = "mock_candles"
    return snap


def _sma(vals: list[float], n: int) -> float | None:
    return round(sum(vals[-n:]) / n, 4) if len(vals) >= n else None


def _rsi(vals: list[float], n: int = 14) -> float | None:
    if len(vals) < n + 1:
        return None
    gains = losses = 0.0
    for i in range(-(n), 0):
        d = vals[i] - vals[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    if losses == 0:
        return 100.0
    rs = (gains / n) / (losses / n)
    return round(100 - 100 / (1 + rs), 2)


def _macd_hist(vals: list[float]) -> float | None:
    if len(vals) < 35:
        return None

    def ema(series: list[float], n: int) -> list[float]:
        k = 2 / (n + 1)
        out = [series[0]]
        for v in series[1:]:
            out.append(v * k + out[-1] * (1 - k))
        return out

    e12, e26 = ema(vals, 12), ema(vals, 26)
    dif = [a - b for a, b in zip(e12, e26, strict=True)]
    dea = ema(dif, 9)
    return round((dif[-1] - dea[-1]) * 2, 4)


def _indicator_snapshot(closes: list[float]) -> dict:
    return {
        "MA(5)": _sma(closes, 5),
        "MA(20)": _sma(closes, 20),
        "MA(60)": _sma(closes, 60),
        "RSI(14)": _rsi(closes),
        "MACD": _macd_hist(closes),
    }
