"""Provider 层单测：全部离线（monkeypatch fetch_json / 假 Provider），不打真实网络。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from w3ex.core.schemas import ExecutionQuoteResult, ExecutionRoute, PriceQuote
from w3ex.providers.base import MarketDataProvider, ProviderUnavailable
from w3ex.providers.binance.execution import depth_walk
from w3ex.providers.binance.market import BinanceMarketProvider
from w3ex.providers.composite.rich import CompositeExecutionProvider, CompositeMarketProvider
from w3ex.providers.mock.execution import MockExecutionProvider
from w3ex.providers.mock.market import MockMarketProvider

pytestmark = pytest.mark.asyncio


class _FlakyProvider(MarketDataProvider):
    name = "flaky"

    async def get_price(self, asset: str) -> PriceQuote:
        raise ProviderUnavailable("network down")

    async def get_candles(self, asset, interval="1h", limit=100):
        raise ProviderUnavailable("network down")

    async def get_tickers(self, assets=None):
        raise ProviderUnavailable("network down")

    async def get_funding(self, asset):
        raise ProviderUnavailable("network down")

    async def get_liquidations(self, hours=24):
        raise ProviderUnavailable("network down")

    async def get_market_regime(self):
        raise ProviderUnavailable("network down")


# ---------- CompositeMarketProvider 回退 ----------


async def test_composite_falls_back_to_mock():
    composite = CompositeMarketProvider(
        primary=_FlakyProvider(), meta=_FlakyProvider(), fallback=MockMarketProvider()
    )
    quote = await composite.get_price("BTC")
    assert quote.price > 0
    tickers = await composite.get_tickers(["BTC"])
    assert tickers[0].symbol == "BTC"
    # Decision Workspace 透明性：全部走 mock 时 tick_source 必须为 None（UI 须标注模拟数据）
    assert composite.tick_source is None
    assert composite.last_source is None
    stats = await composite.get_global_stats()
    assert stats and stats["total_market_cap_usd"] > 0
    regime = await composite.get_market_regime()
    assert regime.regime in ("risk_on", "risk_off", "neutral")


async def test_composite_tick_source_records_real_provider():
    """非 mock 命名的真实源成功服务 tickers → tick_source 记录该源名。"""

    class _OkReal(MockMarketProvider):
        name = "ok_real"

    composite = CompositeMarketProvider(
        primary=_OkReal(), meta=_FlakyProvider(), fallback=MockMarketProvider()
    )
    await composite.get_tickers(["BTC"])
    assert composite.tick_source == "ok_real"
    assert composite.last_source == "ok_real"


async def test_composite_tick_source_none_on_mock_fallback():
    composite = CompositeMarketProvider(
        primary=_FlakyProvider(), meta=_FlakyProvider(), fallback=MockMarketProvider()
    )
    await composite.get_tickers(["BTC"])
    assert composite.tick_source is None


async def test_composite_liquidations_fall_to_mock():
    composite = CompositeMarketProvider(
        primary=BinanceMarketProvider(), meta=_FlakyProvider(), fallback=MockMarketProvider()
    )
    liqs = await composite.get_liquidations(hours=24)
    assert len(liqs) > 0  # binance 不可用（无网络/无端点）→ mock


# ---------- Binance 解析（monkeypatch fetch_json）----------


async def test_binance_parse_price(monkeypatch):
    payload = {
        "symbol": "BTCUSDT",
        "lastPrice": "65000.5",
        "bidPrice": "65000.4",
        "askPrice": "65000.6",
        "quoteVolume": "123456789.0",
        "priceChangePercent": "-1.25",
        "highPrice": "66000",
        "lowPrice": "64000",
    }

    async def fake_fetch(url, **kwargs):
        return payload

    monkeypatch.setattr("w3ex.providers.binance.market.fetch_json", fake_fetch)
    quote = await BinanceMarketProvider().get_price("BTC")
    assert quote.symbol == "BTC"
    assert quote.price == Decimal("65000.5")
    assert quote.change_24h_pct == -1.25


async def test_binance_parse_candles(monkeypatch):
    row = [1700000000000, "100", "110", "95", "105", "12.5", 1700003599999]

    async def fake_fetch(url, **kwargs):
        return [row, row]

    monkeypatch.setattr("w3ex.providers.binance.market.fetch_json", fake_fetch)
    candles = await BinanceMarketProvider().get_candles("BTC", limit=2)
    assert len(candles) == 2
    assert candles[0].open == Decimal("100")
    assert candles[0].close == Decimal("105")


# ---------- 深度推演 ----------


async def test_depth_walk_buy(monkeypatch):
    payload = {
        "bids": [["99.0", "10"]],
        "asks": [["100.0", "2"], ["101.0", "3"], ["102.0", "10"]],
    }

    async def fake_fetch(url, **kwargs):
        return payload

    monkeypatch.setattr("w3ex.providers.binance.execution.fetch_json", fake_fetch)
    result = await depth_walk("BTC", "buy", 400.0)  # $400 吃穿 2@100 + 2@101
    assert result["avg_price"] > 100.0  # 平均价劣于最优 ask
    assert abs(result["filled_qty"] * result["avg_price"] - 400.0) < 1e-6


# ---------- CompositeExecutionProvider ----------


def _route(venue: str, cost: str) -> ExecutionRoute:
    return ExecutionRoute(
        venue=venue,
        kind="cex",
        price=Decimal("100"),
        slippage_pct=0.01,
        fees_usd=Decimal("0.1"),
        gas_usd=Decimal("0"),
        total_cost_usd=Decimal(cost),
        estimated_receive=Decimal("1"),
        confidence=0.9,
        notes=[],
    )


class _OkProvider(MockExecutionProvider):
    name = "ok"
    venue_prefix = "ok"

    async def get_quote(self, side, asset, fiat_amount, fiat_currency="USD", market_type="spot"):
        from datetime import datetime

        return ExecutionQuoteResult(
            side=side,
            asset_symbol=asset.upper(),
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            routes=[_route("ok_venue", "1000.5")],
            best_route_index=0,
            expires_in_seconds=30,
            ts=datetime.utcnow(),
        )


async def test_composite_execution_merges_and_picks_best():
    composite = CompositeExecutionProvider(
        subs=[_OkProvider(), _FlakyProvider2()], fallback=MockExecutionProvider()
    )
    quote = await composite.get_quote("buy", "BTC", Decimal("1000"))
    assert len(quote.routes) == 1
    assert quote.routes[0].venue == "ok_venue"
    assert quote.best_route_index == 0


class _FlakyProvider2(MockExecutionProvider):
    name = "flaky2"

    async def get_quote(self, side, asset, fiat_amount, fiat_currency="USD", market_type="spot"):
        raise ProviderUnavailable("down")


async def test_composite_execution_all_fail_falls_back():
    composite = CompositeExecutionProvider(
        subs=[_FlakyProvider2()], fallback=MockExecutionProvider()
    )
    quote = await composite.get_quote("buy", "ETH", Decimal("500"))
    assert len(quote.routes) == 2  # mock 现货两通道（P0-1 分组）
    costs = [float(r.total_cost_usd) for r in quote.routes]
    assert quote.best_route_index == costs.index(min(costs))
