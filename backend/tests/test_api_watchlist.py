from __future__ import annotations


async def test_watchlist_put_get(client) -> None:
    resp = await client.put("/api/v1/watchlist", json={"symbols": ["BTC", "sol", "ETH", "SOL"]})
    assert resp.status_code == 200
    symbols = resp.json()
    assert symbols == ["BTC", "SOL", "ETH"]  # 大写化 + 去重保序

    resp = await client.get("/api/v1/watchlist")
    assert resp.status_code == 200
    assert resp.json() == ["BTC", "SOL", "ETH"]


async def test_watchlist_default_empty(client) -> None:
    resp = await client.get("/api/v1/watchlist")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_health(client) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
