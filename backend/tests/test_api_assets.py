from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_asset_detail_shape(client):
    resp = await client.get("/api/v1/assets/SOL")
    assert resp.status_code == 200
    data = resp.json()
    assert data["symbol"] == "SOL"
    assert data["name"]
    assert data["price"] > 0
    assert "change_24h_pct" in data and "change_1h_pct" in data
    assert len(data["candles"]) >= 24
    candle = data["candles"][-1]
    assert {"ts", "o", "h", "l", "c", "v"} <= set(candle)
    stats = data["stats"]
    assert {"market_cap", "market_cap_rank", "volume_24h_usd"} <= set(stats)
    assert stats["market_cap"] and stats["market_cap"] > 0
    # depth 可能为 None（真实源不可达）或含 bids/asks
    if data["depth"] is not None:
        assert {"bids", "asks"} <= set(data["depth"])
    # funding_rate 可能为 None 或 float
    assert data["funding_rate"] is None or isinstance(data["funding_rate"], float)
    assert data["sources"]["market"] == "mock"  # 测试环境默认 mock


async def test_asset_detail_interval_switch(client):
    resp = await client.get("/api/v1/assets/BTC?interval=1d&limit=30")
    assert resp.status_code == 200


async def test_asset_detail_interval_rejected(client):
    resp = await client.get("/api/v1/assets/BTC?interval=3m")
    assert resp.status_code == 422
