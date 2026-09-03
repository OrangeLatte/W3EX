from __future__ import annotations

from sqlalchemy import func, select

from w3ex.db.models import (
    Entities,
    Narratives,
    News,
    OnchainEvents,
    Prices,
    ProtocolMetrics,
    WalletProfiles,
)


async def test_seed_counts(session) -> None:
    assets = await session.scalar(
        select(func.count()).select_from(Entities).where(Entities.type == "asset")
    )
    events = await session.scalar(select(func.count()).select_from(OnchainEvents))
    prices = await session.scalar(select(func.count()).select_from(Prices))
    news = await session.scalar(select(func.count()).select_from(News))
    narratives = await session.scalar(select(func.count()).select_from(Narratives))
    wallets = await session.scalar(select(func.count()).select_from(WalletProfiles))
    protocols = await session.scalar(select(func.count()).select_from(ProtocolMetrics))

    assert assets >= 25
    assert events >= 500
    assert prices >= 48 * 25
    assert news >= 20
    assert narratives == 8
    assert wallets == 12
    # signals 表保留但已不再生成（研究模块移除）
    assert protocols >= 40


async def test_major_assets_exist(session) -> None:
    for sym in ("BTC", "ETH", "SOL", "USDC", "AAVE", "HYPE"):
        ent = await session.scalar(
            select(Entities).where(Entities.type == "asset", Entities.symbol == sym)
        )
        assert ent is not None, f"missing asset {sym}"


async def test_binance_wallet_verified(session) -> None:
    profile = await session.scalar(
        select(WalletProfiles).where(WalletProfiles.label_verified.is_not(None))
    )
    assert profile is not None
    assert "Binance" in profile.label_verified
