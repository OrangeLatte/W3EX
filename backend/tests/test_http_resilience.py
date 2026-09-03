"""评审落地测试：tickers 去重、错误脱敏、request_id、TTLCache 治理（single-flight / stale-if-error / LRU 上限）。"""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import pytest

import w3ex.providers.coingecko.market as cg_market
import w3ex.providers.http as http_mod
from w3ex.providers.base import ProviderUnavailable
from w3ex.providers.coingecko.market import CoinGeckoProvider
from w3ex.providers.http import TTLCache, fetch_json
from w3ex.providers.mock.market import MockMarketProvider

# ---------- TTLCache ----------


def test_cache_lru_maxsize_eviction():
    cache = TTLCache(maxsize=3)
    for i in range(5):
        cache.set(f"k{i}", i, ttl=60)
    assert len(cache) == 3
    # 最早的 k0/k1 被淘汰
    assert cache.get("k0") is None and cache.get("k1") is None
    assert cache.get("k2") == 2 and cache.get("k4") == 4


def test_cache_stale_access():
    cache = TTLCache()
    cache.set("s", "old", ttl=-1)
    assert cache.get("s") is None  # 过期默认不可见
    assert cache.get("s", allow_stale=True) == "old"


# ---------- single-flight / stale-if-error ----------


class _FakeResp:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.status_code = 200

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, payload: dict | None = None, fail: bool = False) -> None:
        self.calls = 0
        self._payload = payload or {}
        self._fail = fail

    async def request(self, *args, **kwargs):
        self.calls += 1
        if self._fail:
            raise httpx.ConnectError("boom")
        return _FakeResp(self._payload)


import httpx  # noqa: E402


@pytest.mark.asyncio
async def test_single_flight_shares_one_request(monkeypatch):
    client = _FakeClient({"ok": 1})
    monkeypatch.setattr(http_mod, "_get_client", lambda: client)

    async def call():
        return await fetch_json("http://test/x", cache_key="sf:key", ttl=60, retries=0)

    results = await asyncio.gather(*(call() for _ in range(5)))
    assert all(r == {"ok": 1} for r in results)
    assert client.calls == 1


@pytest.mark.asyncio
async def test_stale_if_error(monkeypatch):
    cache = http_mod._CACHE
    cache.set("stale:key", {"price": 1}, ttl=-1)  # 已过期
    client = _FakeClient(fail=True)
    monkeypatch.setattr(http_mod, "_get_client", lambda: client)
    data = await fetch_json("http://test/y", cache_key="stale:key", ttl=60, retries=0)
    assert data == {"price": 1}


@pytest.mark.asyncio
async def test_failure_without_stale_raises(monkeypatch):
    client = _FakeClient(fail=True)
    monkeypatch.setattr(http_mod, "_get_client", lambda: client)
    with pytest.raises(ProviderUnavailable):
        await fetch_json("http://test/z", cache_key="none:key", ttl=60, retries=0)


# ---------- coingecko tickers 去重（USDF duplicate key 根因） ----------


@pytest.mark.asyncio
async def test_coingecko_tickers_dedupe_by_symbol(monkeypatch):
    rows = [
        {
            "symbol": "usdf",
            "current_price": 1.0,
            "price_change_percentage_24h": 0.1,
            "market_cap": 5,
        },
        {
            "symbol": "sol",
            "current_price": 100.0,
            "price_change_percentage_24h": 2.0,
            "market_cap": 9,
        },
        {
            "symbol": "usdf",
            "current_price": 0.5,
            "price_change_percentage_24h": -1.0,
            "market_cap": 2,
        },
    ]

    async def fake_fetch(*args, **kwargs):
        return rows

    monkeypatch.setattr(cg_market, "fetch_json", fake_fetch)
    tickers = await CoinGeckoProvider().get_tickers()
    syms = [t.symbol for t in tickers]
    assert syms == ["USDF", "SOL"]  # 市值高者保留且唯一


# ---------- 错误脱敏 + request_id ----------


@pytest.mark.asyncio
async def test_upstream_error_sanitized(client, monkeypatch):
    async def boom(*args, **kwargs):
        raise ProviderUnavailable("upstream http://secret.internal/api/x -> 500")

    monkeypatch.setattr(MockMarketProvider, "get_candles", boom)
    resp = await client.get("/api/v1/market/klines/BTC")
    assert resp.status_code == 502
    body = resp.json()
    msg = body["detail"]["message"]
    assert "http" not in msg and "secret" not in msg


@pytest.mark.asyncio
async def test_request_id_header(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert "x-request-id" in {k.lower() for k in resp.headers}


# ---------------------------------------------------------------------------
# 熔断器：死源冷却快速失败
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold(monkeypatch):
    calls = {"n": 0}

    async def boom(*args, **kwargs):
        calls["n"] += 1
        raise httpx.ConnectTimeout("dead", request=None)

    monkeypatch.setattr(http_mod._get_client(), "request", boom)
    url = "https://dead.example/api"
    for _ in range(http_mod._CIRCUIT_FAIL_THRESHOLD):
        with pytest.raises(ProviderUnavailable):
            await fetch_json(url, cacheable=False, retries=0)
    assert http_mod._CIRCUIT[urlsplit(url).netloc]["open_until"] > 0

    # 冷却期内：不打网络快速失败（calls 不再增长）
    n_before = calls["n"]
    with pytest.raises(ProviderUnavailable, match="circuit open"):
        await fetch_json(url, cacheable=False, retries=0)
    assert calls["n"] == n_before


@pytest.mark.asyncio
async def test_circuit_success_resets(monkeypatch):
    url = "https://flaky.example/api"

    class _Resp:
        status_code = 200

        def json(self):
            return {"ok": True}

    async def ok(*args, **kwargs):
        return _Resp()

    async def boom(*args, **kwargs):
        raise httpx.ConnectTimeout("dead", request=None)

    monkeypatch.setattr(http_mod._get_client(), "request", boom)
    for _ in range(http_mod._CIRCUIT_FAIL_THRESHOLD - 1):
        with pytest.raises(ProviderUnavailable):
            await fetch_json(url, cacheable=False, retries=0)
    monkeypatch.setattr(http_mod._get_client(), "request", ok)
    assert await fetch_json(url, cacheable=False, retries=0) == {"ok": True}
    assert urlsplit(url).netloc not in http_mod._CIRCUIT
