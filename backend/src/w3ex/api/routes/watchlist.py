from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from w3ex.api.deps import DBSession
from w3ex.intelligence.watchlist import get_watchlist, set_watchlist

router = APIRouter(prefix="/watchlist", tags=["watchlist"])

SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,10}$")


def _user_key(
    user_key: str | None = Header(default=None, alias="X-User-Key"),
) -> str:
    """评审 7.1：watchlist 按 user_id 隔离（浏览器端 X-User-Key）。"""
    return (user_key or "default").strip()[:64] or "default"


class WatchlistUpdate(BaseModel):
    symbols: list[str] = Field(default_factory=list)


@router.get("")
async def read_watchlist(
    session: DBSession,
    user_key: str = Depends(_user_key),  # noqa: B008
) -> list[str]:
    return await get_watchlist(session, name=user_key)


@router.put("")
async def update_watchlist(
    req: WatchlistUpdate,
    session: DBSession,
    user_key: str = Depends(_user_key),  # noqa: B008
) -> list[str]:
    """统一校验：大写规范化 → 格式校验 → 保序去重（前后端唯一性契约以后端为准）。"""
    cleaned: list[str] = []
    for s in req.symbols:
        sym = s.strip().upper()
        if not SYMBOL_RE.fullmatch(sym):
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_symbol", "message": f"非法交易对代码：{s!r}"},
            )
        if sym not in cleaned:
            cleaned.append(sym)
    return await set_watchlist(session, cleaned, name=user_key)
