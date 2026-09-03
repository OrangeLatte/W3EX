from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from w3ex.config import get_settings
from w3ex.db.base import Base


def _make_engine_url(database_url: str) -> str:
    # sqlite 相对路径基于后端工作目录；固定到 backend 目录
    if database_url.startswith("sqlite+aiosqlite:///./"):
        return database_url
    return database_url


_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        url = _make_engine_url(settings.database_url)
        # sqlite 连接绑定线程/loop，跨事件循环复用不安全 → NullPool
        pool = NullPool if url.startswith("sqlite") else None
        _engine = create_async_engine(url, echo=False, poolclass=pool)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


_CREATE_TABLE_MIGRATIONS = [
    # create_all 不会给已存在的表加列；这里按需补列（幂等）
    "ALTER TABLE trade_quotes ADD COLUMN idempotency_key VARCHAR(64)",
    "ALTER TABLE paper_orders ADD COLUMN linked_position_id VARCHAR(36)",
    "ALTER TABLE paper_orders ADD COLUMN reduce_only BOOLEAN",
    # 需求⑥ 模拟账户：按用户隔离
    "ALTER TABLE paper_orders ADD COLUMN user_key VARCHAR(64) DEFAULT 'default'",
    "ALTER TABLE positions ADD COLUMN user_key VARCHAR(64) DEFAULT 'default'",
    # 报价确认按请求杠杆记账（此前硬编码 1x）
    "ALTER TABLE trade_quotes ADD COLUMN leverage INTEGER DEFAULT 1",
]


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for ddl in _CREATE_TABLE_MIGRATIONS:
            with contextlib.suppress(Exception):  # 列已存在
                await conn.exec_driver_sql(ddl)


async def drop_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
