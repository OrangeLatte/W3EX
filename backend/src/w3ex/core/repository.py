from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.db.models import (
    Entities,
    IntelSignals,
    Narratives,
    News,
    OnchainEvents,
    Prices,
    ProtocolMetrics,
    WalletProfiles,
    WalletSnapshots,
    WalletTxns,
    narrative_assets,
)


async def upsert_entity(
    session: AsyncSession,
    etype: str,
    symbol: str | None = None,
    address: str | None = None,
    name: str | None = None,
    chain: str | None = None,
    metadata_: dict | None = None,
) -> Entities:
    """按 (type, symbol) 或 (type, address) 幂等获取或创建实体。"""
    if address:
        existing = await session.scalar(
            select(Entities).where(Entities.type == etype, Entities.address == address)
        )
    else:
        existing = await session.scalar(
            select(Entities).where(Entities.type == etype, Entities.symbol == symbol)
        )
    if existing:
        return existing
    ent = Entities(
        type=etype,
        name=name or symbol or (address[:20] if address else "unknown"),
        symbol=symbol,
        address=address,
        chain=chain,
        metadata_=metadata_ or {},
    )
    session.add(ent)
    await session.flush()
    return ent


async def get_entity(
    session: AsyncSession,
    symbol: str | None = None,
    address: str | None = None,
    etype: str | None = None,
) -> Entities | None:
    q = select(Entities)
    if etype:
        q = q.where(Entities.type == etype)
    if symbol:
        q = q.where(Entities.symbol == symbol.upper())
    if address:
        q = q.where(Entities.address == address)
    return await session.scalar(q)


async def clear_all(session: AsyncSession) -> None:
    """清空全部业务表（seed 幂等用），保留元数据。"""
    for model in (
        WalletTxns,
        WalletSnapshots,
        WalletProfiles,
        OnchainEvents,
        Prices,
        ProtocolMetrics,
        News,
        IntelSignals,
        narrative_assets,
        Narratives,
    ):
        await session.execute(delete(model))
    await session.execute(delete(Entities))
    await session.commit()


# ---------- prices ----------


async def insert_price(session: AsyncSession, entity_id: uuid.UUID, candle: Any) -> None:
    session.add(
        Prices(
            entity_id=entity_id,
            ts=candle.ts,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
            source="mock",
        )
    )


async def latest_price(session: AsyncSession, symbol: str) -> Prices | None:
    ent = await get_entity(session, symbol=symbol, etype="asset")
    if ent is None:
        return None
    return await session.scalar(
        select(Prices).where(Prices.entity_id == ent.id).order_by(Prices.ts.desc()).limit(1)
    )


async def price_change_pct(session: AsyncSession, symbol: str, hours: int = 24) -> float | None:
    ent = await get_entity(session, symbol=symbol, etype="asset")
    if ent is None:
        return None
    rows = (
        (
            await session.execute(
                select(Prices)
                .where(Prices.entity_id == ent.id)
                .order_by(Prices.ts.desc())
                .limit(hours + 1)
            )
        )
        .scalars()
        .all()
    )
    if len(rows) < 2:
        return None
    newest, oldest = float(rows[0].close), float(rows[-1].open)
    if oldest == 0:
        return None
    return (newest - oldest) / oldest * 100


async def price_series(session: AsyncSession, symbol: str, hours: int = 48) -> list[Prices]:
    ent = await get_entity(session, symbol=symbol, etype="asset")
    if ent is None:
        return []
    return list(
        (
            await session.execute(
                select(Prices)
                .where(Prices.entity_id == ent.id)
                .order_by(Prices.ts.desc())
                .limit(hours)
            )
        ).scalars()
    )[::-1]


# ---------- signals ----------


async def add_signal(
    session: AsyncSession,
    *,
    signal_type: str,
    title: str,
    description: str | None,
    asset_entity_id: uuid.UUID | None,
    scores: dict[str, float],
    priority: float,
    source: str = "mock",
    ts: datetime | None = None,
) -> IntelSignals:
    sig = IntelSignals(
        signal_type=signal_type,
        asset_entity_id=asset_entity_id,
        title=title,
        description=description,
        scores=scores,
        priority=priority,
        source=source,
        ts=ts or datetime.utcnow(),
    )
    session.add(sig)
    return sig
