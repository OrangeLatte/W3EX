# 02 · System Architecture

## 模块化单体 (Modular Monolith)

```
┌─────────────────────────────────────────────────────────────────┐
│  Next.js Terminal UI  (frontend/)                                │
│  Market Overview / All Tickers / Asset Detail / Trade / Watchlist │
└───────────────────────────────┬─────────────────────────────────┘
                                │ REST JSON (api/v1)
┌───────────────────────────────▼─────────────────────────────────┐
│  FastAPI  (backend/src/w3ex)                                     │
│  ┌──────────────────────┬──────────────────┬──────────────┐      │
│  │ api/routes           │ execution/       │ core/        │      │
│  │ market/assets/trade/ │ router           │ schemas      │      │
│  │ watchlist            │ quotes→confirm   │ repository   │      │
│  └──────────┬───────────┴────────┬─────────┴──────┬───────┘      │
│             │                    │                │               │
│  ┌──────────▼────────────────────▼────────────────▼───────────┐  │
│  │  providers/  (工厂 + 注册表, env 选型)                       │  │
│  │  market: binance | coingecko | rich(composite) | mock      │  │
│  │  execution: binance | jupiter | hyperliquid | rich | mock  │  │
│  │  http.py: TTLCache + 退避重试 + ProviderUnavailable          │  │
│  └──────────┬─────────────────────────────────────────────────┘  │
│             │                                                    │
│  ┌──────────▼─────────────────────────────────────────────────┐  │
│  │  db/  SQLAlchemy 2.x async                                  │  │
│  │  PostgreSQL (prod) / SQLite (dev/test 降级)                 │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## 数据管线

```
External API (Binance 镜像 / CoinGecko / Jupiter / Hyperliquid)
   → Provider Adapter (canonical Pydantic 结构)
   → CompositeMarketProvider (primary→meta→fallback 链)
   → API 路由 (薄壳, Decimal→str)
   → UI (sources 透出)
```

- 业务代码仅依赖接口（`providers/base.py`），不依赖具体 Provider。
- 失败语义：单源失败 → 链内降级；全失败 → `ProviderUnavailable` / mock 回退。

## 执行链路

```
User 交易意图 → ExecutionRouter
  ├── Binance CEX   (订单簿 depth_walk 吃单模拟, taker 0.1%)
  ├── Jupiter DEX   (Solana 聚合器真实 quote)
  └── Hyperliquid   (allMids 中间价)
→ ExecutionQuote (价格/滑点/费用/总成本对比, best=min total_cost_usd)
→ User Confirmation (POST /trade/confirm)
→ Execution (paper fill, 落库 trades, paper=true)
```

## 部署形态 (docker-compose)

- `postgres`: PostgreSQL 16（watchlist / trade_quotes / trades 持久化）
- `redis`: 缓存预留
- `api`: uvicorn FastAPI（启动时 init-db + seed）
- `web`: Next.js（构建时注入 NEXT_PUBLIC_API_BASE）

## 异步

- 全链路 async（httpx.AsyncClient + SQLAlchemy async + anyio）。
- Temporal 类工作流系统不在 MVP 范围。
