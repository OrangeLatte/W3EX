from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------- Market Data ----------


class PriceQuote(BaseModel):
    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume_24h: Decimal
    change_24h_pct: float
    ts: datetime


class Candle(BaseModel):
    symbol: str
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class Ticker(BaseModel):
    symbol: str
    last: Decimal
    bid: Decimal
    ask: Decimal
    high_24h: Decimal
    low_24h: Decimal
    volume_24h: Decimal
    change_24h_pct: float
    funding_rate: float | None = None
    ts: datetime


class LiquidationEvent(BaseModel):
    symbol: str
    side: Literal["long", "short"]
    amount_usd: Decimal
    price: Decimal
    ts: datetime


class MarketRegime(BaseModel):
    regime: Literal["risk_on", "risk_off", "neutral"]
    score: float  # -100..100
    btc_change_24h_pct: float
    eth_change_24h_pct: float
    sol_change_24h_pct: float
    label: str
    drivers: list[str] = Field(default_factory=list)


# ---------- On-chain Data ----------


class ChainTransaction(BaseModel):
    tx_hash: str
    chain: str
    from_address: str | None
    to_address: str | None
    value: Decimal
    asset_symbol: str | None
    value_usd: Decimal | None
    ts: datetime
    method: str | None = None
    log_events: list[dict[str, Any]] = Field(default_factory=list)


class WalletBalance(BaseModel):
    asset_symbol: str
    balance: Decimal
    value_usd: Decimal | None = None
    price: Decimal | None = None


class OnchainEvent(BaseModel):
    event_type: str
    asset_symbol: str | None
    amount: Decimal | None
    from_entity: str
    to_entity: str
    value_usd: Decimal | None
    tx_hash: str | None
    ts: datetime
    significance: float = 0.0
    raw: dict[str, Any] = Field(default_factory=dict)


class DexSwap(BaseModel):
    tx_hash: str
    chain: str
    dex_name: str
    token_in: str
    token_out: str
    amount_in: Decimal
    amount_out: Decimal
    value_usd: Decimal
    trader_address: str
    ts: datetime


class HolderStats(BaseModel):
    asset_symbol: str
    total_holders: int
    holders_24h_change: int
    top10_concentration_pct: float
    ts: datetime


class ExchangeFlow(BaseModel):
    asset_symbol: str
    exchange_name: str
    inflow_usd: Decimal
    outflow_usd: Decimal
    net_usd: Decimal
    ts: datetime


# ---------- Protocol Data ----------


class ProtocolMetric(BaseModel):
    protocol: str
    metric: str
    value: float
    ts: datetime


class ProtocolSnapshot(BaseModel):
    protocol: str
    chain: str | None
    category: str | None
    metrics: dict[str, float]
    ts: datetime


# ---------- News ----------


class NewsItem(BaseModel):
    title: str
    summary: str | None = None
    url: str | None = None
    source: str
    sentiment: float
    importance: float
    entity_symbols: list[str] = Field(default_factory=list)
    ts: datetime


# ---------- Execution ----------


class ExecutionRoute(BaseModel):
    venue: str  # e.g. binance_cex / jupiter_dex / hyperliquid_perp
    kind: Literal["cex", "dex", "perp"]
    price: Decimal
    slippage_pct: float
    fees_usd: Decimal
    gas_usd: Decimal
    total_cost_usd: Decimal
    estimated_receive: Decimal
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)
    # v2（评审 P0-1/P0-2）：产品语义与比较基准
    instrument_type: Literal["spot", "perp"] = "spot"
    net_proceeds_usd: Decimal | None = None  # 卖出现货：净到手 USD
    comparison_basis: str = "all_in_cost_usd"  # buy: all_in_cost_usd | sell: net_proceeds_usd
    # v3（Decision Workspace）：数据新鲜度 + 交易前风险
    data_age_ms: int = 0  # 报价数据年龄（provider 请求往返耗时，mock≈0）
    worst_receive: Decimal | None = None  # 最坏到手/净到手（按本路由滑点推演）
    funding_rate: float | None = None  # perp：资金费率（router 层填充）
    margin_required_usd: Decimal | None = None  # perp：所需保证金（按 leverage）
    liquidation_distance_pct: float | None = None  # perp：预估强平距离%（100/leverage）


class ExecutionQuoteResult(BaseModel):
    side: Literal["buy", "sell"]
    asset_symbol: str
    fiat_amount: Decimal
    fiat_currency: str = "USD"
    routes: list[ExecutionRoute]
    best_route_index: int
    expires_in_seconds: int = 60
    ts: datetime
    market_type: str = "spot"  # v2: spot|perp，只比较同类产品
    recommendation_reason: str = ""  # v2: 推荐理由（全成本最低 / 净到手最多）
    # v3（Decision Workspace）：用户约束
    constraints: dict[str, int] | None = None  # {max_slippage_bps, max_data_age_ms}
    filtered_routes: list[dict[str, Any]] = Field(default_factory=list)  # [{route, reason}]


class ExecutionResult(BaseModel):
    quote_id: str
    status: Literal["executed", "failed"]
    filled: dict[str, Any]
    paper: bool = True
    executed_at: datetime


# ---------- LLM ----------


class LLMMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LLMCompleteRequest(BaseModel):
    messages: list[LLMMessage]
    temperature: float = 0.2
    max_tokens: int = 1024


class LLMCompleteResponse(BaseModel):
    content: str
    model: str
    usage: dict[str, int] = Field(default_factory=dict)
