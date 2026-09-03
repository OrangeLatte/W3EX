from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="W3EX_", extra="ignore")

    app_name: str = "w3ex"
    debug: bool = True

    # sqlite+aiosqlite:///./w3ex.db  (dev/test) | postgresql+asyncpg://user:pass@localhost/w3ex
    database_url: str = "sqlite+aiosqlite:///./w3ex.db"
    redis_url: str | None = None  # 预留；无 Redis 自动降级 in-memory

    # Provider 选型：mock | binance | coingecko | rich（组合，真实源优先）
    market_provider: str = "mock"
    # mock | binance | jupiter | hyperliquid | rich（多通道并发报价）
    execution_provider: str = "mock"

    seed_size: str = "small"  # small | full

    # 前端跨域来源（逗号分隔）；本地 dev 默认放行 localhost 常用端口
    cors_origins: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://127.0.0.1:3000,http://127.0.0.1:3002"


@lru_cache
def get_settings() -> Settings:
    return Settings()
