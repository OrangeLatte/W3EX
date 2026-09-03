from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from w3ex.db.base import Base, IdMixin, TimestampMixin, utcnow

JSONVariant = JSON().with_variant(JSONB(), "postgresql")


class EntityType(StrEnum):
    asset = "asset"
    wallet = "wallet"
    protocol = "protocol"
    exchange = "exchange"
    narrative = "narrative"
    category = "category"


class Chain(StrEnum):
    ethereum = "ethereum"
    solana = "solana"
    base = "base"


class EventType(StrEnum):
    large_transfer = "large_transfer"
    exchange_inflow = "exchange_inflow"
    exchange_outflow = "exchange_outflow"
    whale_move = "whale_move"
    new_wallet_accumulation = "new_wallet_accumulation"
    dex_spike = "dex_spike"
    holder_change = "holder_change"
    protocol_usage_spike = "protocol_usage_spike"


class WalletClass(StrEnum):
    whale = "whale"
    active_trader = "active_trader"
    dex_trader = "dex_trader"
    long_term_holder = "long_term_holder"
    high_frequency = "high_frequency"
    new_wallet = "new_wallet"
    unknown = "unknown"


class Entities(IdMixin, TimestampMixin, Base):
    __tablename__ = "entities"

    type: Mapped[str] = mapped_column(Enum(EntityType, name="entity_type"), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    symbol: Mapped[str | None] = mapped_column(String(32), index=True)
    address: Mapped[str | None] = mapped_column(String(128), index=True)
    chain: Mapped[str | None] = mapped_column(String(24))
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONVariant, default=dict)

    __table_args__ = (
        UniqueConstraint("type", "symbol", name="uq_entities_type_symbol"),
        UniqueConstraint("type", "address", name="uq_entities_type_address"),
        Index("ix_entities_symbol_type", "symbol", "type"),
    )

    prices: Mapped[list[Prices]] = relationship(back_populates="entity")  # type: ignore[name-defined]


class Prices(IdMixin, Base):
    __tablename__ = "prices"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id"), index=True, nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    high: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    low: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    close: Mapped[Decimal] = mapped_column(Numeric(30, 12))
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    source: Mapped[str] = mapped_column(String(32), default="mock")

    entity: Mapped[Entities] = relationship(back_populates="prices")

    __table_args__ = (
        UniqueConstraint("entity_id", "ts", "source", name="uq_prices_entity_ts_source"),
    )


class AssetsMeta(IdMixin, Base):
    __tablename__ = "assets_meta"

    entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id"), index=True, nullable=False
    )
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    circulating_supply: Mapped[Decimal | None] = mapped_column(Numeric(40, 8))
    total_supply: Mapped[Decimal | None] = mapped_column(Numeric(40, 8))
    rank: Mapped[int | None] = mapped_column(Integer, index=True)
    category: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)


class OnchainEvents(IdMixin, Base):
    __tablename__ = "onchain_events"

    chain: Mapped[str] = mapped_column(String(24), index=True)
    block: Mapped[int | None] = mapped_column(BigInteger)
    tx_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    event_type: Mapped[str] = mapped_column(
        Enum(EventType, name="event_type"), index=True, nullable=False
    )
    asset_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(40, 10))
    from_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    to_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    value_usd: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    significance: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tx_hash", "event_type", "asset_entity_id", name="uq_onchain_tx_event"),
    )


class WalletSnapshots(IdMixin, Base):
    __tablename__ = "wallet_snapshots"

    wallet_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id"), index=True, nullable=False
    )
    asset_entity_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("entities.id"), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(40, 10))
    value_usd: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("wallet_entity_id", "asset_entity_id", "ts", name="uq_wallet_snapshot"),
    )


class WalletTxns(IdMixin, Base):
    __tablename__ = "wallet_txns"

    wallet_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id"), index=True, nullable=False
    )
    tx_hash: Mapped[str] = mapped_column(String(128))
    asset_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    side: Mapped[str] = mapped_column(String(16))  # swap/buy/sell/send/receive
    amount: Mapped[Decimal | None] = mapped_column(Numeric(40, 10))
    counterparty_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    value_usd: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    fee: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)

    __table_args__ = (UniqueConstraint("wallet_entity_id", "tx_hash", name="uq_wallet_tx"),)


class WalletProfiles(IdMixin, Base):
    __tablename__ = "wallet_profiles"

    wallet_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id"), index=True, nullable=False
    )
    label_verified: Mapped[str | None] = mapped_column(String(120))
    classification: Mapped[str] = mapped_column(
        Enum(WalletClass, name="wallet_class"), default=WalletClass.unknown.value
    )
    behavior_tags: Mapped[list[str]] = mapped_column(JSONVariant, default=list)
    trading_frequency: Mapped[float] = mapped_column(Float, default=0.0)  # trades/day
    favorite_assets: Mapped[list[str]] = mapped_column(JSONVariant, default=list)
    pnl_est: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ProtocolMetrics(IdMixin, Base):
    __tablename__ = "protocol_metrics"

    protocol_entity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("entities.id"), index=True, nullable=False
    )
    metric: Mapped[str] = mapped_column(String(24))  # tvl/fees/users/volume
    value: Mapped[float] = mapped_column(Float)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="mock")


class News(IdMixin, Base):
    __tablename__ = "news"

    title: Mapped[str] = mapped_column(String(300))
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(600))
    source: Mapped[str] = mapped_column(String(64))
    sentiment: Mapped[float] = mapped_column(Float, default=0.0)  # -1..1
    importance: Mapped[float] = mapped_column(Float, default=0.5)  # 0..1
    entity_ids: Mapped[list[str]] = mapped_column(JSONVariant, default=list)  # asset symbols
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)


class Narratives(IdMixin, TimestampMixin, Base):
    __tablename__ = "narratives"

    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    momentum_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100
    trend: Mapped[str] = mapped_column(String(12), default="flat")  # rising/falling/flat
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    drivers: Mapped[list[dict[str, Any]]] = mapped_column(JSONVariant, default=list)
    related_asset_ids: Mapped[list[str]] = mapped_column(JSONVariant, default=list)  # symbols


class NarrativeEvents(IdMixin, Base):
    __tablename__ = "narrative_events"

    narrative_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("narratives.id"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)


class IntelSignals(IdMixin, Base):
    __tablename__ = "intel_signals"

    signal_type: Mapped[str] = mapped_column(String(48), index=True)
    asset_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    scores: Mapped[dict[str, float]] = mapped_column(JSONVariant, default=dict)
    priority: Mapped[float] = mapped_column(Float, index=True, default=0.0)
    source: Mapped[str] = mapped_column(String(32), default="mock")
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)


class ResearchAnswers(IdMixin, Base):
    __tablename__ = "research_answers"

    query: Mapped[str] = mapped_column(Text, index=True)
    intent: Mapped[str | None] = mapped_column(String(48))
    entities: Mapped[list[str]] = mapped_column(JSONVariant, default=list)
    answer: Mapped[str] = mapped_column(Text)
    claims: Mapped[list[dict[str, Any]]] = mapped_column(JSONVariant, default=list)
    retrieval_trace: Mapped[list[dict[str, Any]]] = mapped_column(JSONVariant, default=list)
    model: Mapped[str] = mapped_column(String(64), default="mock-llm")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False, default=utcnow)


class Watchlists(IdMixin, Base):
    __tablename__ = "watchlists"

    name: Mapped[str] = mapped_column(String(64), default="default")
    asset_ids: Mapped[list[str]] = mapped_column(JSONVariant, default=list)  # symbols
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class TradeQuotes(IdMixin, Base):
    __tablename__ = "trade_quotes"

    side: Mapped[str] = mapped_column(String(8))  # buy/sell
    asset_entity_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("entities.id"))
    asset_symbol: Mapped[str] = mapped_column(String(32))
    fiat_amount: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    fiat_currency: Mapped[str] = mapped_column(String(8), default="USD")
    routes: Mapped[list[dict[str, Any]]] = mapped_column(JSONVariant, default=list)
    best_route_index: Mapped[int] = mapped_column(Integer, default=0)
    selected_route: Mapped[dict[str, Any] | None] = mapped_column(JSONVariant, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending/confirmed/executed/cancelled
    # 需求：报价请求的杠杆必须落库，confirm 记账时按此杠杆开仓（否则恒 1x）
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Trades(IdMixin, Base):
    __tablename__ = "trades"

    quote_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trade_quotes.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="executed")  # executed/failed
    filled: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
    paper: Mapped[bool] = mapped_column(default=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class PaperOrders(IdMixin, Base):
    """模拟盘订单：支持市价/限价/止盈/止损 × 现货/永续（杠杆）。"""

    __tablename__ = "paper_orders"

    side: Mapped[str] = mapped_column(
        String(8)
    )  # buy|sell（perp 语义: long|short 归一为 buy|sell）
    asset_symbol: Mapped[str] = mapped_column(String(16), index=True)
    market_type: Mapped[str] = mapped_column(String(8), default="spot")  # spot|perp
    order_type: Mapped[str] = mapped_column(String(8), default="market")  # market|limit|tp|sl
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 8))
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    tp_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    sl_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True
    )  # pending|filled|cancelled
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    fill_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    linked_position_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reduce_only: Mapped[bool] = mapped_column(Boolean, default=False)
    user_key: Mapped[str] = mapped_column(String(64), default="default", index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class Positions(IdMixin, Base):
    """模拟盘永续仓位：PaperEngine 按 netting 逻辑开仓/加仓/减仓/平仓。"""

    __tablename__ = "positions"

    venue: Mapped[str] = mapped_column(String(32), default="paper")
    asset_symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))  # long|short
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 8))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(30, 8))
    leverage: Mapped[int] = mapped_column(Integer, default=1)
    margin_usd: Mapped[Decimal] = mapped_column(Numeric(30, 6), default=Decimal("0"))
    status: Mapped[str] = mapped_column(String(8), default="open", index=True)  # open|closed
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(30, 6), default=Decimal("0"))
    closed_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_key: Mapped[str] = mapped_column(String(64), default="default", index=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


class PaperAccount(IdMixin, TimestampMixin, Base):
    """模拟交易账户（需求⑥）：每用户独立资金与盈亏，交易历史按 user_key 保留。"""

    __tablename__ = "paper_accounts"

    user_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    initial_balance_usd: Mapped[Decimal] = mapped_column(Numeric(30, 2), default=Decimal("100000"))
    # balance_usd 仅记现金口径的当前快照；权益 = initial + realized(全部平仓) + unrealized(持仓)
    realized_pnl_usd: Mapped[Decimal] = mapped_column(Numeric(30, 2), default=Decimal("0"))
    reset_count: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)


# narrative → asset link table (many-to-many, graph-ready)
narrative_assets = Table(
    "narrative_assets",
    Base.metadata,
    Column("narrative_id", ForeignKey("narratives.id"), primary_key=True),
    Column("asset_id", ForeignKey("entities.id"), primary_key=True),
)


class AiBinding(IdMixin, TimestampMixin, Base):
    """用户绑定的模型 API（OpenAI 兼容 / Anthropic）。单活跃绑定：最新一条生效。"""

    __tablename__ = "ai_bindings"

    provider: Mapped[str] = mapped_column(String(24))  # openai_compatible | anthropic
    label: Mapped[str] = mapped_column(String(64), default="")
    base_url: Mapped[str] = mapped_column(String(255))
    api_key: Mapped[str] = mapped_column(String(255))
    model: Mapped[str | None] = mapped_column(String(96), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="unknown", index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONVariant, default=dict)
