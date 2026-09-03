"""PaperEngine 触发逻辑测试（全离线，mock 行情）。"""

from decimal import Decimal

import pytest

from w3ex.execution.paper import PaperEngine


class FakeMarket:
    def __init__(self, price: str) -> None:
        self.p = Decimal(price)

    async def get_price(self, asset: str):
        from datetime import datetime

        from w3ex.core.schemas import PriceQuote

        return PriceQuote(
            symbol=asset,
            price=self.p,
            bid=self.p * Decimal("0.999"),
            ask=self.p * Decimal("1.001"),
            volume_24h=Decimal("1000000"),
            change_24h_pct=0.0,
            ts=datetime.utcnow(),
        )


@pytest.fixture
def engine():
    return PaperEngine(FakeMarket("100"))


async def _make(session, engine, **kw):
    defaults = dict(
        side="buy",
        asset="BTC",
        order_type="limit",
        amount_usd=Decimal("1000"),
        market_type="spot",
        limit_price=Decimal("95"),
    )
    defaults.update(kw)
    return await engine.create_order(session, **defaults)


async def test_market_order_fills_immediately(session, engine):
    o = await _make(session, engine, order_type="market", limit_price=None)
    assert o["status"] == "filled"
    assert Decimal(o["fill_price"]) == Decimal("100.1")  # ask = 100*1.001
    assert o["paper"] is True


async def test_limit_buy_triggers_when_price_drops(session, engine):
    o = await _make(session, engine, limit_price=Decimal("95"))
    assert o["status"] == "pending"
    # 价格未到 → 不触发
    assert await engine.check_pending(session) == []
    # 价格跌破限价 → 触发，按限价成交
    engine.market = FakeMarket("94")
    filled = await engine.check_pending(session)
    mine = [x for x in filled if x["order_id"] == o["order_id"]]
    assert len(mine) == 1
    assert Decimal(mine[0]["fill_price"]) == Decimal("95")
    assert mine[0]["status"] == "filled"


async def test_limit_sell_triggers_when_price_rises(session, engine):
    o = await _make(session, engine, side="sell", limit_price=Decimal("105"))
    engine.market = FakeMarket("106")
    filled = await engine.check_pending(session)
    mine = [x for x in filled if x["order_id"] == o["order_id"]]
    assert len(mine) == 1 and Decimal(mine[0]["fill_price"]) == Decimal("105")


async def _open_position_and_protect(session, engine, **kw):
    """P0-3：TP/SL 必须关联开放仓位。先开 5x 多头仓位再挂保护单。"""
    await engine.create_order(
        session,
        side="buy",
        asset="BTC",
        order_type="market",
        amount_usd=Decimal("1000"),
        market_type="perp",
        leverage=5,
    )
    pos = (await engine.list_positions(session))[0]
    defaults = dict(
        side="sell",
        asset="BTC",
        order_type="tp",
        amount_usd=Decimal("500"),
        market_type="perp",
        limit_price=Decimal("110"),
        leverage=5,
        linked_position_id=pos["position_id"],
    )
    defaults.update(kw)
    return await engine.create_order(session, **defaults)


async def test_tp_triggers_on_rise_and_sl_ignores(session, engine):
    tp = await _open_position_and_protect(session, engine, order_type="tp")
    sl = await _open_position_and_protect(
        session, engine, order_type="sl", limit_price=Decimal("90")
    )
    engine.market = FakeMarket("111")
    filled = {x["order_id"]: x["order_type"] for x in await engine.check_pending(session)}
    assert filled.get(tp["order_id"]) == "tp"
    assert sl["order_id"] not in filled


async def test_sl_triggers_on_drop(session, engine):
    sl = await _open_position_and_protect(
        session, engine, order_type="sl", limit_price=Decimal("90")
    )
    engine.market = FakeMarket("89")
    filled = await engine.check_pending(session)
    mine = [x for x in filled if x["order_id"] == sl["order_id"]]
    assert len(mine) == 1 and mine[0]["order_type"] == "sl"


async def test_perp_leverage_and_pnl(session, engine):
    o = await _make(
        session,
        engine,
        side="buy",
        order_type="market",
        market_type="perp",
        leverage=10,
        limit_price=None,
    )
    assert o["leverage"] == 10
    lst = await engine.list_orders(session)
    mine = [x for x in lst if x["order_id"] == o["order_id"]][0]
    # 10x 多头：PnL = (cur - entry) * qty * 10
    entry = Decimal(o["fill_price"])
    cur = Decimal(mine["current_price"])
    expected = (cur - entry) * Decimal(o["quantity"]) * 10
    assert Decimal(mine["unrealized_pnl_usd"]) == expected.quantize(Decimal("0.01"))


async def test_cancel_pending_only(session, engine):
    o = await _make(session, engine)
    res = await engine.cancel(session, o["order_id"])
    assert res["status"] == "cancelled"
    with pytest.raises(ValueError, match="不可取消"):
        await engine.cancel(session, o["order_id"])


async def test_invalid_inputs(session, engine):
    with pytest.raises(ValueError, match="leverage"):
        await _make(
            session, engine, market_type="perp", leverage=3, limit_price=None, order_type="market"
        )
    with pytest.raises(ValueError, match="limit_price"):
        await _make(session, engine, order_type="tp", limit_price=None)
    with pytest.raises(ValueError, match="杠杆"):
        await _make(
            session, engine, market_type="spot", leverage=2, order_type="market", limit_price=None
        )


async def test_no_rows_fast_path(session, engine):
    assert await engine.check_pending(session) == []
