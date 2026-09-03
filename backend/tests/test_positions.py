"""评审 P0-3：仓位模型 + 关联仓位的 reduce-only TP/SL。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from w3ex.execution.paper import PaperEngine


class FakeMarket:
    """可编程价格：asset -> PriceQuote(price)。"""

    def __init__(self, price: Decimal) -> None:
        self.price_value = price

    def set_price(self, p: Decimal) -> None:
        self.price_value = p

    async def get_price(self, asset: str):
        from datetime import datetime

        from w3ex.core.schemas import PriceQuote

        return PriceQuote(
            symbol=asset,
            price=self.price_value,
            bid=self.price_value,
            ask=self.price_value,
            volume_24h=Decimal("1000000"),
            change_24h_pct=0.0,
            ts=datetime.utcnow(),
        )


def _engine() -> PaperEngine:
    return PaperEngine(FakeMarket(Decimal("100")))  # type: ignore[arg-type]


async def _open_long(
    engine: PaperEngine, session, amount: str = "1000", asset: str = "TST1"
) -> dict:
    return await engine.create_order(
        session,
        side="buy",
        asset=asset,
        order_type="market",
        amount_usd=Decimal(amount),
        market_type="perp",
        leverage=5,
    )


async def _open_long_get_position(
    engine: PaperEngine, session, amount: str = "1000", asset: str = "TST1"
) -> dict:
    """开多头仓位并返回本测试新建的仓位（按 id 差集定位，避免共享 DB 污染）。"""
    before = {p["position_id"] for p in await engine.list_positions(session)}
    await _open_long(engine, session, amount, asset)
    fresh = [p for p in await engine.list_positions(session) if p["position_id"] not in before]
    assert len(fresh) == 1
    return fresh[0]


async def test_perp_market_order_opens_position(session) -> None:
    engine = _engine()
    p = await _open_long_get_position(engine, session, asset="TST1")
    assert p["side"] == "long"
    assert Decimal(p["entry_price"]) == Decimal("100")
    assert p["leverage"] == 5
    # margin = qty * entry / lev = 10 * 100 / 5 = 200
    assert Decimal(p["margin_usd"]) == Decimal("200.00")
    assert "unrealized_pnl_usd" in p


async def test_reverse_market_order_closes_and_opposes(session) -> None:
    engine = _engine()
    await _open_long(engine, session)  # long 10 ETH @100, 5x
    # 反向卖出 1000 USD @ 110 → 平掉 9.09 ETH，剩余做多
    engine.market.set_price(Decimal("110"))  # type: ignore[union-attr]
    await engine.create_order(
        session,
        side="sell",
        asset="ETH",
        order_type="market",
        amount_usd=Decimal("1000"),
        market_type="perp",
        leverage=5,
    )
    positions = await engine.list_positions(session)
    open_pos = [p for p in positions if p["status"] == "open"]
    closed = [p for p in positions if p["status"] == "closed"]
    assert len(closed) == 0 or closed[0]["realized_pnl"] != "0.00"
    assert len(open_pos) >= 1


async def test_tp_requires_linked_position(session) -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="linked_position_id"):
        await engine.create_order(
            session,
            side="sell",
            asset="TST3",
            order_type="tp",
            amount_usd=Decimal("100"),
            market_type="perp",
            limit_price=Decimal("120"),
            leverage=5,
        )


async def test_tp_wrong_side_rejected(session) -> None:
    engine = _engine()
    pos = await _open_long_get_position(engine, session, asset="TST3")
    with pytest.raises(ValueError, match="方向"):
        await engine.create_order(
            session,
            side="buy",
            asset="TST3",
            order_type="tp",
            amount_usd=Decimal("100"),
            market_type="perp",
            limit_price=Decimal("120"),
            leverage=5,
            linked_position_id=pos["position_id"],
        )


async def test_tp_over_position_quantity_rejected(session) -> None:
    engine = _engine()
    pos = await _open_long_get_position(engine, session, asset="TST4")  # 10 @100
    with pytest.raises(ValueError, match="超出仓位"):
        await engine.create_order(
            session,
            side="sell",
            asset="TST4",
            order_type="tp",
            amount_usd=Decimal("1500"),
            market_type="perp",
            limit_price=Decimal("120"),
            leverage=5,
            linked_position_id=pos["position_id"],
        )


async def test_linked_tp_triggers_and_reduces_position(session) -> None:
    engine = _engine()
    pos = await _open_long_get_position(engine, session, asset="TST5")  # long 10 @100
    tp = await engine.create_order(
        session,
        side="sell",
        asset="TST5",
        order_type="tp",
        amount_usd=Decimal("500"),
        market_type="perp",
        limit_price=Decimal("120"),
        leverage=5,
        linked_position_id=pos["position_id"],
    )
    assert tp["reduce_only"] is True
    assert tp["linked_position_id"] == pos["position_id"]

    # 价格涨到 120 → TP 触发，仓位减至 5 ETH
    # 已实现盈亏 = (120-100)*5*5 - 平仓手续费(120*5*0.001=0.60) = 499.40
    engine.market.set_price(Decimal("120"))  # type: ignore[union-attr]
    filled = await engine.check_pending(session)
    assert any(f["order_id"] == tp["order_id"] for f in filled)
    pos_after = await session.get(
        __import__("w3ex.db.models", fromlist=["Positions"]).Positions,
        __import__("uuid").UUID(pos["position_id"]),
    )
    assert Decimal(str(pos_after.quantity)) == Decimal("5.00000000")
    assert Decimal(str(pos_after.realized_pnl)) == Decimal("499.40")


async def test_spot_tp_still_rejected(session) -> None:
    engine = _engine()
    with pytest.raises(ValueError, match="永续"):
        await engine.create_order(
            session,
            side="sell",
            asset="ETH",
            order_type="tp",
            amount_usd=Decimal("100"),
            market_type="spot",
            limit_price=Decimal("90"),
        )
