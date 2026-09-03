from w3ex.providers import (
    base,  # noqa: F401
    mock,  # noqa: F401  (registers mock factories)
    registry,  # noqa: F401
)
from w3ex.providers.binance import BinanceExecutionProvider, BinanceMarketProvider
from w3ex.providers.coingecko import CoinGeckoProvider
from w3ex.providers.composite import CompositeExecutionProvider, CompositeMarketProvider
from w3ex.providers.hyperliquid import HyperliquidExecutionProvider
from w3ex.providers.jupiter import JupiterExecutionProvider
from w3ex.providers.mock.execution import MockExecutionProvider
from w3ex.providers.mock.market import MockMarketProvider

# market: 单源直选或 rich 组合（真实源优先 + mock 兜底）
registry.register("market", "mock", MockMarketProvider)
registry.register("market", "binance", BinanceMarketProvider)
registry.register("market", "coingecko", CoinGeckoProvider)
registry.register(
    "market",
    "rich",
    lambda: CompositeMarketProvider(
        primary=BinanceMarketProvider(),
        meta=CoinGeckoProvider(),
        fallback=MockMarketProvider(),
    ),
)

# execution: 单通道或 rich 组合（CEX + DEX 聚合 + Perp 并发报价，paper 成交）
registry.register("execution", "mock", MockExecutionProvider)
registry.register("execution", "binance", BinanceExecutionProvider)
registry.register("execution", "jupiter", JupiterExecutionProvider)
registry.register("execution", "hyperliquid", HyperliquidExecutionProvider)
registry.register(
    "execution",
    "rich",
    lambda: CompositeExecutionProvider(
        subs=[
            BinanceExecutionProvider(),
            JupiterExecutionProvider(),
            HyperliquidExecutionProvider(),
        ],
        fallback=MockExecutionProvider(),
    ),
)

__all__ = ["registry"]
