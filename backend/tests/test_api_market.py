from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_market_overview_shape(client):
    resp = await client.get("/api/v1/market/overview")
    assert resp.status_code == 200
    data = resp.json()
    for key in (
        "as_of",
        "global_stats",
        "regime",
        "indices",
        "gainers",
        "losers",
        "volume_leaders",
        "funding",
        "liquidations",
        "sources",
    ):
        assert key in data, f"overview 缺少 {key}"
    assert data["regime"]["regime"] in ("risk_on", "risk_off", "neutral")
    for sym in ("BTC", "ETH", "SOL"):
        assert sym in data["indices"]
    assert len(data["gainers"]) >= 3
    assert len(data["losers"]) >= 3
    assert len(data["volume_leaders"]) >= 3
    # 排序正确性
    changes = [row["change_24h_pct"] for row in data["gainers"]]
    assert changes == sorted(changes, reverse=True)
    liquidations = data["liquidations"]
    assert liquidations and "amount_usd" in liquidations[0]


async def test_market_tickers(client):
    resp = await client.get("/api/v1/market/tickers?assets=BTC,ETH,SOL")
    assert resp.status_code == 200
    rows = resp.json()
    assert {r["symbol"] for r in rows} == {"BTC", "ETH", "SOL"}
    for r in rows:
        assert r["price"] > 0
        assert "change_24h_pct" in r and "volume_24h_usd" in r


async def test_market_klines(client):
    resp = await client.get("/api/v1/market/klines/BTC?interval=1h&limit=48")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 48
    candle = rows[-1]
    assert {"ts", "o", "h", "l", "c", "v"} <= set(candle)
    assert candle["h"] >= candle["l"]


async def test_market_depth(client):
    resp = await client.get("/api/v1/market/depth/BTC?limit=10")
    assert resp.status_code == 200
    snap = resp.json()
    assert len(snap["bids"]) == 10 and len(snap["asks"]) == 10
    assert snap["bids"][0][0] < snap["asks"][0][0]  # bid < ask


async def test_market_funding(client):
    resp = await client.get("/api/v1/market/funding?limit=5")
    assert resp.status_code == 200
    rows = resp.json()
    assert 0 < len(rows) <= 5
    assert {"symbol", "rate", "mark_price"} <= set(rows[0])
