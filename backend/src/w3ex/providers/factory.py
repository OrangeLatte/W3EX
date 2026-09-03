from __future__ import annotations

from dataclasses import dataclass

from w3ex.config import Settings, get_settings
from w3ex.providers import registry
from w3ex.providers.base import ExecutionProvider, MarketDataProvider


@dataclass
class ProviderBundle:
    market: MarketDataProvider
    execution: ExecutionProvider

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> ProviderBundle:
        settings = settings or get_settings()
        return cls(
            market=registry.build("market", settings.market_provider),
            execution=registry.build("execution", settings.execution_provider),
        )
