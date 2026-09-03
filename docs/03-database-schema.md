# 03 · Database Schema

PostgreSQL (prod) / SQLite (dev/test)。SQLAlchemy 2.x ORM。图兼容抽象：所有关系表带 `entity_id` 外键，未来可平移 Neo4j。

## 表清单

### entities — 统一实体表（资产/钱包/协议/CEX/叙事）
| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| type | enum(asset, wallet, protocol, exchange, narrative, category) | 实体类型 |
| name | text | 显示名 |
| symbol | text nullable | 资产/交易所符号 (BTC, ETH…) |
| address | text nullable | 链上地址（钱包/合约） |
| chain | text nullable | ethereum / solana / base |
| metadata | jsonb | 附加属性（logo、描述、分类…） |
| created_at / updated_at | timestamptz | |

### prices — 行情
| 列 | 类型 |
|---|---|
| id | bigserial PK |
| entity_id | uuid FK→entities |
| ts | timestamptz |
| open/high/low/close | numeric |
| volume | numeric |
| source | text |

### assets_meta — 资产基本面
entity_id FK, market_cap, circulating_supply, total_supply, rank, chain, category, metadata

### onchain_events — 链上事件（canonical 事件流）
| 列 | 类型 | 说明 |
|---|---|---|
| id | uuid PK | |
| chain | text | |
| block | bigint nullable | |
| tx_hash | text | 幂等主键之一 |
| event_type | enum(large_transfer, exchange_inflow, exchange_outflow, whale_move, new_wallet_accumulation, dex_spike, holder_change, protocol_usage_spike) | |
| asset_entity_id | uuid FK | |
| amount | numeric | |
| from_entity_id / to_entity_id | uuid FK nullable | 实体解析后 |
| value_usd | numeric nullable | |
| significance | float | 0-1 重要度 |
| source | text | |
| ts | timestamptz | |

### wallet_snapshots — 钱包持仓快照
wallet_entity_id FK, asset_entity_id FK, balance, value_usd, cost_basis nullable, ts
联合唯一 (wallet, asset, ts)

### wallet_txns — 钱包交易
wallet_entity_id FK, tx_hash, asset_entity_id, side(swap/buy/sell/send/receive), amount, counterparty_entity_id, value_usd, fee, ts

### wallet_profiles — 钱包画像
| 列 | 类型 |
|---|---|
| wallet_entity_id | uuid PK FK |
| label_verified | text nullable |  已验证实体名（仅可靠数据） |
| classification | enum(whale, active_trader, dex_trader, long_term_holder, high_frequency, new_wallet) |
| behavior_tags | jsonb |
| trading_frequency | float (笔/天) |
| favorite_assets | jsonb |
| pnl_est | numeric nullable |
| updated_at | |

### protocol_metrics — 协议指标
protocol_entity_id FK, metric enum(tvl, fees, users, volume), value, ts, source

### news — 新闻
id, title, summary, url, source, sentiment, entity_ids jsonb, importance, ts

### narratives — 叙事
| 列 | 类型 |
|---|---|
| id | uuid PK |
| name | text |
| momentum_score | float 0-100 |
| trend | enum(rising, falling, flat) |
| confidence | float |
| drivers | jsonb |  驱动事件列表 |
| related_asset_ids | jsonb |
| updated_at | |

### narrative_events — 叙事时间线
narrative_id FK, event_type, payload jsonb, ts

### intel_signals — 智能信号（打分后）
| 列 | 类型 |
|---|---|
| id | uuid PK |
| signal_type | text |
| entity_asset_id | uuid FK |
| title | text |
| description | text |
| scores | jsonb {impact, novelty, confidence, recency} |
| priority | float |  = impact×novelty×confidence×recency |
| source | text |
| ts | timestamptz |

### research_answers — 研究回答缓存/审计
id, query, answer, claims jsonb, retrieval_trace jsonb, latency_ms, ts

### watchlists — 自选
id, name, asset_ids jsonb, created_at

### trade_quotes — 交易报价
id, side, asset_entity_id, fiat_amount, routes jsonb, selected_route jsonb nullable, status(pending/confirmed/cancelled/executed), ts

### trades — 执行记录（MVP simulated）
id, quote_id FK, status, filled jsonb, executed_at

## 图兼容映射（未来 Neo4j）

| 关系表外键 | 图边 |
|---|---|
| onchain_events.from/to_entity_id | wallet→(traded)→asset |
| onchain_events | wallet→(interacted_with)→protocol |
| wallet_txns.counterparty | wallet→(counterparty)→wallet |
| news.entity_ids | asset→(mentioned_in)→news |
| narratives.related_asset_ids | narrative→(relates_to)→asset |

## 幂等

- onchain_events: `(tx_hash, event_type, asset_entity_id)` 唯一，重放安全。
- wallet_snapshots: `(wallet, asset, ts)` 唯一。
- prices: `(entity, ts_bucket, source)` 唯一（seed 固定桶）。

## 当前状态（pivot 后）

产品收敛为行情 + 交易后，API 层只使用 `watchlists / trade_quotes / trades` 三个表。
研究类表（`entities / prices / assets_meta / onchain_events / wallet_* / protocol_metrics / news / narratives* / intel_signals / research_answers`）的 ORM 定义与 seed 保留在代码中，供未来研究模块回归时复用，但**不在 API 层暴露**。
