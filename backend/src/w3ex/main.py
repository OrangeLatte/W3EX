from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from w3ex.api.routes import agent, ai, assets, macro, market, trade, watchlist
from w3ex.config import get_settings
from w3ex.db.models import Entities
from w3ex.db.seed import seed_database
from w3ex.db.session import get_session_factory, init_db
from w3ex.execution.paper import paper_engine_loop

logger = logging.getLogger("w3ex")


async def _warm_one(coro_fn: Callable[[], Awaitable[Any]]) -> None:
    """单个预热探针：失败即目的（烧掉熔断器失败预算），成功则填充缓存。"""
    with contextlib.suppress(Exception):
        await coro_fn()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    factory = get_session_factory()
    async with factory() as session:
        count = await session.scalar(select(func.count()).select_from(Entities))
        if not count:
            await seed_database(session)
    settings = get_settings()
    # 评审 P0-4：所有 provider（含 mock）都启动挂单调度；
    # mock 价格为确定性小时级漂移路径，挂单按可复现路径触发。
    from w3ex.providers.factory import ProviderBundle

    bundle = ProviderBundle.from_settings(settings)
    task = asyncio.create_task(paper_engine_loop(bundle.market, interval_seconds=5.0))

    async def _warm_circuits() -> None:
        """冷启动预热熔断器：把不可达上游（如 CoinGecko/fapi）的失败预算在启动期烧完，
        避免首批用户请求各承担 ~10s 的探测成本。后台并发运行，失败即目的达成。"""
        await asyncio.gather(
            _warm_one(lambda: bundle.market.get_global_stats()),
            _warm_one(lambda: bundle.market.get_funding_summary(limit=5)),
        )

    warm_task = asyncio.create_task(_warm_circuits())

    async def _cache_warm_loop() -> None:
        """后台缓存预热循环：周期性刷新 overview/tickers/macro 热数据，
        用户请求始终命中 TTL 缓存（OKX/币安级响应速度）。单轮失败静默跳过。"""
        from w3ex.intelligence.market import build_market_overview
        from w3ex.providers.worldbank.macro import WorldBankProvider
        from w3ex.providers.yahoo.market import YahooProvider

        while True:
            try:
                bundle2 = ProviderBundle.from_settings(settings)
                yahoo, wb = YahooProvider(), WorldBankProvider()
                await asyncio.gather(
                    build_market_overview(bundle2.market),
                    bundle2.market.get_tickers(),
                    yahoo.get_indices(),
                    yahoo.get_commodities(),
                    wb.get_macro_overview(),
                    return_exceptions=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — 预热失败不影响服务
                logger.debug("cache warm cycle failed", exc_info=True)
            await asyncio.sleep(45)

    cache_task = asyncio.create_task(_cache_warm_loop())
    yield
    task.cancel()
    warm_task.cancel()
    cache_task.cancel()


app = FastAPI(
    title="Web3 Exchange",
    version="0.2.0",
    description="行情 + 交易执行终端（MVP，paper 模式；真实数据源 + mock 兜底）",
    lifespan=lifespan,
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = uuid.uuid4().hex[:8]
    request.state.request_id = rid
    response = await call_next(request)
    response.headers["X-Request-Id"] = rid
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # 评审 P1-4：内部异常不向外泄露堆栈/上游 URL，日志保留 request_id 便于排查
    rid = getattr(request.state, "request_id", "-")
    logger.exception("unhandled error rid=%s path=%s", rid, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "internal_error",
                "message": "服务内部错误，请稍后重试",
                "request_id": rid,
            }
        },
    )


API = "/api/v1"

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(market.router, prefix=API)
app.include_router(assets.router, prefix=API)
app.include_router(trade.router, prefix=API)
app.include_router(watchlist.router, prefix=API)
app.include_router(macro.router, prefix=API)
app.include_router(ai.router, prefix=API)
app.include_router(agent.router, prefix=API)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "w3ex"}
