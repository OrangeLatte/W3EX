from __future__ import annotations

from w3ex.core.schemas import NewsItem, ProtocolMetric
from w3ex.providers.base import NewsProvider, ProtocolDataProvider
from w3ex.providers.mock.generator import PROTOCOLS, MockDataset


class MockProtocolProvider(ProtocolDataProvider):
    name = "mock"

    def __init__(self, dataset: MockDataset | None = None) -> None:
        self.ds = dataset or MockDataset()

    async def get_protocol_metrics(self, protocol: str) -> list[ProtocolMetric]:
        return self.ds.protocol_metrics(protocol)

    async def list_protocols(self) -> list[str]:
        return [p["name"] for p in PROTOCOLS]


class MockNewsProvider(NewsProvider):
    name = "mock"

    def __init__(self, dataset: MockDataset | None = None) -> None:
        self.ds = dataset or MockDataset()

    async def get_news(self, hours: int = 24, limit: int = 50) -> list[NewsItem]:
        return self.ds.news(hours=hours, limit=limit)
