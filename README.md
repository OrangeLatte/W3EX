# W3EX — Web3 Market & Paper-Trading Terminal

AI-native Web3 行情与模拟交易终端：**看行情 → 理解市场 → 模拟演练 → 谨慎执行**。

> ⚠️ 本项目为 **Paper Trading（模拟交易）** 系统：所有订单、仓位、账户均为模拟撮合，不涉及真实资金托管。AI 不得自主下单，所有执行需用户显式确认。

## Features

- **行情总览**：市场体制（Risk-On/Off 仪表盘 + AI 简报）、涨跌榜、市场热力图、资金费率、强平事件、稳定币流向；每块数据带来源标注（provenance badge，mock 数据显眼警示）
- **全量行情 + 标的详情合并页**：左侧 250+ 交易对列表（搜索/筛选），右侧 K 线（OKX 式 OHLC 图例、MA/EMA/BOLL/MACD/RSI/KDJ 指标自选、盘口深度、资金费率、1m 分时）、AI 实时技术分析对话框
- **宏观模块**：全球股指（SPX/NDX/DAX/日经/恒指…）+ 大宗商品（黄金/原油/铜…）+ 8 大经济体宏观指标（GDP/通胀/失业率/政策利率，World Bank 1960 起），点击查看历史时序与 AI 分析
- **AI 教练（四类 Agent + Function Calling）**：交易导师（苏格拉底式）/ 市场侦察 / 风险教练 / 复盘助手——自主调用 7 个工具（行情快照/账户/交易历史/宏观/下单预览），回复带工具调用轨迹；支持 6 语言回复
- **模拟交易**：现货/永续（1-20x 杠杆）/ 限价/止盈/止损，多通道路由比价（CEX 全成本 vs DEX 净到手 vs Perp），分阶段执行状态（CEX 撮合 / DEX 签名-广播-确认），幂等确认，每浏览器独立账户（权益/保证金/已实现/未实现盈亏）
- **回放审计**：每笔交易保留报价快照 + 推荐理由 + 「如果选另一条路线会怎样」反事实对比
- **六语 i18n**：中/英/法/西/阿（RTL）/俄

## Architecture

```
┌─────────────────────┐     REST /api/v1      ┌──────────────────────────┐
│  Next.js 15 (App)   │ ◄───────────────────► │  FastAPI (modular monolith)│
│  Tailwind v4        │                       │                          │
│  lightweight-charts │                       │  api/routes (薄壳)        │
└─────────────────────┘                       │  intelligence/ (Agent)   │
                                              │  execution/ (Paper Engine)│
                                              └───────────┬──────────────┘
                                                          │ Provider 抽象
                        ┌─────────────┬───────────────────┼──────────────┐
                        ▼             ▼                   ▼              ▼
                   Binance       CoinGecko          Jupiter /       Yahoo Finance
                   (行情/深度)    (市值/元数据)       Hyperliquid     World Bank
                                     │               (执行通道)      (宏观/股指)
                                     └───────── 全失败 → mock 兜底（诚实标注）──┘
```

核心循环：**Observe → Understand → Decide → Execute (Paper) → Review**

## Tech Stack

| Layer | Tech | Version |
|---|---|---|
| Frontend | Next.js (App Router) / React / Tailwind CSS | 15.x / 19.x / 4.x |
| Charts | lightweight-charts (TradingView) | 5.x |
| Backend | Python + FastAPI + SQLAlchemy 2 (async) | 3.11+ / 0.115+ / 2.0+ |
| LLM | OpenAI-compatible（GLM/DeepSeek 等，Function Calling）+ Anthropic | — |
| Data | SQLite (默认零配置) / PostgreSQL (可选) | — |
| Testing | pytest (96+ 离线) / ruff | — |

## Quickstart

### Backend

```bash
cd backend
conda create -n orangeCai python=3.11 -y && conda activate orangeCai   # 或任意 venv
pip install -e ".[dev]"
cp .env.example .env          # 可选；默认 SQLite + rich provider
python -m w3ex.cli init-db && python -m w3ex.cli seed   # 种子数据（mock 兜底用）
uvicorn w3ex.main:app --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --port 3002    # 打开 http://localhost:3002
```

### AI 教练绑定（可选）

`/settings` 页绑定任意 OpenAI 兼容 API（如智谱 GLM：Base URL `https://open.bigmodel.cn/api/paas/v4`），支持自动识别模型列表；未绑定时所有 AI 功能自动回退规则引擎（输出诚实标注 `source=rule`）。

### Docker（可选）

```bash
docker compose up -d          # postgres16 + redis + api + web
```

## Environment Variables

| Var | Default | 说明 |
|---|---|---|
| `W3EX_MARKET_PROVIDER` | `rich` | 行情链：Binance→CoinGecko→mock 回退 |
| `W3EX_EXECUTION_PROVIDER` | `rich` | 执行通道聚合（模拟成交） |
| `W3EX_DATABASE_URL` | SQLite | `postgresql+asyncpg://...` 可切换 |
| `W3EX_HTTPS_PROXY` | 自动探测 | macOS 读系统代理；显式覆盖出网 |
| `W3EX_BINANCE_SPOT_BASE` | 官方镜像 | 主站不可达时用 `data-api.binance.vision` |
| `W3EX_CORS_ORIGINS` | localhost:3000-3002 | 前端跨域白名单 |

## Resilience（网络韧性设计）

- **TTLCache + LRU(512)**：进程内缓存，TTL 30s–12h 按数据类型分级
- **熔断器**：连续 3 次失败 → 该上游冷却 120s，快速失败不再拖垮请求
- **single-flight + stale-if-error**：并发去重；上游失败回退过期缓存而非报错
- **httpx 客户端自愈**：真实源全败时丢弃重建客户端（代理变更/连接池坏死场景）
- **诚实降级**：任何 mock 兜底都带 `X-Data-Quality: simulated` 头 + UI 琥珀徽章，绝不冒充真实数据

## Testing

```bash
cd backend && python -m pytest -v          # 96 tests，全离线（mock 上游）
cd frontend && npx tsc --noEmit && npm run lint
```

## Project Structure

```
OrangeC_w3ex/
├── backend/
│   └── src/w3ex/
│       ├── providers/        # 数据源抽象 + composite 回退链 + LLM 客户端
│       ├── intelligence/     # Agent 工具化 / 行情聚合 / 快照
│       ├── execution/        # Paper Engine（netting/保证金/账户）
│       ├── api/routes/       # market/assets/macro/trade/watchlist/agent/ai
│       └── db/               # SQLAlchemy 模型 + 幂等迁移
├── frontend/
│   ├── app/                  # 9 页面（App Router）
│   ├── components/           # candle-chart / ai-chat-panel / heatmap / gauge
│   └── lib/                  # api 客户端 / i18n / 指标计算
├── docs/                     # 架构/契约/边界文档（01-07）
└── docker-compose.yml
```

## License

MIT
