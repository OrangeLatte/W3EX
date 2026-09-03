"""组合 Provider（rich 模式）：多真实源优先 + mock 兜底，单源故障不致不可用。

- 行情/K线/深度/资金费率/体制: Binance → CoinGecko → Mock
- 全局统计/资产元数据/行情列表: CoinGecko → Binance → Mock
- 强平数据: 无公开真实源 → Mock（确定性模拟，UI 标注 simulated）
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from time import perf_counter
from typing import Any

from w3ex.core.schemas import (
    Candle,
    ExecutionRoute,
    LiquidationEvent,
    MarketRegime,
    PriceQuote,
    Ticker,
)
from w3ex.providers.base import (
    ExecutionProvider,
    ExecutionQuoteResult,
    MarketDataProvider,
    ProviderUnavailable,
)
from w3ex.providers.http import close_client


class CompositeMarketProvider(MarketDataProvider):
    name = "rich"

    def __init__(
        self,
        primary: MarketDataProvider,
        meta: MarketDataProvider,
        fallback: MarketDataProvider,
    ) -> None:
        self.primary = primary
        self.meta = meta
        self.fallback = fallback
        # 最近一次成功取数的真实 provider 名（mock 回退时不计入），
        # 供 intelligence 层做 sources 透明标注
        self.last_source: str | None = None

    async def _first(self, calls: list[tuple[MarketDataProvider, str, tuple]]) -> Any:
        self.last_source = None  # 每次取数重置：真实源成功才置位，mock 回退保持 None
        errors: list[str] = []
        real_failed = False
        for provider, method, args in calls:
            try:
                result = await getattr(provider, method)(*args)
                if result is None or (isinstance(result, (list, str)) and not result):
                    errors.append(f"{provider.name}: 无数据")
                    continue
                if provider.name != "mock":
                    self.last_source = provider.name
                return result
            except Exception as exc:  # noqa: BLE001 - 回退链必须吞掉一切单源异常
                errors.append(f"{provider.name}: {exc}")
                if provider.name != "mock":
                    real_failed = True
        # 自愈（评审 PDF P0 数据可信度）：真实源全失败说明共享 httpx 客户端可能
        # 已坏（keepalive 死连接/代理状态残留），丢弃重建，下一请求不再持续失败
        if real_failed:
            try:
                from w3ex.providers.http import reset_client

                await reset_client()
            except Exception:  # noqa: BLE001 — 自愈失败不影响 mock 兑底
                pass
        raise RuntimeError("all providers failed: " + " | ".join(errors))

    def _chain(self, method: str, *args: Any) -> list[tuple[MarketDataProvider, str, tuple]]:
        """按方法维度组织回退顺序（惰性求值，只 await 命中的那个）。

        tickers 走交易所优先（ CoinGecko 免费源经常限流/挂起，一次挂起 = 整条链
        8s×重试，直接拖垮行情页）；市值/排名类元数据只有 CoinGecko 提供，保留
        meta 优先，失败时上层以 None/空 数据优雅降级。
        """
        meta_first = {"get_global_stats", "get_asset_meta"}
        order = [self.meta, self.primary] if method in meta_first else [self.primary, self.meta]
        chain = [(p, method, args) for p in order]
        chain.append((self.fallback, method, args))
        return chain

    async def get_price(self, asset: str) -> PriceQuote:
        return await self._first(self._chain("get_price", asset))

    async def get_candles(self, asset: str, interval: str = "1h", limit: int = 100) -> list[Candle]:
        return await self._first(self._chain("get_candles", asset, interval, limit))

    async def get_tickers(self, assets: list[str] | None = None) -> list[Ticker]:
        result = await self._first(self._chain("get_tickers", assets))
        # Decision Workspace 透明性：记录本次 tickers 的真实服务源（mock 回退时为 None）
        self.tick_source = self.last_source
        return result

    async def get_funding(self, asset: str) -> float | None:
        try:
            return await self._first(self._chain("get_funding", asset))
        except RuntimeError:
            return None

    async def get_funding_summary(self, limit: int = 15) -> list[dict] | None:
        try:
            return await self._first(self._chain("get_funding_summary", limit))
        except RuntimeError:
            return None

    async def get_liquidations(self, hours: int = 24) -> list[LiquidationEvent]:
        return await self._first(self._chain("get_liquidations", hours))

    async def get_market_regime(self) -> MarketRegime:
        return await self._first(self._chain("get_market_regime"))

    async def get_depth(self, asset: str, limit: int = 20) -> dict | None:
        try:
            return await self._first(self._chain("get_depth", asset, limit))
        except RuntimeError:
            return None

    async def get_global_stats(self) -> dict | None:
        try:
            return await self._first(self._chain("get_global_stats"))
        except RuntimeError:
            return None

    async def get_asset_meta(self, asset: str) -> dict | None:
        try:
            return await self._first(self._chain("get_asset_meta", asset))
        except RuntimeError:
            return None

    async def aclose(self) -> None:
        await close_client()


class CompositeExecutionProvider(ExecutionProvider):
    """并发收集各执行通道报价 → 按市场类型分组（评审 P0-1）→ 分方向排序（P0-2）。

    - 现货买入：比较 all-in 全成本（价格+滑点+费用+Gas），取最低；
    - 现货卖出：比较净到手 USD，取最高；
    - 永续只与永续比较（仓位语义，不与现货混合排序）。
    """

    name = "rich"

    def __init__(self, subs: list[ExecutionProvider], fallback: ExecutionProvider) -> None:
        self.subs = subs
        self.fallback = fallback

    @staticmethod
    def _tag_routes(side: str, routes: list[ExecutionRoute]) -> list[ExecutionRoute]:
        for r in routes:
            r.instrument_type = "perp" if r.kind == "perp" else "spot"
            if side == "sell" and r.instrument_type == "spot":
                r.net_proceeds_usd = r.estimated_receive
                r.comparison_basis = "net_proceeds_usd"
            # Decision Workspace v3：最坏情况推演（按本路由滑点）
            slip = Decimal(str(r.slippage_pct)) / Decimal(100)
            base = (
                r.net_proceeds_usd
                if (side == "sell" and r.net_proceeds_usd is not None)
                else r.estimated_receive
            )
            r.worst_receive = (base * (Decimal(1) - slip)).quantize(Decimal("0.0001"))
        return routes

    async def get_quote(
        self,
        side: str,
        asset: str,
        fiat_amount: Decimal,
        fiat_currency: str = "USD",
        market_type: str = "spot",
        constraints: dict[str, int] | None = None,
    ) -> ExecutionQuoteResult:
        mt = market_type.lower()
        if mt not in ("spot", "perp"):
            raise ValueError("market_type 必须是 spot 或 perp")

        # Decision Workspace：记录每通道往返耗时 → data_age_ms（真实取价 ≈ RTT）
        async def _timed(sub: ExecutionProvider) -> ExecutionQuoteResult:
            t0 = perf_counter()
            res = await sub.get_quote(side, asset, fiat_amount, fiat_currency, market_type)
            age = int((perf_counter() - t0) * 1000)
            for r in res.routes:
                r.data_age_ms = age
            return res

        results = await asyncio.gather(
            *(_timed(sub) for sub in self.subs),
            return_exceptions=True,
        )
        routes: list[ExecutionRoute] = []
        sources: list[str] = []
        for sub, res in zip(self.subs, results, strict=True):
            if isinstance(res, BaseException):
                sources.append(f"{sub.name}: 不可用")
                continue
            routes.extend(self._tag_routes(side, res.routes))
            sources.append(f"{sub.name}: ok")
        if not routes:
            t0 = perf_counter()
            fallback_res = await self.fallback.get_quote(
                side, asset, fiat_amount, fiat_currency, market_type
            )
            fb_routes = self._tag_routes(side, fallback_res.routes)
            age = int((perf_counter() - t0) * 1000)
            for r in fb_routes:
                r.data_age_ms = age
            routes = fb_routes
            sources.append(f"{self.fallback.name}: fallback")

        # P0-1：只有同类产品可比较与排序
        same_type = [r for r in routes if r.instrument_type == mt]
        if not same_type:
            raise ProviderUnavailable(
                f"当前无 {mt} 可用报价通道（{', '.join(sources) or 'all failed'}）"
            )

        # P0-2：买入按全成本最低，卖出按净到手最高（Router 层约束过滤后会重选）
        if side == "buy":
            best = min(range(len(same_type)), key=lambda i: float(same_type[i].total_cost_usd))
            reason = (
                f"全成本最低：${float(same_type[best].total_cost_usd):,.2f}（含价格/滑点/费用/Gas）"
            )
        else:
            best = max(
                range(len(same_type)), key=lambda i: float(same_type[i].net_proceeds_usd or 0)
            )
            reason = f"净到手最多：${float(same_type[best].net_proceeds_usd or 0):,.2f}"

        # Decision Workspace：约束过滤统一在 ExecutionRouter 层执行（对任意 provider 生效），
        # composite 只负责通道聚合 / 同类过滤 / 计时与标记。
        return ExecutionQuoteResult(
            side=side,
            asset_symbol=asset.upper(),
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            routes=same_type,
            best_route_index=best,
            expires_in_seconds=30,
            ts=datetime.utcnow(),
            market_type=mt,
            recommendation_reason=reason,
        )

    async def execute(self, quote: ExecutionQuoteResult, route_index: int) -> Any:
        route = quote.routes[route_index]
        for sub in self.subs:
            if getattr(sub, "venue_prefix", None) and route.venue.startswith(sub.venue_prefix):
                return await sub.execute(quote, route_index)
        return await self.fallback.execute(quote, route_index)
