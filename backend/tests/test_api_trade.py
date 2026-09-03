from __future__ import annotations

from decimal import Decimal

from w3ex.execution.router import ExecutionRouter
from w3ex.providers.mock.execution import MockExecutionProvider


async def test_quote_and_confirm_paper_fill(client) -> None:
    # 1) 报价
    resp = await client.get("/api/v1/trade/quote?side=buy&asset=ETH&amount=1000")
    assert resp.status_code == 200
    q = resp.json()
    assert q["side"] == "buy"
    # 评审 P0-1：现货报价只含现货通道（cex/dex），perp 不再混入
    assert len(q["routes"]) == 2
    venues = {r["venue"] for r in q["routes"]}
    assert venues == {"binance_cex", "jupiter_dex"}
    assert all(r["instrument_type"] == "spot" for r in q["routes"])
    assert 0 <= q["best_route_index"] < len(q["routes"])
    assert q["recommendation_reason"]

    # 2) 确认 → paper fill
    resp = await client.post(
        "/api/v1/trade/confirm",
        json={"quote_id": q["quote_id"], "route_index": q["best_route_index"]},
    )
    assert resp.status_code == 200
    confirm = resp.json()
    assert confirm["status"] == "executed"
    assert confirm["paper"] is True
    assert confirm["filled"]["venue"]


async def test_quote_cancel(client) -> None:
    resp = await client.get("/api/v1/trade/quote?side=sell&asset=SOL&amount=500")
    q = resp.json()
    resp = await client.post("/api/v1/trade/cancel", json={"quote_id": q["quote_id"]})
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


async def test_double_confirm_rejected(client) -> None:
    resp = await client.get("/api/v1/trade/quote?side=buy&asset=BTC&amount=2000")
    q = resp.json()
    payload = {"quote_id": q["quote_id"], "route_index": 0}
    r1 = await client.post("/api/v1/trade/confirm", json=payload)
    assert r1.status_code == 200
    r2 = await client.post("/api/v1/trade/confirm", json=payload)
    assert r2.status_code == 422


async def test_invalid_quote_id_404(client) -> None:
    resp = await client.post(
        "/api/v1/trade/confirm",
        json={"quote_id": "00000000-0000-0000-0000-000000000000", "route_index": 0},
    )
    assert resp.status_code == 404


async def test_invalid_side_422(client) -> None:
    resp = await client.get("/api/v1/trade/quote?side=hold&asset=ETH&amount=100")
    assert resp.status_code == 422


async def test_router_best_route_cheapest(session) -> None:
    router_ = ExecutionRouter(MockExecutionProvider(), session)
    quote = await router_.get_quote("buy", "SOL", Decimal("1000"))
    costs = [r["total_cost_usd"] for r in quote["routes"]]
    assert float(costs[quote["best_route_index"]]) == min(float(c) for c in costs)
