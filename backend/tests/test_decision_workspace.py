"""Decision Workspace v3：约束报价 / 分阶段完成 / 回放 / watchlist 唯一性。"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.asyncio
async def test_quote_constraints_filter_all(client):
    """max_slippage_bps=1：mock 全部路由滑点 >1bps → 全被过滤，不抛错而是空路由+原因。"""
    r = await client.get(
        "/api/v1/trade/quote",
        params={"side": "buy", "asset": "BTC", "amount": "100", "max_slippage_bps": "1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["routes"] == []
    assert body["best_route_index"] == -1
    assert len(body["filtered_routes"]) >= 1
    assert "超过上限" in body["filtered_routes"][0]["reason"]
    assert body["constraints"]["max_slippage_bps"] == 1


@pytest.mark.asyncio
async def test_quote_constraints_kept_and_risk_fields(client):
    """约束宽松 → 全部合格；每条路由带 data_age_ms 与 worst_receive（风险推演）。"""
    r = await client.get(
        "/api/v1/trade/quote",
        params={"side": "buy", "asset": "BTC", "amount": "100", "max_slippage_bps": "100"},
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["routes"]) >= 1
    assert body["filtered_routes"] == []
    for route in body["routes"]:
        assert "data_age_ms" in route and route["data_age_ms"] >= 0
        assert route["worst_receive"] is not None
        assert float(route["worst_receive"]) < float(route["estimated_receive"])


@pytest.mark.asyncio
async def test_quote_perp_risk_fields(client):
    """perp 报价按 leverage 填充保证金与强平距离。"""
    r = await client.get(
        "/api/v1/trade/quote",
        params={
            "side": "buy",
            "asset": "ETH",
            "amount": "1000",
            "market_type": "perp",
            "leverage": "5",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body["routes"]) >= 1
    route = body["routes"][0]
    assert route["instrument_type"] == "perp"
    assert float(route["margin_required_usd"]) == pytest.approx(
        float(route["total_cost_usd"]) / 5, abs=0.5
    )
    assert route["liquidation_distance_pct"] == 20.0


@pytest.mark.asyncio
async def test_quote_invalid_leverage(client):
    r = await client.get(
        "/api/v1/trade/quote",
        params={"side": "buy", "asset": "BTC", "amount": "100", "leverage": "3"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_confirm_has_execution_stages(client):
    q = (
        await client.get(
            "/api/v1/trade/quote", params={"side": "buy", "asset": "BTC", "amount": "100"}
        )
    ).json()
    c = await client.post(
        "/api/v1/trade/confirm",
        json={"quote_id": q["quote_id"], "route_index": q["best_route_index"]},
    )
    assert c.status_code == 200
    stages = c.json()["execution_stages"]
    assert [s["stage"] for s in stages][0] == "order_accepted"
    assert all(s["simulated"] for s in stages)


@pytest.mark.asyncio
async def test_replay_snapshot_and_counterfactual(client):
    q = (
        await client.get(
            "/api/v1/trade/quote", params={"side": "sell", "asset": "BTC", "amount": "100"}
        )
    ).json()
    await client.post(
        "/api/v1/trade/confirm",
        json={"quote_id": q["quote_id"], "route_index": q["best_route_index"]},
    )
    r = await client.get(f"/api/v1/trade/replay/{q['quote_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "executed"
    assert body["actual"]["paper"] is True
    assert len(body["snapshot_routes"]) == len(q["routes"])
    assert body["selected_venue"]
    for cf in body["counterfactual"]:
        assert "diff_pct" in cf and "would_be_better" in cf


@pytest.mark.asyncio
async def test_replay_not_found(client):
    r = await client.get(f"/api/v1/trade/replay/{uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_watchlist_normalizes_and_dedups(client):
    r = await client.put("/api/v1/watchlist", json={"symbols": ["btc", "BTC", "eth"]})
    assert r.status_code == 200
    assert r.json() == ["BTC", "ETH"]


@pytest.mark.asyncio
async def test_watchlist_rejects_invalid_symbol(client):
    r = await client.put("/api/v1/watchlist", json={"symbols": ["TOOLONGSYMBOLX"]})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "invalid_symbol"


@pytest.mark.asyncio
async def test_confirm_persists_leverage_and_opens_position(client):
    """用户报修锁定：perp 报价选择 5x 杠杆，confirm 成交后订单/仓位必须按 5x 记账。"""
    r = await client.get(
        "/api/v1/trade/quote",
        params={
            "side": "buy",
            "asset": "SOL",
            "amount": "500",
            "market_type": "perp",
            "leverage": "5",
        },
    )
    assert r.status_code == 200
    q = r.json()
    assert q["leverage"] == 5
    c = await client.post(
        "/api/v1/trade/confirm",
        json={"quote_id": q["quote_id"], "route_index": q["best_route_index"]},
    )
    assert c.status_code == 200
    body = c.json()
    assert body["leverage"] == 5
    # 订单按 5x 记账
    orders = (await client.get("/api/v1/trade/orders?status=filled")).json()
    match = [o for o in orders if o["order_id"] and o.get("leverage") == 5]
    assert match, f"expected a 5x order, got {orders}"
    # netting 开仓：positions 表应有 5x 开放仓位
    positions = (await client.get("/api/v1/trade/positions?status=open")).json()
    pos5 = [p for p in positions if p["leverage"] == 5]
    assert pos5, f"expected 5x open position, got {positions}"
