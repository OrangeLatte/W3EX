# 04 · Provider Abstraction Interfaces

核心业务代码只依赖抽象接口（`providers/base.py`），通过 `providers/factory.py` + `registry.py` 按配置注入具体实现。默认 `rich`（真实源 + mock 回退），可切 `mock` 离线运行。

## MarketDataProvider

```python
class MarketDataProvider(ABC):
    name: str
    async def get_price(self, asset: str) -> PriceQuote
    async def get_candles(self, asset: str, interval: str, limit: int) -> list[Candle]
    async def get_tickers(self, assets: list[str] | None = None) -> list[Ticker]
    async def get_funding(self, asset: str) -> FundingRate | None
    async def get_market_regime(self) -> MarketRegime
    async def get_depth(self, asset: str, limit: int) -> OrderBookSnapshot | None
    async def get_global_stats(self) -> GlobalStats | None
    async def get_asset_meta(self, symbol: str) -> AssetMeta | None
    async def get_funding_summary(self, limit: int) -> list[FundingRate]
    async def get_liquidations(self, since_ts: datetime) -> list[LiquidationEvent]
```

可选方法默认 `return None`（provider 不支持时由 composite 链降级）。无数据抛 `ProviderUnavailable`。

## ExecutionProvider

```python
class ExecutionProvider(ABC):
    name: str
    venue_prefix: str
    async def get_quote(self, request: QuoteRequest) -> list[ExecutionRoute]
    async def execute(self, venue: str, route: ExecutionRoute, side, asset, fiat_amount) -> ExecutionResult
```

`get_quote` 返回候选路由（价格/滑点/费用/gas/总成本/置信度/notes）；`execute` 默认 paper fill。

## Composite（rich）

- `CompositeMarketProvider(primary=binance, meta=coingecko, fallback=mock)`：按方法组织优先级链，惰性 await，None/空视为无数据继续下一个。
- `CompositeExecutionProvider(subs, fallback)`：`asyncio.gather(return_exceptions=True)` 并发收集路由，best = min(total_cost_usd)；`execute` 按 venue 前缀分发。

## 注册表与工厂

```python
registry.register("binance", BinanceMarketProvider)   # providers/__init__.py
build_market(settings) / build_execution(settings) -> Provider
```

| 组件 | env | 可选值 |
|---|---|---|
| market | W3EX_MARKET_PROVIDER | mock \| binance \| coingecko \| rich |
| execution | W3EX_EXECUTION_PROVIDER | mock \| binance \| jupiter \| hyperliquid \| rich |

Binance 镜像可用 `W3EX_BINANCE_SPOT_BASE` / `W3EX_BINANCE_FAPI_BASE` 覆盖。

## 规范

所有 Provider 返回 **canonical Pydantic 结构**（`core/schemas.py`），不透出厂商结构。新增数据源只加 Provider 实现 + 注册，不改业务逻辑。
