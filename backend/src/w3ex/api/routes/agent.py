"""AI 交易教练路由（评审 PDF 6.2）：四类 Agent。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from w3ex.api.deps import DBSession, ProvidersDep
from w3ex.api.routes.trade import _user_key
from w3ex.intelligence.agent import AGENT_KINDS, AGENT_META, run_agent

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentChatRequest(BaseModel):
    message: str = Field(default="", max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)
    lang: str = Field(default="zh", pattern="^(zh|en|fr|es|ar|ru)$")


@router.get("")
async def list_agents() -> dict:
    return {"agents": [{"kind": k, **AGENT_META[k]} for k in AGENT_KINDS]}


@router.post("/{kind}")
async def agent_chat(
    kind: str,
    req: AgentChatRequest,
    session: DBSession,
    providers: ProvidersDep,
    user_key: str = Depends(_user_key),
) -> dict:
    try:
        return await run_agent(
            session, kind, req.message, req.history, providers.market, user_key, lang=req.lang
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": str(exc)}
        ) from exc
