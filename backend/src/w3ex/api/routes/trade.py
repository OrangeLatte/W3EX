from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from w3ex.api.deps import DBSession, ProvidersDep
from w3ex.execution.paper import PaperEngine
from w3ex.execution.router import ExecutionRouter

router = APIRouter(prefix="/trade", tags=["trade"])


def _user_key(user_key: str | None = Header(default=None, alias="X-User-Key")) -> str:
    """需求⑥：用户标识由前端生成（localStorage uuid），经 X-User-Key 头透传；缺省 default。"""
    k = (user_key or "default").strip()[:64]
    return k or "default"


class ConfirmRequest(BaseModel):
    quote_id: str
    route_index: int = Field(default=0, ge=0)


class CancelRequest(BaseModel):
    quote_id: str


def _parse_decimal(value: str, field: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{field} 不是合法金额") from exc


@router.get("/quote")
async def quote(
    side: str,
    asset: str,
    amount: str,
    session: DBSession,
    providers: ProvidersDep,
    market_type: str = "spot",
    max_slippage_bps: int = 0,
    max_data_age_ms: int = 0,
    leverage: int = 1,
) -> dict:
    try:
        # 评审工程项：金额以 Decimal 字符串承载，不走 float
        amount_dec = _parse_decimal(amount, "amount")
        router_ = ExecutionRouter(providers.execution, session, providers.market)
        return await router_.get_quote(
            side,
            asset,
            amount_dec,
            market_type=market_type.lower(),
            max_slippage_bps=max_slippage_bps,
            max_data_age_ms=max_data_age_ms,
            leverage=leverage,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_request", "message": str(exc)}
        ) from exc
    except Exception as exc:  # noqa: BLE001 — ProviderUnavailable → 503
        raise HTTPException(
            status_code=503,
            detail={"code": "no_route", "message": "上游数据源暂不可用，请稍后重试"},
        ) from exc


@router.get("/replay/{quote_id}")
async def replay_quote(quote_id: str, session: DBSession, providers: ProvidersDep) -> dict:
    try:
        router_ = ExecutionRouter(providers.execution, session)
        return await router_.replay(quote_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_request", "message": str(exc)}
        ) from exc


@router.post("/confirm")
async def confirm(
    req: ConfirmRequest,
    session: DBSession,
    providers: ProvidersDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_key: str = Depends(_user_key),
) -> dict:
    try:
        router_ = ExecutionRouter(providers.execution, session, providers.market)
        return await router_.confirm(req.quote_id, req.route_index, idempotency_key, user_key)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_state", "message": str(exc)}
        ) from exc


@router.post("/cancel")
async def cancel(req: CancelRequest, session: DBSession, providers: ProvidersDep) -> dict:
    try:
        router_ = ExecutionRouter(providers.execution, session)
        return await router_.cancel(req.quote_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_state", "message": str(exc)}
        ) from exc


class OrderRequest(BaseModel):
    side: str  # buy|sell（perp 语义 long|short）
    asset: str
    order_type: str = "market"  # market|limit|tp|sl
    amount_usd: str = Field(...)  # Decimal 字符串
    market_type: str = "spot"  # spot|perp
    limit_price: str | None = None
    tp_price: str | None = None
    sl_price: str | None = None
    leverage: int = 1
    linked_position_id: str | None = None  # P0-3：TP/SL 必须关联开放仓位


def _paper_engine(providers: ProvidersDep) -> PaperEngine:
    return PaperEngine(providers.market)


@router.post("/order")
async def create_order(
    req: OrderRequest,
    session: DBSession,
    providers: ProvidersDep,
    user_key: str = Depends(_user_key),
) -> dict:
    try:
        return await _paper_engine(providers).create_order(
            session,
            side=req.side,
            asset=req.asset,
            order_type=req.order_type,
            amount_usd=_parse_decimal(req.amount_usd, "amount_usd"),
            market_type=req.market_type,
            limit_price=_parse_decimal(req.limit_price, "limit_price") if req.limit_price else None,
            tp_price=_parse_decimal(req.tp_price, "tp_price") if req.tp_price else None,
            sl_price=_parse_decimal(req.sl_price, "sl_price") if req.sl_price else None,
            leverage=req.leverage,
            linked_position_id=req.linked_position_id,
            user_key=user_key,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_request", "message": str(exc)}
        ) from exc


@router.get("/orders")
async def list_orders(
    session: DBSession,
    providers: ProvidersDep,
    status: str = "all",
    user_key: str = Depends(_user_key),
) -> list[dict]:
    try:
        return await _paper_engine(providers).list_orders(session, status=status, user_key=user_key)
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_request", "message": str(exc)}
        ) from exc


@router.delete("/orders/{order_id}")
async def delete_order(order_id: str, session: DBSession, providers: ProvidersDep) -> dict:
    try:
        return await _paper_engine(providers).cancel(session, order_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "not_found", "message": str(exc)}
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_state", "message": str(exc)}
        ) from exc


@router.get("/positions")
async def list_positions(
    session: DBSession,
    providers: ProvidersDep,
    status: str = "open",
    user_key: str = Depends(_user_key),
) -> list[dict]:
    return await _paper_engine(providers).list_positions(session, status=status, user_key=user_key)


@router.get("/account")
async def get_account(
    session: DBSession,
    providers: ProvidersDep,
    user_key: str = Depends(_user_key),
) -> dict:
    """模拟账户资产/收益汇总（需求⑥）。"""
    from w3ex.execution.paper import account_summary

    return await account_summary(session, user_key, market=providers.market)


@router.post("/account/reset")
async def reset_account(
    session: DBSession,
    providers: ProvidersDep,
    user_key: str = Depends(_user_key),
) -> dict:
    """重置模拟账户：撤销挂单+平掉持仓，历史交易记录保留。"""
    from w3ex.execution.paper import reset_account

    return await reset_account(session, user_key)
