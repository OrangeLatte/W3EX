from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.db.models import PaperAccount, PaperOrders, Positions
from w3ex.providers.base import MarketDataProvider

logger = logging.getLogger(__name__)

MARKET_TYPES = ("spot", "perp")
ORDER_TYPES = ("market", "limit", "tp", "sl")
LEVERAGES = (1, 2, 5, 10, 20)
PAPER_FEE_RATE = Decimal("0.001")
Q8 = Decimal("0.00000001")


class PaperEngine:
    """模拟盘撮合：市价即时成交；限价/止盈/止损由后台循环按实时价格触发。

    评审 P0-3：永续采用仓位模型（netting）——
    - 市价/限价成交自动开仓/加仓/减仓/平仓；
    - TP/SL 必须关联开放仓位（linked_position_id, reduce_only=True），
      服务端校验方向与数量，触发后仅减仓并计入已实现盈亏。
    """

    def __init__(self, market: MarketDataProvider) -> None:
        self.market = market

    # ---------- 下单 ----------

    async def create_order(
        self,
        session: AsyncSession,
        *,
        side: str,
        asset: str,
        order_type: str,
        amount_usd: Decimal,
        market_type: str = "spot",
        limit_price: Decimal | None = None,
        tp_price: Decimal | None = None,
        sl_price: Decimal | None = None,
        leverage: int = 1,
        linked_position_id: str | None = None,
        user_key: str = "default",
    ) -> dict[str, Any]:
        side = side.lower()
        asset = asset.upper()
        market_type = market_type.lower()
        order_type = order_type.lower()

        if side not in ("buy", "sell"):
            raise ValueError("side 必须是 buy/long 或 sell/short")
        if market_type not in MARKET_TYPES:
            raise ValueError("market_type 必须是 spot 或 perp")
        if order_type not in ORDER_TYPES:
            raise ValueError("order_type 必须是 market/limit/tp/sl")
        if amount_usd <= 0:
            raise ValueError("amount_usd 必须为正数")
        if market_type == "perp" and leverage not in LEVERAGES:
            raise ValueError(f"leverage 必须是 {LEVERAGES} 之一")
        if market_type == "spot" and leverage != 1:
            raise ValueError("现货不支持杠杆")
        if order_type in ("limit", "tp", "sl") and limit_price is None:
            raise ValueError(f"{order_type} 订单必须提供 limit_price 触发价")

        position: Positions | None = None
        reduce_only = False
        if order_type in ("tp", "sl"):
            # P0-3：保护单必须归属开放仓位，方向与数量由服务端校验
            if market_type != "perp":
                raise ValueError("止盈/止损仅支持永续仓位")
            if linked_position_id is None:
                raise ValueError("止盈/止损必须关联开放仓位（linked_position_id）")
            position = await session.get(Positions, _uuid(linked_position_id))
            if position is None or position.status != "open":
                raise ValueError("关联仓位不存在或已平仓")
            if position.asset_symbol != asset:
                raise ValueError("保护单资产与仓位资产不一致")
            expected_side = "sell" if position.side == "long" else "buy"
            if side != expected_side:
                raise ValueError(
                    f"保护单方向错误：{position.side} 仓位的保护单应为 {expected_side}"
                )
            reduce_only = True

        # 现货不可做空：卖出必须已有该资产持仓（放在 TP/SL 校验之后，优先级让位）
        if market_type == "spot" and side == "sell":
            held = (
                (
                    await session.execute(
                        select(Positions).where(
                            Positions.asset_symbol == asset,
                            Positions.status == "open",
                            Positions.side == "long",
                            Positions.user_key == user_key,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if held is None:
                raise ValueError("现货卖出需先持有该资产（无持仓可卖）")

        price = await self.market.get_price(asset)
        ref = price.ask if side == "buy" else price.bid
        quantity = (amount_usd / ref).quantize(Q8)

        if reduce_only and position is not None and quantity > position.quantity:
            raise ValueError(f"保护单数量超出仓位数量（仓位 {position.quantity}，请求 {quantity}）")

        order = PaperOrders(
            side=side,
            asset_symbol=asset,
            market_type=market_type,
            order_type=order_type,
            quantity=quantity,
            limit_price=limit_price,
            tp_price=tp_price,
            sl_price=sl_price,
            leverage=leverage if position is None else position.leverage,
            entry_price=ref,
            linked_position_id=str(position.id) if position is not None else None,
            reduce_only=reduce_only,
            user_key=user_key,
            status="pending",
            meta={"ref_price": str(ref), "amount_usd": str(amount_usd)},
        )
        if order_type == "market":
            order.status = "filled"
            order.fill_price = ref
            order.filled_at = datetime.utcnow()
            # 现货与永续统一走 netting 记账（现货=等价 1x 持仓）
            await self._apply_fill(session, order, ref)
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return self._dump(order)

    # ---------- 仓位（P0-3 netting） ----------

    async def _apply_fill(self, session: AsyncSession, order: PaperOrders, fill: Decimal) -> None:
        # 现货同样走 netting（等价杠杆 1x 持仓）：买入=开多，卖出=平多；
        # 否则账户与持仓完全不反映现货成交，用户视角「数字不对」
        pos: Positions | None = None
        if order.reduce_only and order.linked_position_id:
            pos = await session.get(Positions, _uuid(order.linked_position_id))
        else:
            pos = (
                await session.execute(
                    select(Positions)
                    .where(
                        Positions.asset_symbol == order.asset_symbol,
                        Positions.status == "open",
                        Positions.user_key == order.user_key,
                    )
                    .order_by(Positions.ts.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        lev = Decimal(order.leverage) if order.market_type == "perp" else Decimal("1")

        order_dir = Decimal("1") if order.side == "buy" else Decimal("-1")

        if pos is None or pos.status != "open":
            margin = (fill * order.quantity / lev).quantize(Decimal("0.01"))
            session.add(
                Positions(
                    venue="paper",
                    asset_symbol=order.asset_symbol,
                    side="long" if order.side == "buy" else "short",
                    quantity=order.quantity,
                    entry_price=fill,
                    leverage=order.leverage,
                    margin_usd=margin,
                    status="open",
                    user_key=getattr(order, "user_key", None) or "default",
                    meta={"opened_by_order": str(order.id)},
                )
            )
            return

        pos_dir = Decimal("1") if pos.side == "long" else Decimal("-1")
        if pos_dir == order_dir:
            # 加仓：加权 entry
            total_qty = (pos.quantity + order.quantity).quantize(Q8)
            if total_qty > 0:
                pos.entry_price = (
                    (pos.entry_price * pos.quantity + fill * order.quantity) / total_qty
                ).quantize(Q8)
            pos.quantity = total_qty
            pos.margin_usd += (fill * order.quantity / lev).quantize(Decimal("0.01"))
        else:
            # 减仓/平仓
            close_qty = min(order.quantity, pos.quantity)
            # 保证金按平仓比例同步释放（部分平仓时账户可用资金即时反映）
            margin_release = (
                pos.margin_usd * close_qty / pos.quantity if pos.quantity > 0 else Decimal("0")
            ).quantize(Decimal("0.01"))
            pos.margin_usd = (pos.margin_usd - margin_release).quantize(Decimal("0.01"))
            pnl = ((fill - pos.entry_price) * close_qty * Decimal(pos.leverage) * pos_dir).quantize(
                Decimal("0.01")
            )
            # taker 手续费随平仓计入已实现盈亏（开仓费已含在 entry 成本口径外，此处统一收平仓费）
            fee = (fill * close_qty * PAPER_FEE_RATE).quantize(Decimal("0.01"))
            pos.realized_pnl = (pos.realized_pnl + pnl - fee).quantize(Decimal("0.01"))
            pos.quantity = (pos.quantity - close_qty).quantize(Q8)
            if pos.quantity <= 0:
                pos.quantity = Decimal("0")
                pos.status = "closed"
                pos.closed_price = fill
                pos.closed_at = datetime.utcnow()
                pos.margin_usd = Decimal("0")
            elif not order.reduce_only:
                # 反向超额：剩余数量开反向新仓（残余为 0 时不建幽灵仓）
                residual = (order.quantity - close_qty).quantize(Q8)
                if residual > 0:
                    margin = (fill * residual / lev).quantize(Decimal("0.01"))
                    session.add(
                        Positions(
                            venue="paper",
                            asset_symbol=order.asset_symbol,
                            side="long" if order.side == "buy" else "short",
                            quantity=residual,
                            entry_price=fill,
                            leverage=order.leverage,
                            margin_usd=margin,
                            status="open",
                            user_key=getattr(order, "user_key", None) or "default",
                            meta={"opened_by_order": str(order.id)},
                        )
                    )

    # ---------- 触发 ----------

    async def cancel(self, session: AsyncSession, order_id: str) -> dict[str, Any]:
        order = await session.get(PaperOrders, _uuid(order_id))
        if order is None:
            raise KeyError("order 不存在")
        if order.status != "pending":
            raise ValueError(f"订单状态为 {order.status}，不可取消")
        order.status = "cancelled"
        await session.commit()
        return self._dump(order)

    async def check_pending(self, session: AsyncSession) -> list[dict[str, Any]]:
        """后台循环入口：逐个检查 pending 订单是否触发。"""
        rows = (
            (await session.execute(select(PaperOrders).where(PaperOrders.status == "pending")))
            .scalars()
            .all()
        )
        if not rows:
            return []
        price_cache: dict[str, Decimal] = {}
        filled: list[dict[str, Any]] = []
        for o in rows:
            px = price_cache.get(o.asset_symbol)
            if px is None:
                try:
                    px = (await self.market.get_price(o.asset_symbol)).price
                except Exception:  # noqa: BLE001 — 单币种取价失败不阻塞其余订单
                    continue
                price_cache[o.asset_symbol] = px
            fill = self._trigger_fill(o, px)
            if fill is not None:
                o.status = "filled"
                o.fill_price = fill
                o.filled_at = datetime.utcnow()
                await self._apply_fill(session, o, fill)
                filled.append(self._dump(o))
        if filled:
            await session.commit()
        return filled

    def _trigger_fill(self, o: PaperOrders, px: Decimal) -> Decimal | None:
        lp = o.limit_price
        if o.order_type == "limit":
            if o.side == "buy":
                return lp if px <= lp else None
            return lp if px >= lp else None
        if o.order_type == "tp":
            if o.side == "sell":
                return lp if px >= lp else None  # 多单止盈：涨到触发价
            return lp if px <= lp else None  # 空单止盈：跌到触发价
        if o.order_type == "sl":
            if o.side == "sell":
                return lp if px <= lp else None  # 多单止损：跌到触发价
            return lp if px >= lp else None  # 空单止损：涨到触发价
        return None

    # ---------- 查询 ----------

    async def list_orders(
        self, session: AsyncSession, status: str = "all", limit: int = 50, user_key: str = "default"
    ) -> list[dict[str, Any]]:
        stmt = (
            select(PaperOrders)
            .where(PaperOrders.user_key == user_key)
            .order_by(PaperOrders.ts.desc())
            .limit(limit)
        )
        if status != "all":
            stmt = stmt.where(PaperOrders.status == status)
        rows = (await session.execute(stmt)).scalars().all()
        price_cache: dict[str, Decimal] = {}
        out = []
        for o in rows:
            d = self._dump(o)
            if o.market_type == "perp" and o.status in ("pending", "filled"):
                px = price_cache.get(o.asset_symbol)
                if px is None:
                    try:
                        px = (await self.market.get_price(o.asset_symbol)).price
                        price_cache[o.asset_symbol] = px
                    except Exception:  # noqa: BLE001
                        px = None
                if px is not None:
                    d["current_price"] = str(px)
                    if o.entry_price and not o.reduce_only:
                        direction = Decimal("1") if o.side == "buy" else Decimal("-1")
                        pnl = (px - o.entry_price) * o.quantity * o.leverage * direction
                        d["unrealized_pnl_usd"] = str(pnl.quantize(Decimal("0.01")))
            out.append(d)
        return out

    async def list_positions(
        self,
        session: AsyncSession,
        status: str = "open",
        limit: int = 50,
        user_key: str = "default",
    ) -> list[dict[str, Any]]:
        stmt = (
            select(Positions)
            .where(Positions.user_key == user_key)
            .order_by(Positions.ts.desc())
            .limit(limit)
        )
        if status != "all":
            stmt = stmt.where(Positions.status == status)
        rows = (await session.execute(stmt)).scalars().all()
        price_cache: dict[str, Decimal] = {}
        out = []
        for p in rows:
            d = self._dump_position(p)
            if p.status == "open":
                px = price_cache.get(p.asset_symbol)
                if px is None:
                    try:
                        px = (await self.market.get_price(p.asset_symbol)).price
                        price_cache[p.asset_symbol] = px
                    except Exception:  # noqa: BLE001
                        px = None
                if px is not None:
                    d["current_price"] = str(px)
                    pos_dir = Decimal("1") if p.side == "long" else Decimal("-1")
                    upnl = (px - p.entry_price) * p.quantity * p.leverage * pos_dir
                    d["unrealized_pnl_usd"] = str(upnl.quantize(Decimal("0.01")))
                    # 预估强平价（隔离保证金近似：entry×(1∓1/lev)，标注为估算值）
                    liq_ratio = Decimal("1") / Decimal(p.leverage)
                    est = (
                        p.entry_price * (1 - liq_ratio)
                        if p.side == "long"
                        else p.entry_price * (1 + liq_ratio)
                    )
                    d["liquidation_estimate"] = str(est.quantize(Q8))
                    d["liquidation_estimated"] = True
            out.append(d)
        return out

    # ---------- 序列化 ----------

    def _dump(self, o: PaperOrders) -> dict[str, Any]:
        return {
            "order_id": str(o.id),
            "side": o.side,
            "asset": o.asset_symbol,
            "market_type": o.market_type,
            "order_type": o.order_type,
            "quantity": str(o.quantity),
            "limit_price": str(o.limit_price) if o.limit_price else None,
            "tp_price": str(o.tp_price) if o.tp_price else None,
            "sl_price": str(o.sl_price) if o.sl_price else None,
            "leverage": o.leverage,
            "linked_position_id": o.linked_position_id,
            "reduce_only": o.reduce_only,
            "status": o.status,
            "entry_price": str(o.entry_price) if o.entry_price else None,
            "fill_price": str(o.fill_price) if o.fill_price else None,
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
            "fee_rate": str(PAPER_FEE_RATE),
            "paper": True,
            "ts": o.ts.isoformat(),
        }

    def _dump_position(self, p: Positions) -> dict[str, Any]:
        return {
            "position_id": str(p.id),
            "venue": p.venue,
            "asset": p.asset_symbol,
            "side": p.side,
            "quantity": str(p.quantity),
            "entry_price": str(p.entry_price),
            "leverage": p.leverage,
            "margin_usd": str(p.margin_usd),
            "notional_usd": str((p.entry_price * p.quantity).quantize(Decimal("0.01"))),
            "status": p.status,
            "realized_pnl": str(p.realized_pnl),
            "closed_price": str(p.closed_price) if p.closed_price else None,
            "closed_at": p.closed_at.isoformat() if p.closed_at else None,
            "ts": p.ts.isoformat(),
            "paper": True,
        }


def _uuid(s: str):
    import uuid

    return uuid.UUID(s)


# ---------- 模拟账户（需求⑥） ----------

DEFAULT_BALANCE = Decimal("100000")


async def get_or_create_account(session: AsyncSession, user_key: str = "default") -> PaperAccount:
    acct = (
        await session.execute(select(PaperAccount).where(PaperAccount.user_key == user_key))
    ).scalar_one_or_none()
    if acct is None:
        acct = PaperAccount(
            user_key=user_key,
            initial_balance_usd=DEFAULT_BALANCE,
            realized_pnl_usd=Decimal("0"),
            reset_count=0,
        )
        session.add(acct)
        await session.commit()
        await session.refresh(acct)
    return acct


async def reset_account(session: AsyncSession, user_key: str = "default") -> dict[str, Any]:
    """重置：撤销该用户全部挂单并平掉开放仓位（删除）；历史订单记录保留。"""
    acct = await get_or_create_account(session, user_key)
    now = datetime.utcnow()
    await session.execute(
        PaperOrders.__table__.delete().where(
            PaperOrders.user_key == user_key, PaperOrders.status == "pending"
        )
    )
    await session.execute(
        Positions.__table__.delete().where(
            Positions.user_key == user_key, Positions.status == "open"
        )
    )
    acct.reset_count += 1
    acct.updated_at = now
    await session.commit()
    return {
        "user_key": user_key,
        "reset_count": acct.reset_count,
        "cleared": ["pending_orders", "open_positions"],
        "history_retained": True,
        "ts": now.isoformat(),
    }


async def account_summary(
    session: AsyncSession, user_key: str = "default", market: MarketDataProvider | None = None
) -> dict[str, Any]:
    """资产/收益汇总：权益 = 初始资金 + 已实现盈亏（全部仓位） + 未实现盈亏（开放仓位）。"""
    acct = await get_or_create_account(session, user_key)

    realized_total = Decimal("0")
    positions_rows = (
        (
            await session.execute(
                select(Positions).where(Positions.user_key == user_key).order_by(Positions.ts)
            )
        )
        .scalars()
        .all()
    )
    unrealized_total = Decimal("0")
    margin_used = Decimal("0")
    open_count = 0
    price_cache: dict[str, Decimal] = {}
    for p in positions_rows:
        realized_total += Decimal(str(p.realized_pnl))
        if p.status != "open":
            continue
        open_count += 1
        margin_used += Decimal(str(p.margin_usd))
        px = price_cache.get(p.asset_symbol)
        if px is None and market is not None:
            try:
                px = (await market.get_price(p.asset_symbol)).price
            except Exception:  # noqa: BLE001 — 取价失败该仓位不计未实现盈亏
                px = None
            if px is not None:
                price_cache[p.asset_symbol] = px
        if px is None:
            continue
        direction = Decimal("1") if p.side == "long" else Decimal("-1")
        unrealized_total += ((px - p.entry_price) * p.quantity * p.leverage * direction).quantize(
            Decimal("0.01")
        )

    orders_rows = (
        (await session.execute(select(PaperOrders.id).where(PaperOrders.user_key == user_key)))
        .scalars()
        .all()
    )

    initial = Decimal(str(acct.initial_balance_usd))
    equity = (initial + realized_total + unrealized_total).quantize(Decimal("0.01"))
    return {
        "user_key": user_key,
        "initial_balance_usd": str(initial),
        "realized_pnl_usd": str(realized_total.quantize(Decimal("0.01"))),
        "unrealized_pnl_usd": str(unrealized_total),
        "equity_usd": str(equity),
        "total_pnl_usd": str((equity - initial).quantize(Decimal("0.01"))),
        "margin_used_usd": str(margin_used.quantize(Decimal("0.01"))),
        "available_usd": str((equity - margin_used).quantize(Decimal("0.01"))),
        "open_positions": open_count,
        "orders_count": len(orders_rows),
        "reset_count": acct.reset_count,
        "paper": True,
        "ts": datetime.utcnow().isoformat(),
    }


async def paper_engine_loop(market: MarketDataProvider, interval_seconds: float = 5.0) -> None:
    """FastAPI lifespan 后台任务：持续触发 pending 订单。

    所有 Provider（含 mock）都启动调度（评审 P0-4）：
    mock 价格为确定性小时级漂移路径，挂单按该可复现路径触发。
    """
    from w3ex.db.session import get_session_factory

    engine = PaperEngine(market)
    factory = get_session_factory()
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            async with factory() as session:
                filled = await engine.check_pending(session)
                for f in filled:
                    logger.info(
                        "paper order filled: %s %s @ %s", f["side"], f["asset"], f["fill_price"]
                    )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — 后台循环永不退出
            logger.exception("paper engine loop error")
            await asyncio.sleep(interval_seconds)
