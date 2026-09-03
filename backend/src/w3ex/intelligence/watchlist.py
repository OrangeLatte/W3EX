from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.db.models import Watchlists


async def get_watchlist(session: AsyncSession, name: str = "default") -> list[str]:
    row = (
        await session.execute(select(Watchlists).where(Watchlists.name == name))
    ).scalar_one_or_none()
    if row is None:
        return []
    return list(row.asset_ids or [])


async def set_watchlist(
    session: AsyncSession, symbols: list[str], name: str = "default"
) -> list[str]:
    row = (
        await session.execute(select(Watchlists).where(Watchlists.name == name))
    ).scalar_one_or_none()
    if row is None:
        row = Watchlists(name=name, asset_ids=[])
        session.add(row)
    row.asset_ids = list(dict.fromkeys(s.upper() for s in symbols))  # 去重保序
    await session.commit()
    return list(row.asset_ids)
