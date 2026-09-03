"""AI 交易教练四类 Agent 测试（离线，rule 回退）。"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_agents(client):
    r = await client.get("/api/v1/agent")
    assert r.status_code == 200
    kinds = [a["kind"] for a in r.json()["agents"]]
    assert kinds == ["mentor", "scout", "risk", "review"]


@pytest.mark.asyncio
async def test_agent_scout_rule(client):
    r = await client.post("/api/v1/agent/scout", json={"message": "现在市场怎么样"})
    assert r.status_code == 200
    body = r.json()
    assert body["agent"] == "scout"
    assert body["source"] == "rule"
    assert "市场状态" in body["reply"]
    assert body["disclaimer"]


@pytest.mark.asyncio
async def test_agent_risk_empty_account(client):
    r = await client.post(
        "/api/v1/agent/risk",
        json={"message": "我的风险如何"},
        headers={"X-User-Key": "agent-test-u1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "rule"
    assert "开放仓位: 0" in body["context"]


@pytest.mark.asyncio
async def test_agent_review_no_history(client):
    r = await client.post("/api/v1/agent/review", json={}, headers={"X-User-Key": "agent-test-u2"})
    assert r.status_code == 200
    assert "暂无历史交易" in r.json()["context"]


@pytest.mark.asyncio
async def test_agent_unknown_kind_404(client):
    r = await client.post("/api/v1/agent/nope", json={})
    assert r.status_code == 404
