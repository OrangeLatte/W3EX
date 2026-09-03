"""Agent 工具循环（Function Calling）测试：全离线 FakeClient + FakeMarket。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from w3ex.intelligence.agent import run_agent
from w3ex.providers.base import ProviderUnavailable


class _Q:
    def __init__(self, p: str) -> None:
        self.price = Decimal(p)
        self.bid = Decimal(p)
        self.ask = Decimal(p)


class FakeMarket:
    name = "fake"

    async def get_price(self, asset):
        return _Q("100")


class FakeLLM:
    """第一轮返回 tool_calls，第二轮返回最终文本。"""

    def __init__(self, calls_per_round: list[list[dict]]) -> None:
        self.rounds = list(calls_per_round)
        self.seen_msgs: list[list[dict]] = []

    async def chat_tools(self, messages, tools=None, max_tokens=4096, temperature=0.4):
        self.seen_msgs.append(messages)
        if self.rounds:
            calls = self.rounds.pop(0)
            return {
                "content": "",
                "reasoning": "",
                "tool_calls": calls,
                "finish_reason": "tool_calls",
            }
        return {"content": "最终回答", "reasoning": "", "tool_calls": [], "finish_reason": "stop"}


@pytest.mark.asyncio
async def test_tool_loop_executes_and_returns_trace(session, monkeypatch):
    """LLM 请求 get_account → 工具执行 → 第二轮给最终回答；trace 记录调用。"""
    fake = FakeLLM(
        [
            [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "get_account", "arguments": "{}"},
                }
            ]
        ]
    )
    monkeypatch.setattr("w3ex.intelligence.agent.client_from_binding", lambda b: fake, raising=True)
    # 造一条 AiBinding（run_agent 需要）
    from w3ex.db.models import AiBinding

    session.add(
        AiBinding(provider="openai_compatible", base_url="http://x", api_key="k", model="m")
    )
    await session.commit()

    out = await run_agent(session, "risk", "我的账户怎么样", [], FakeMarket(), "tester")
    assert out["reply"] == "最终回答"
    assert out["source"] == "llm:m"
    assert len(out["tool_trace"]) == 1
    step = out["tool_trace"][0]
    assert step["tool"] == "get_account" and step["ok"] is True
    assert "权益" in step["summary"]
    # 工具结果应回填进第二轮消息
    second = fake.seen_msgs[1]
    assert any(m.get("role") == "tool" for m in second)


@pytest.mark.asyncio
async def test_place_order_preview_then_confirm(session):
    """双阶段下单：confirmed=false 只出预览；confirmed=true 才执行。"""
    from w3ex.intelligence.agent_tools import build_tools

    schemas, dispatch = build_tools(session, FakeMarket(), "tester2")
    names = [s["function"]["name"] for s in schemas]
    assert "place_order" in names and "get_market_overview" in names

    preview = await dispatch["place_order"](
        {
            "side": "buy",
            "asset": "BTC",
            "order_type": "market",
            "amount_usd": "100",
            "market_type": "perp",
            "confirmed": False,
        }
    )
    assert "未执行" in preview

    done = await dispatch["place_order"](
        {
            "side": "buy",
            "asset": "BTC",
            "order_type": "market",
            "amount_usd": "100",
            "market_type": "perp",
            "leverage": 5,
            "confirmed": True,
        }
    )
    assert "[已执行]" in done


@pytest.mark.asyncio
async def test_unknown_tool_reported(session, monkeypatch):
    fake = FakeLLM(
        [
            [
                {
                    "id": "call_x",
                    "type": "function",
                    "function": {"name": "no_such_tool", "arguments": "{}"},
                }
            ]
        ]
    )
    monkeypatch.setattr("w3ex.intelligence.agent.client_from_binding", lambda b: fake)
    from w3ex.db.models import AiBinding

    session.add(
        AiBinding(provider="openai_compatible", base_url="http://x", api_key="k", model="m")
    )
    await session.commit()
    out = await run_agent(session, "scout", "hi", [], FakeMarket(), "tester3")
    assert out["reply"] == "最终回答"
    assert out["tool_trace"][0]["ok"] is False


@pytest.mark.asyncio
async def test_market_unavailable_tool_tolerated(session, monkeypatch):
    """行情源抛 ProviderUnavailable → 工具失败但不炸 Agent。"""

    class BoomMarket:
        name = "boom"

        async def get_price(self, asset):
            raise ProviderUnavailable("boom")

    fake = FakeLLM(
        [
            [
                {
                    "id": "c",
                    "type": "function",
                    "function": {"name": "get_asset_snapshot", "arguments": '{"symbol":"BTC"}'},
                }
            ]
        ]
    )
    monkeypatch.setattr("w3ex.intelligence.agent.client_from_binding", lambda b: fake)
    from w3ex.db.models import AiBinding

    session.add(
        AiBinding(provider="openai_compatible", base_url="http://x", api_key="k", model="m")
    )
    await session.commit()
    out = await run_agent(session, "scout", "BTC 怎么样", [], BoomMarket(), "tester4")
    assert out["reply"] == "最终回答"
    assert out["tool_trace"][0]["ok"] is False
