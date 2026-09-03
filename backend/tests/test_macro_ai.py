"""宏观模块 + AI 绑定/简报/对话 测试（全部离线，monkeypatch 网络层）。"""

from __future__ import annotations

import pytest

from w3ex.providers.llm.client import LLMClient
from w3ex.providers.worldbank.macro import WorldBankProvider
from w3ex.providers.yahoo.market import YahooProvider

# ---------- macro ----------


@pytest.mark.asyncio
async def test_macro_overview_success(client, monkeypatch):
    async def fake_indices(self):
        return [
            {
                "symbol": "SPX",
                "yahoo_symbol": "^GSPC",
                "name": "标普500",
                "price": 5000.0,
                "change_pct": 0.5,
                "ts": "2026-01-01T00:00:00",
            }
        ]

    async def fake_cmdty(self):
        return [
            {
                "symbol": "XAU",
                "yahoo_symbol": "GC=F",
                "name": "黄金",
                "price": 2300.0,
                "change_pct": -0.2,
                "ts": "2026-01-01T00:00:00",
            }
        ]

    async def fake_macro(self):
        return {
            "countries": [
                {
                    "iso3": "USA",
                    "name": "美国",
                    "metrics": {"gdp_growth": {"value": 2.5, "year": 2024}},
                }
            ],
            "source": "worldbank",
            "note": "",
        }

    monkeypatch.setattr(YahooProvider, "get_indices", fake_indices)
    monkeypatch.setattr(YahooProvider, "get_commodities", fake_cmdty)
    monkeypatch.setattr(WorldBankProvider, "get_macro_overview", fake_macro)
    r = await client.get("/api/v1/macro/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["indices"][0]["symbol"] == "SPX"
    assert body["commodities"][0]["name"] == "黄金"
    assert body["macro"]["countries"][0]["iso3"] == "USA"
    assert body["sources"] == {"indices": "yahoo", "commodities": "yahoo", "macro": "worldbank"}


@pytest.mark.asyncio
async def test_macro_overview_degrades(client, monkeypatch):
    async def boom(self):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(YahooProvider, "get_indices", boom)
    monkeypatch.setattr(YahooProvider, "get_commodities", boom)
    monkeypatch.setattr(WorldBankProvider, "get_macro_overview", boom)
    r = await client.get("/api/v1/macro/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["indices"] == [] and body["commodities"] == [] and body["macro"] is None
    assert set(body["sources"].values()) == {"unavailable"}


# ---------- ai bind ----------


@pytest.mark.asyncio
async def test_ai_bind_rejected_on_validation_failure(client, monkeypatch):
    async def bad_validate(self):
        return {"ok": False, "models": [], "error": "401 unauthorized"}

    monkeypatch.setattr(LLMClient, "validate", bad_validate)
    r = await client.post(
        "/api/v1/ai/bind",
        json={
            "provider": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-12345678",
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "bind_failed"


@pytest.mark.asyncio
async def test_ai_bind_success_and_status(client, monkeypatch):
    async def ok_validate(self):
        return {"ok": True, "models": ["gpt-x", "gpt-y"], "error": None}

    async def ok_list_models(self):
        return ["gpt-x", "gpt-y"]

    monkeypatch.setattr(LLMClient, "validate", ok_validate)
    monkeypatch.setattr(LLMClient, "list_models", ok_list_models)
    r = await client.post(
        "/api/v1/ai/bind",
        json={
            "provider": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-12345678",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["bound"] is True
    assert body["model"] == "gpt-x"  # 未指定 model → 自动识别首个
    assert body["api_key_masked"].startswith("sk-t")
    assert "12345678" not in body["api_key_masked"]

    st = await client.get("/api/v1/ai/status")
    assert st.status_code == 200
    assert st.json()["bound"] is True

    models = await client.get("/api/v1/ai/models")
    assert models.status_code == 200
    assert "gpt-y" in models.json()["models"]

    un = await client.delete("/api/v1/ai/bind")
    assert un.json()["bound"] is False


@pytest.mark.asyncio
async def test_asset_chat_rule_fallback(client):
    """未绑定模型 → 确定性规则回复（source=rule + 免责声明）。"""
    r = await client.post(
        "/api/v1/ai/asset-chat/BTC",
        json={"message": "现在趋势如何？"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "rule"
    assert "不构成任何投资建议" in body["disclaimer"]
    assert body["reply"]


@pytest.mark.asyncio
async def test_regime_brief_rule_fallback(client):
    r = await client.post("/api/v1/ai/regime-brief")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "rule"
    assert len(body["summary"]) == 3
    assert body["detail"]


@pytest.mark.asyncio
async def test_asset_chat_with_binding_uses_llm(client, monkeypatch):
    """绑定后对话走 LLMClient.chat，返回模型文本。"""

    async def ok_validate(self):
        return {"ok": True, "models": ["m1"], "error": None}

    async def fake_chat(self, messages, **kwargs):
        return "根据 RSI 与 MACD，当前呈震荡偏多结构。"

    monkeypatch.setattr(LLMClient, "validate", ok_validate)
    monkeypatch.setattr(LLMClient, "chat", fake_chat)
    await client.post(
        "/api/v1/ai/bind",
        json={
            "provider": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "api_key": "sk-test-12345678",
        },
    )
    r = await client.post("/api/v1/ai/asset-chat/ETH", json={"message": "分析一下"})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "llm"
    assert "偏多" in body["reply"]


# ---------- 宏观长周期 + 指标时序（离线解析） ----------


@pytest.mark.asyncio
async def test_yahoo_get_ohlc_parses(monkeypatch):
    ym = __import__("w3ex.providers.yahoo.market", fromlist=["fetch_json"])
    payload = {
        "chart": {
            "result": [
                {
                    "timestamp": [1700000000, 1700086400, 1700172800],
                    "indicators": {
                        "quote": [
                            {
                                "open": [100.0, None, 102.0],
                                "high": [101.0, 103.0, 104.0],
                                "low": [99.0, 101.0, 101.0],
                                "close": [100.5, 102.5, 103.5],
                                "volume": [12345, 0, 54321],
                            }
                        ]
                    },
                }
            ]
        }
    }

    async def fake_fetch(url, **kw):
        return payload

    monkeypatch.setattr(ym, "fetch_json", fake_fetch)
    rows = await ym.YahooProvider().get_ohlc("TEST")
    assert len(rows) == 2  # None open 的 bar 被跳过
    assert rows[0]["o"] == 100.0 and rows[0]["c"] == 100.5 and rows[0]["v"] == 12345.0
    assert rows[1]["v"] == 54321.0


@pytest.mark.asyncio
async def test_macro_history_range_validation(client):
    r = await client.get("/api/v1/macro/history/SPX", params={"rng": "3d"})
    assert r.status_code == 422
    r2 = await client.get("/api/v1/macro/history/NOPE")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_macro_indicator_series(client, monkeypatch):
    async def fake_series(self, iso3, indicator, start_year=1960):
        assert (iso3, indicator) == ("USA", "gdp_growth")
        return {
            "iso3": "USA",
            "name": "美国",
            "indicator": "gdp_growth",
            "indicator_name": "GDP 年增速 %",
            "series": [{"year": 2000, "value": 4.1}, {"year": 2001, "value": 1.0}],
            "source": "worldbank",
        }

    # 先测未 patch 的真实校验路径（404/422），再 patch 走成功分支
    r2 = await client.get("/api/v1/macro/indicator/XXX/gdp_growth")
    assert r2.status_code == 404
    r3 = await client.get("/api/v1/macro/indicator/USA/bad_key")
    assert r3.status_code == 422

    from w3ex.providers.worldbank import macro as wb_mod

    monkeypatch.setattr(wb_mod.WorldBankProvider, "get_indicator_series", fake_series)
    r = await client.get("/api/v1/macro/indicator/USA/gdp_growth")
    assert r.status_code == 200
    body = r.json()
    assert body["series"][0]["year"] == 2000
    assert body["indicator_name"] == "GDP 年增速 %"
