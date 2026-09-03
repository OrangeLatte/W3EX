from w3ex.providers import (
    base,  # noqa: F401
    registry,
)

# 注册全部 mock provider（离线兜底实现）
from w3ex.providers.mock.execution import MockExecutionProvider
from w3ex.providers.mock.generator import MockDataset
from w3ex.providers.mock.market import MockMarketProvider, MockOnchainProvider
from w3ex.providers.mock.protocol import MockNewsProvider, MockProtocolProvider

registry.register("market", "mock", MockMarketProvider)
registry.register("onchain", "mock", MockOnchainProvider)
registry.register("protocol", "mock", MockProtocolProvider)
registry.register("news", "mock", MockNewsProvider)
registry.register("execution", "mock", MockExecutionProvider)

__all__ = ["MockDataset"]
