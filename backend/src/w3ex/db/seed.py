from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.core import repository as repo
from w3ex.db.models import (
    AssetsMeta,
    NarrativeEvents,
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
from w3ex.providers.mock.generator import (
    ASSETS,
    EXCHANGES,
    NARRATIVE_MEMBERS,
    NARRATIVES,
    PROTOCOLS,
    WALLET_PROFILES,
    MockDataset,
)

CHAIN_FOR_SYMBOL = {
    "SOL": "solana",
    "JUP": "solana",
    "JTO": "solana",
    "PYTH": "solana",
    "WIF": "solana",
    "BONK": "solana",
    "USDC": "ethereum",
    "USDT": "ethereum",
}


async def seed_database(
    session: AsyncSession, dataset: MockDataset | None = None
) -> dict[str, int]:
    """把 mock 数据集写入规范库。幂等：先清空业务表。"""
    ds = dataset or MockDataset()
    counts: dict[str, int] = {}
    await repo.clear_all(session)

    # ---- entities: assets ----
    asset_ids: dict[str, uuid.UUID] = {}
    for a in ASSETS:
        ent = await repo.upsert_entity(
            session,
            etype="asset",
            symbol=a["symbol"],
            name=a["name"],
            chain=CHAIN_FOR_SYMBOL.get(a["symbol"], a.get("chain", "ethereum")),
            metadata_={"category": a["category"], "mcap": a["mcap"]},
        )
        asset_ids[a["symbol"]] = ent.id
        session.add(
            AssetsMeta(
                entity_id=ent.id,
                market_cap=Decimal(str(a["mcap"])),
                rank=list(ASSETS).index(a) + 1,
                category=a["category"],
            )
        )
    counts["assets"] = len(ASSETS)

    # ---- entities: exchanges / protocols ----
    for ex in EXCHANGES:
        await repo.upsert_entity(session, etype="exchange", name=ex, symbol=None)
    proto_ids: dict[str, uuid.UUID] = {}
    for p in PROTOCOLS:
        ent = await repo.upsert_entity(
            session,
            etype="protocol",
            name=p["name"],
            symbol=p["name"].upper(),
            chain=p["chain"],
            metadata_={"category": p["category"]},
        )
        proto_ids[p["name"]] = ent.id
    counts["protocols"] = len(PROTOCOLS)

    # ---- prices (48h hourly) ----
    price_rows = 0
    for a in ASSETS:
        ent_id = asset_ids[a["symbol"]]
        for c in ds.candles(a["symbol"], limit=48):
            session.add(
                Prices(
                    entity_id=ent_id,
                    ts=c.ts,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume,
                    source="mock",
                )
            )
            price_rows += 1
    counts["prices"] = price_rows

    # ---- onchain events ----
    for e in ds._build_events():
        session.add(
            OnchainEvents(
                chain=e["chain"],
                block=None,
                tx_hash=e["tx_hash"],
                event_type=e["event_type"],
                asset_entity_id=asset_ids.get(e["asset_symbol"]),
                amount=e["amount"],
                from_entity_id=None,
                to_entity_id=None,
                value_usd=e["value_usd"],
                significance=e["significance"],
                source="mock",
                ts=e["ts"],
            )
        )
    counts["onchain_events"] = len(ds._build_events())

    # ---- wallets ----
    wallet_ids: dict[str, uuid.UUID] = {}
    for w in WALLET_PROFILES:
        ent = await repo.upsert_entity(
            session,
            etype="wallet",
            symbol=None,
            address=w["address"],
            name=w["name"],
            metadata_={"tags": w["tags"]},
        )
        wallet_ids[w["address"]] = ent.id
        session.add(
            WalletProfiles(
                wallet_entity_id=ent.id,
                label_verified=w["verified"],
                classification=w["classification"],
                behavior_tags=w["tags"],
                trading_frequency=w["freq"],
                favorite_assets=w["favorites"],
                pnl_est=Decimal(str(w["pnl"])) if w["pnl"] is not None else None,
            )
        )
        for bal in ds._wallet_holdings(w["address"]):
            session.add(
                WalletSnapshots(
                    wallet_entity_id=ent.id,
                    asset_entity_id=asset_ids[bal.asset_symbol],
                    balance=bal.balance,
                    value_usd=bal.value_usd,
                    ts=ds.now,
                )
            )
        for tx in ds.wallet_transactions(w["address"], limit=20):
            session.add(
                WalletTxns(
                    wallet_entity_id=ent.id,
                    tx_hash=tx.tx_hash,
                    asset_entity_id=asset_ids.get(tx.asset_symbol or ""),
                    side="receive",
                    amount=tx.value,
                    counterparty_entity_id=None,
                    value_usd=tx.value_usd,
                    ts=tx.ts,
                )
            )
    counts["wallets"] = len(WALLET_PROFILES)

    # ---- protocol metrics ----
    for p in PROTOCOLS:
        for m in ds.protocol_metrics(p["name"]):
            session.add(
                ProtocolMetrics(
                    protocol_entity_id=proto_ids[p["name"]],
                    metric=m.metric,
                    value=m.value,
                    ts=m.ts,
                    source="mock",
                )
            )
    counts["protocol_metrics"] = len(PROTOCOLS) * 96

    # ---- news ----
    for n in ds.news(hours=48, limit=50):
        session.add(
            News(
                title=n.title,
                summary=n.summary,
                url=n.url,
                source=n.source,
                sentiment=n.sentiment,
                importance=n.importance,
                entity_ids=n.entity_symbols,
                ts=n.ts,
            )
        )
    counts["news"] = len(ds.news(hours=48, limit=50))

    # ---- narratives + links ----
    nar_ids: dict[str, uuid.UUID] = {}
    for name in NARRATIVES:
        ent = await repo.upsert_entity(session, etype="narrative", name=name, symbol=None)
        nar_ids[name] = ent.id
    for name in NARRATIVES:
        momentum, trend, confidence = _narrative_metrics(ds, name)
        row = (
            await session.execute(select(Narratives).where(Narratives.name == name))
        ).scalar_one_or_none()
        if row is None:
            row = Narratives(name=name)
            session.add(row)
        row.momentum_score = momentum
        row.trend = trend
        row.confidence = confidence
        row.drivers = _narrative_drivers(ds, name)
        row.related_asset_ids = NARRATIVE_MEMBERS[name]
        await session.flush()
        for sym in NARRATIVE_MEMBERS[name]:
            await session.execute(
                narrative_assets.insert().values(narrative_id=row.id, asset_id=asset_ids[sym])
            )
        session.add(
            NarrativeEvents(
                narrative_id=row.id,
                event_type="narrative_update",
                payload={"momentum": momentum, "trend": trend},
                ts=ds.now,
            )
        )
    counts["narratives"] = len(NARRATIVES)

    await session.commit()
    return counts


def _narrative_metrics(ds: MockDataset, name: str) -> tuple[float, str, float]:
    members = NARRATIVE_MEMBERS.get(name, [])
    returns = [ds.price(s).change_24h_pct for s in members]
    avg_ret = sum(returns) / len(returns) if returns else 0.0
    momentum = min(100.0, max(0.0, 50.0 + avg_ret * 5.0))
    trend = "rising" if avg_ret > 2 else "falling" if avg_ret < -2 else "flat"
    confidence = min(0.95, 0.45 + 0.05 * len(members))
    return round(momentum, 1), trend, round(confidence, 2)


def _narrative_drivers(ds: MockDataset, name: str) -> list[dict]:
    members = NARRATIVE_MEMBERS.get(name, [])
    drivers = []
    for s in members[:3]:
        p = ds.price(s)
        drivers.append({"asset": s, "change_24h_pct": p.change_24h_pct})
    return drivers
