"""⑥ 模拟账户：用户隔离 / 汇总 / 重置保留历史。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from w3ex.execution.paper import (
    PaperEngine,
    account_summary,
    get_or_create_account,
    reset_account,
)


class FakeMarket:
    """固定价格（b38 测试约定：市价 ask/bid 同价）。"""

    class _Q:
        price = Decimal("100")
        ask = Decimal("100")
        bid = Decimal("100")

    async def get_price(self, asset: str):
        return self._Q()


async def _mk_order(engine, session, user_key: str, side="buy", order_type="market", **kw):
    return await engine.create_order(
        session,
        side=side,
        asset=kw.pop("asset", "TSTA"),
        order_type=order_type,
        amount_usd=Decimal("1000"),
        market_type="perp",
        leverage=5,
        user_key=user_key,
        **kw,
    )


@pytest.mark.asyncio
async def test_account_isolated_per_user(session):
    engine = PaperEngine(FakeMarket())
    await _mk_order(engine, session, "userA")
    await _mk_order(engine, session, "userB")

    sa = await account_summary(session, "userA", market=FakeMarket())
    sb = await account_summary(session, "userB", market=FakeMarket())
    # 各自 1 笔订单、1 个开放仓位，互不可见
    assert sa["orders_count"] == 1 and sb["orders_count"] == 1
    assert sa["open_positions"] == 1 and sb["open_positions"] == 1
    # 同向同价 → unrealized 相同但相互独立；equity = 100000 + 0 + unrealized
    assert sa["initial_balance_usd"] == "100000.00" or sa["initial_balance_usd"] == 100000
    assert float(sa["equity_usd"]) == pytest.approx(
        100000 + float(sa["unrealized_pnl_usd"]), abs=0.01
    )


@pytest.mark.asyncio
async def test_reset_clears_pending_keeps_history(session):
    engine = PaperEngine(FakeMarket())
    await _mk_order(engine, session, "userR", order_type="market")  # 立即成交
    await _mk_order(
        engine, session, "userR", order_type="limit", limit_price=Decimal("90")
    )  # pending
    out = await reset_account(session, "userR")
    assert out["history_retained"] is True
    assert out["reset_count"] == 1
    # 成交历史仍在（orders_count 含 filled），reset 只清 pending 与 open positions
    s = await account_summary(session, "userR", market=FakeMarket())
    assert s["orders_count"] >= 1


@pytest.mark.asyncio
async def test_get_or_create_account_idempotent(session):
    a1 = await get_or_create_account(session, "userX")
    a2 = await get_or_create_account(session, "userX")
    assert str(a1.id) == str(a2.id)
