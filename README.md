# W3EX — Web3 Market & Paper-Trading Terminal

[English](./README.md) | [简体中文](./README.zh-CN.md)

An AI-native Web3 market and paper-trading terminal: **Observe → Understand → Practice → Execute with care**.

> ⚠️ This project is a **Paper Trading** system: all orders, positions and accounts are simulated. No real funds are ever custodied. The AI never trades autonomously — every execution requires explicit user confirmation.

## Features

- **Market Overview**: market regime (Risk-On/Off gauge + AI briefing), top movers, market heatmap, funding rates, liquidation events, stablecoin flow; every panel carries a data-provenance badge (mock data is prominently flagged)
- **Markets + Asset Detail (merged page)**: 250+ tradable pairs on the left (search/filter), candlestick chart on the right (OKX-style OHLC legend, MA/EMA/BOLL/MACD/RSI/KDJ indicator picker, order-book depth, funding rate, 1m ticks) plus a real-time AI technical-analysis chat
- **Macro Module**: global equity indices (SPX/NDX/DAX/Nikkei/HSI…), commodities (gold/oil/copper…), and macro indicators for 8 major economies (GDP/inflation/unemployment/policy rate, World Bank, back to 1960) — click any series for history charts and AI analysis
- **AI Coaches (4 Agents + Function Calling)**: Trading Mentor (Socratic) / Market Scout / Risk Coach / Review Assistant — they autonomously call 7 tools (market snapshot / account / trade history / macro / order preview), replies carry a tool-call trace; replies available in 6 languages
- **Paper Trading**: spot & perpetual (1–20x leverage), limit / take-profit / stop-loss; multi-venue route comparison (CEX all-in cost vs DEX net proceeds vs Perp); staged execution status (CEX matching / DEX sign-broadcast-confirm); idempotent confirmation; per-browser account (equity / margin / realized / unrealized PnL)
- **Replay & Audit**: every trade keeps the quote snapshot, the recommendation rationale, and a "what if I had picked the other route" counterfactual comparison
- **6-language i18n**: English / 中文 / Français / Español / العربية (RTL) / Русский

## Architecture

```
┌─────────────────────┐     REST /api/v1      ┌──────────────────────────┐
│  Next.js 15 (App)   │ ◄───────────────────► │  FastAPI (modular monolith)│
│  Tailwind v4        │                       │                          │
│  lightweight-charts │                       │  api/routes (thin shells) │
└─────────────────────┘                       │  intelligence/ (Agents)  │
                                              │  execution/ (Paper Engine)│
                                              └───────────┬──────────────┘
                                                          │ Provider abstraction
                        ┌─────────────┬───────────────────┼──────────────┐
                        ▼             ▼                   ▼              ▼
                   Binance       CoinGecko          Jupiter /       Yahoo Finance
                   (prices/      (market cap/       Hyperliquid     World Bank
                    depth)        metadata)         (venues)        (macro/indices)
                                      │
                                      └────── all fail → mock fallback (honestly labeled)
```

Core loop: **Observe → Understand → Decide → Execute (Paper) → Review**

## Tech Stack

| Layer | Tech | Version |
|---|---|---|
| Frontend | Next.js (App Router) / React / Tailwind CSS | 15.x / 19.x / 4.x |
| Charts | lightweight-charts (TradingView) | 5.x |
| Backend | Python + FastAPI + SQLAlchemy 2 (async) | 3.11+ / 0.115+ / 2.0+ |
| LLM | OpenAI-compatible (GLM/DeepSeek etc., Function Calling) + Anthropic | — |
| Data | SQLite (default, zero config) / PostgreSQL (optional) | — |
| Testing | pytest (96+ offline tests) / ruff | — |

## Quickstart

### Backend

```bash
cd backend
conda create -n orangeCai python=3.11 -y && conda activate orangeCai   # or any venv
pip install -e ".[dev]"
cp .env.example .env          # optional; defaults to SQLite + rich provider
python -m w3ex.cli init-db && python -m w3ex.cli seed   # seed data (used by mock fallback)
uvicorn w3ex.main:app --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev -- --port 3002    # open http://localhost:3002
```

### AI Coach Binding (optional)

Bind any OpenAI-compatible API on the `/settings` page (e.g. Zhipu GLM: base URL `https://open.bigmodel.cn/api/paas/v4`); model lists are auto-detected. Without a binding, all AI features gracefully fall back to the rule engine (output honestly labeled `source=rule`).

### Docker (optional)

```bash
docker compose up -d          # postgres16 + redis + api + web
```

## Environment Variables

| Var | Default | Description |
|---|---|---|
| `W3EX_MARKET_PROVIDER` | `rich` | Market chain: Binance → CoinGecko → mock fallback |
| `W3EX_EXECUTION_PROVIDER` | `rich` | Execution venue aggregation (simulated fills) |
| `W3EX_DATABASE_URL` | SQLite | Switch with `postgresql+asyncpg://...` |
| `W3EX_HTTPS_PROXY` | auto-detected | macOS reads the system proxy; set explicitly to override egress |
| `W3EX_BINANCE_SPOT_BASE` | official mirror | Use `data-api.binance.vision` when the main site is unreachable |
| `W3EX_CORS_ORIGINS` | localhost:3000-3002 | Frontend CORS whitelist |

## Resilience Design

- **TTLCache + LRU(512)**: in-process cache, TTL 30s–12h tiered by data type
- **Circuit breaker**: 3 consecutive failures → that upstream cools down for 120s, failing fast instead of dragging requests
- **single-flight + stale-if-error**: concurrent dedup; on upstream failure, serve stale cache instead of erroring
- **httpx client self-healing**: when all real sources fail, the shared client is dropped and rebuilt (handles dead connection pools / proxy changes)
- **Honest degradation**: every mock fallback carries the `X-Data-Quality: simulated` header + an amber UI badge — never impersonating real data

## Testing

```bash
cd backend && python -m pytest -v          # 96 tests, fully offline (mocked upstreams)
cd frontend && npx tsc --noEmit && npm run lint
```

## Project Structure

```
OrangeC_w3ex/
├── backend/
│   └── src/w3ex/
│       ├── providers/        # data-source abstraction + composite fallback chain + LLM client
│       ├── intelligence/     # agent tooling / market aggregation / snapshots
│       ├── execution/        # Paper Engine (netting / margin / accounts)
│       ├── api/routes/       # market/assets/macro/trade/watchlist/agent/ai
│       └── db/               # SQLAlchemy models + idempotent migrations
├── frontend/
│   ├── app/                  # 9 pages (App Router)
│   ├── components/           # candle-chart / ai-chat-panel / heatmap / gauge
│   └── lib/                  # api client / i18n / indicator math
├── docs/                     # architecture / contract / boundary docs (01-07)
└── docker-compose.yml
```

## License

MIT
