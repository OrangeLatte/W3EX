from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Any

from w3ex.core.schemas import (
    Candle,
    ChainTransaction,
    ExchangeFlow,
    ExecutionQuoteResult,
    ExecutionResult,
    HolderStats,
    LiquidationEvent,
    LLMCompleteRequest,
    LLMCompleteResponse,
    MarketRegime,
    NewsItem,
    PriceQuote,
    ProtocolMetric,
    Ticker,
    WalletBalance,
)


class ProviderUnavailable(RuntimeError):
    """真实数据源不可达 / 不支持该资产 / 返回无数据，调用方应回退下一个 Provider。"""


class MarketDataProvider(ABC):
    """市场数据：价格 / K线 / 行情 / 衍生品 / 体制判定。"""

    name = "base"

    @abstractmethod
    async def get_price(self, asset: str) -> PriceQuote: ...

    @abstractmethod
    async def get_candles(
        self, asset: str, interval: str = "1h", limit: int = 100
    ) -> list[Candle]: ...

    @abstractmethod
    async def get_tickers(self, assets: list[str] | None = None) -> list[Ticker]: ...

    @abstractmethod
    async def get_funding(self, asset: str) -> float | None: ...

    @abstractmethod
    async def get_liquidations(self, hours: int = 24) -> list[LiquidationEvent]: ...

    @abstractmethod
    async def get_market_regime(self) -> MarketRegime: ...

    # ---- 可选扩展能力（默认不支持，组合层逐级回退）----

    async def get_depth(self, asset: str, limit: int = 20) -> dict | None:
        """订单簿深度快照：{"bids": [[price, size], ...], "asks": [[...]], "ts": iso}。"""
        return None

    async def get_global_stats(self) -> dict | None:
        """全局市场统计：总市值 / 24h 成交额 / BTC 占比 / 市值 24h 变化。"""
        return None

    async def get_asset_meta(self, asset: str) -> dict | None:
        """资产元数据：名称 / 市值 / 排名 / 流通量 / 24h 高低。"""
        return None

    async def get_funding_summary(self, limit: int = 15) -> list[dict] | None:
        """资金费率总览：[{symbol, rate, mark_price, ts}]。"""
        return None


class OnchainProvider(ABC):
    """链上数据：交易 / 余额 / 大额转移 / 换手 / 持仓 / 交易所流。"""

    name = "base"

    @abstractmethod
    async def get_transactions(self, address: str, limit: int = 50) -> list[ChainTransaction]: ...

    @abstractmethod
    async def get_balances(self, address: str) -> list[WalletBalance]: ...

    @abstractmethod
    async def get_large_transfers(
        self, asset: str | None = None, hours: int = 24
    ) -> list[ChainTransaction]: ...

    @abstractmethod
    async def get_dex_swaps(
        self, asset: str | None = None, hours: int = 24
    ) -> list[ChainTransaction]: ...

    @abstractmethod
    async def get_holder_stats(self, asset: str) -> HolderStats: ...

    @abstractmethod
    async def get_exchange_flow(self, asset: str, hours: int = 24) -> list[ExchangeFlow]: ...


class ProtocolDataProvider(ABC):
    """协议基本面：TVL / 费用 / 用户 / 交易量。"""

    name = "base"

    @abstractmethod
    async def get_protocol_metrics(self, protocol: str) -> list[ProtocolMetric]: ...

    @abstractmethod
    async def list_protocols(self) -> list[str]: ...


class NewsProvider(ABC):
    """新闻与情绪。"""

    name = "base"

    @abstractmethod
    async def get_news(self, hours: int = 24, limit: int = 50) -> list[NewsItem]: ...


class ExecutionProvider(ABC):
    """执行层：报价与下单（MVP 全部 paper fill，真实成交由 CEX 账户/API Key 接入后开启）。"""

    name = "base"

    @abstractmethod
    async def get_quote(
        self,
        side: str,
        asset: str,
        fiat_amount: Decimal,
        fiat_currency: str = "USD",
        market_type: str = "spot",
        constraints: dict[str, int] | None = None,
    ) -> ExecutionQuoteResult: ...

    async def execute(self, quote: ExecutionQuoteResult, route_index: int) -> ExecutionResult:
        """默认 paper fill：按报价字段构造成交回执，不发生真实资金转移。"""
        from datetime import datetime

        route = quote.routes[route_index]
        return ExecutionResult(
            quote_id="pending",
            status="executed",
            paper=True,
            filled=dict(
                side=quote.side,
                asset_symbol=quote.asset_symbol,
                venue=route.venue,
                price=str(route.price),
                receive=str(route.estimated_receive),
                fees_usd=str(route.fees_usd),
                total_cost_usd=str(route.total_cost_usd),
            ),
            executed_at=datetime.utcnow(),
        )


class LLMProvider(ABC):
    """LLM 抽象：自由文本 + 结构化输出。mock 默认，openai/anthropic 预留。"""

    name = "base"
    model: str = "unknown"

    @abstractmethod
    async def complete(self, request: LLMCompleteRequest) -> LLMCompleteResponse: ...

    async def complete_structured(self, request: LLMCompleteRequest, schema: Any) -> dict:
        """将 free-text 输出尝试解析为 schema 结构。默认实现：返回原文 dict。"""
        resp = await self.complete(request)
        return {"content": resp.content, "model": resp.model}
