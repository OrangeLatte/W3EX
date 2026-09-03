# 07 · Data Sources & Mock Fallback

## 定位变化

MVP 初始版本为全 mock；当前版本默认 **`rich` provider**——真实公开数据源优先，mock 仅作为**降级回退**。每个响应带 `sources` 字段透出实际数据来源。

## Provider 拓扑

```
CompositeMarketProvider (W3EX_MARKET_PROVIDER=rich)
  primary  → BinanceMarketProvider   data-api.binance.vision（官方公开行情镜像）
  meta     → CoinGeckoProvider       api.coingecko.com/api/v3（公开，免 key）
  fallback → MockMarketProvider      确定性数据（固定 seed）

CompositeExecutionProvider (W3EX_EXECUTION_PROVIDER=rich)
  binance    → 订单簿吃单模拟（depth_walk，taker 0.1%）
  jupiter    → Jupiter quote-api v6（Solana DEX 聚合）
  hyperliquid → allMids 中间价（fee 0.045%）
  fallback   → MockExecutionProvider（3 条模拟路由）
```

`_chain` 策略：主源失败/空数据 → meta → fallback；全失败抛 `ProviderUnavailable`/`RuntimeError`。
`get_tickers/get_global_stats/get_asset_meta` 走 meta 优先（CoinGecko 全市场覆盖更广）。

## 方法 → 数据源映射

| 方法 | Binance（镜像） | CoinGecko | Mock 回退 |
|---|---|---|---|
| get_price / get_tickers | 24hr ticker | coins/markets | 确定性生成 |
| get_candles | klines（5m-1d） | — | 确定性随机游走 |
| get_depth | depth | — | 阶梯深度 |
| get_funding / summary | premiumIndex | — | — |
| get_market_regime | 三大币 24hr 加权 | tickers 加权 | ASSETS 加权 |
| get_global_stats | — | /global | ASSETS 汇总 |
| get_asset_meta | — | SYMBOL_TO_ID 静态映射 | mcap 排名 |
| get_liquidations | 无公开端点 → 抛 | — | 模拟清算 |

环境变量：`W3EX_BINANCE_SPOT_BASE` / `W3EX_BINANCE_FAPI_BASE` 可覆盖镜像地址。

## 基础设施（providers/http.py）

- 全局 `httpx.AsyncClient`（timeout 8s）+ 进程内 TTLCache
- 429/5xx GET 指数退避重试（0.5s / 1s，最多 2 次重试）
- 失败统一抛 `ProviderUnavailable`，由 composite 链消费

## Mock 数据（降级时 / 测试用）

- 确定性（固定 seed 文本），测试全离线可复现
- 资产：BTC/ETH/SOL/稳定币 + Top 长尾；48h candles
- `trade/confirm` 永远 `paper: true`，不移动真实资金
- 响应 `sources` 中 mock 出现时 UI 明确标注（如 `liquidations: "mock"`）

## 明确标注

- 每个响应的 `sources` 字段是 UI 数据来源声明的唯一依据
- 执行结果 `paper: true` + UI "Simulated" 徽章
