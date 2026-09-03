# 05 · API Contracts (REST · /api/v1)

所有金额类 Decimal 字段序列化为字符串。统一错误：`{"detail": {"code": "...", "message": "..."}}`。

## 市场总览
```
GET /market/overview
{
  "as_of": "...",
  "global_stats": {                                  // 可 null（数据源不可达）
    "total_market_cap_usd": 0.0, "total_volume_24h_usd": 0.0,
    "btc_dominance_pct": 0.0, "eth_dominance_pct": 0.0,
    "mcap_change_24h_pct": 0.0, "active_cryptocurrencies": 0,
    "source": "coingecko", "ts": "..."
  },
  "regime": {"regime": "risk_on|risk_off|neutral", "score": 59.08, "label": "...",
             "drivers": ["BTC +34.5%", ...],
             "btc_change_24h_pct": 34.5, "eth_change_24h_pct": -1.6, "sol_change_24h_pct": 29.5},
  "indices": {"BTC": 34.5, "ETH": -1.6, "SOL": 29.5},          // 24h 变动 %
  "gainers":        [ticker, ...],   // 前 10，按 change_24h_pct 降序
  "losers":         [ticker, ...],   // 前 10，升序
  "volume_leaders": [ticker, ...],   // 前 10，按 volume_24h_usd 降序
  // ticker = {"symbol","price","change_24h_pct","volume_24h_usd","high_24h","low_24h"}
  "funding":      [{"symbol","rate","mark_price","ts"}],
  "liquidations": [{"symbol","side","amount_usd":"123.4","price":"...","ts"}],  // mock（无公开源）
  "sources": {"market": "rich", "liquidations": "mock"}
}
```

## 行情
```
GET /market/tickers?assets=BTC,ETH   → [ticker, ...]（不传 assets 返回全量）
GET /market/klines/{symbol}?interval=5m|15m|1h|4h|1d&limit=10..500
  → [{"ts","o","h","l","c","v"}]
GET /market/depth/{symbol}?limit=20
  → {"bids": [["price","qty"], ...], "asks": [...], "ts", "source"}  （稳定币等无深度 → 404）
GET /market/funding?limit=10 → [{"symbol","rate","mark_price","ts"}]
```

## 资产详情
```
GET /assets/{symbol}?interval=1h
{
  "symbol","name","price","change_24h_pct","change_1h_pct",   // change_1h_pct 可 null
  "interval": "1h",
  "candles": [{"ts","o","h","l","c","v"}],
  "stats": {"market_cap","market_cap_rank","volume_24h_usd","circulating_supply",
            "high_24h","low_24h"},                            // 部分可 null
  "funding_rate": 0.0001 | null,
  "depth": {"bids","asks","ts","source"} | null,
  "sources": {"market": "rich", "meta": "coingecko"}
}
```

## 交易
```
GET  /trade/quote?side=buy|sell&asset=SOL&amount=1000
{
  "quote_id","side","asset","fiat_amount":"1000","fiat_currency":"USD",
  "routes": [
    {"venue":"binance:spot","kind":"cex|dex|perp","price":"...","slippage_pct":0.01,
     "fees_usd":"1.0","gas_usd":"0.0","total_cost_usd":"1.2","estimated_receive":"...",
     "confidence":0.9,"notes":[...]}
  ],
  "best_route_index": 0,          // total_cost_usd 最低
  "expires_at": "...", "status": "pending"
}
POST /trade/confirm  {"quote_id":"...","route_index":0}
{
  "quote_id","status":"executed","filled":{"side","asset_symbol","venue","price",
    "receive","fees_usd","total_cost_usd"},
  "paper": true,
  "selected_route": {"venue","price","total_cost_usd"}, "executed_at": "..."
}
POST /trade/cancel   {"quote_id":"..."} → {"quote_id","status":"cancelled"}
```
状态机：`pending → executed | cancelled`；过期/重复确认 → 422；不存在 → 404。

## 自选
```
GET /watchlist → ["BTC","SOL", ...]
PUT /watchlist  {"symbols":["BTC","SOL"]} → ["BTC","SOL"]
```

## 健康检查
```
GET /health（根路径）→ {"status":"ok","service":"w3ex"}
```
