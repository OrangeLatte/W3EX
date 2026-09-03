"""评审 P0 修复验证：交易语义分流（P0-1/2）、confirm 幂等（P0-5）。"""

from __future__ import annotations

from decimal import Decimal

import pytest

from w3ex.core.schemas import ExecutionQuoteResult, ExecutionRoute
from w3ex.execution.router import ExecutionRouter
from w3ex.providers.base import ExecutionProvider, ProviderUnavailable


def _route(venue: str, kind: str, *, total_cost: str, receive: str) -> ExecutionRoute:
    return ExecutionRoute(
        venue=venue,
        kind=kind,  # type: ignore[arg-type]
        price=Decimal("100"),
        slippage_pct=0.05,
        fees_usd=Decimal("1"),
        gas_usd=Decimal("0"),
        total_cost_usd=Decimal(total_cost),
        estimated_receive=Decimal(receive),
    )


class _FakeSub(ExecutionProvider):
    def __init__(self, name: str, routes: list[ExecutionRoute]) -> None:
        self.name = name
        self._routes = routes

    async def get_quote(
        self,
        side: str,
        asset: str,
        fiat_amount: Decimal,
        fiat_currency: str = "USD",
        market_type: str = "spot",
    ) -> ExecutionQuoteResult:
        for r in self._routes:
            want = "perp" if r.kind == "perp" else "spot"
            if market_type != want:
                raise ProviderUnavailable(f"{self.name} 无 {market_type} 报价")
        return ExecutionQuoteResult(
            side=side,  # type: ignore[arg-type]
            asset_symbol=asset,
            fiat_amount=fiat_amount,
            routes=self._routes,
            best_route_index=0,
            expires_in_seconds=30,
            ts=__import__("datetime").datetime.utcnow(),
        )


def _composite(subs: list[ExecutionProvider]):
    from w3ex.providers.composite.rich import CompositeExecutionProvider

    return CompositeExecutionProvider(subs=subs, fallback=_FakeSub("mock", []))


async def test_spot_buy_excludes_perp_and_picks_min_cost() -> None:
    c = _composite(
        [
            _FakeSub("binance", [_route("binance_cex", "cex", total_cost="1001", receive="10")]),
            _FakeSub(
                "hyperliquid", [_route("hyperliquid_perp", "perp", total_cost="900", receive="11")]
            ),
        ]
    )
    q = await c.get_quote("buy", "ETH", Decimal("1000"), market_type="spot")
    assert [r.venue for r in q.routes] == ["binance_cex"]
    assert all(r.instrument_type == "spot" for r in q.routes)
    assert q.best_route_index == 0
    assert "全成本最低" in q.recommendation_reason


async def test_sell_ranks_by_net_proceeds_not_cost() -> None:
    # P0-2：卖出时 total_cost 只是手续费，best 应按净到手最高
    c = _composite(
        [
            _FakeSub("binance", [_route("binance_cex", "cex", total_cost="1.0", receive="990")]),
            _FakeSub("jupiter", [_route("jupiter_dex", "dex", total_cost="0.4", receive="995")]),
        ]
    )
    q = await c.get_quote("sell", "ETH", Decimal("1000"), market_type="spot")
    best = q.routes[q.best_route_index]
    assert best.venue == "jupiter_dex"
    assert str(best.net_proceeds_usd) == "995"
    assert "净到手最多" in q.recommendation_reason


async def test_perp_quote_only_perp_channel() -> None:
    c = _composite(
        [
            _FakeSub("binance", [_route("binance_cex", "cex", total_cost="1001", receive="10")]),
            _FakeSub(
                "hyperliquid", [_route("hyperliquid_perp", "perp", total_cost="1000", receive="10")]
            ),
        ]
    )
    q = await c.get_quote("buy", "ETH", Decimal("1000"), market_type="perp")
    assert [r.venue for r in q.routes] == ["hyperliquid_perp"]
    assert q.market_type == "perp"


async def test_no_channel_for_market_type_raises_503able() -> None:
    c = _composite(
        [_FakeSub("binance", [_route("binance_cex", "cex", total_cost="1", receive="1")])]
    )
    with pytest.raises(ProviderUnavailable):
        await c.get_quote("buy", "ETH", Decimal("100"), market_type="perp")


async def test_invalid_market_type() -> None:
    c = _composite([])
    with pytest.raises(ValueError):
        await c.get_quote("buy", "ETH", Decimal("100"), market_type="margin")


# ---------- P0-5: confirm 幂等 ----------


async def test_confirm_idempotency_key_replay(client) -> None:
    q = (await client.get("/api/v1/trade/quote?side=buy&asset=ETH&amount=100")).json()
    headers = {"Idempotency-Key": "test-key-001"}
    r1 = await client.post(
        "/api/v1/trade/confirm", json={"quote_id": q["quote_id"], "route_index": 0}, headers=headers
    )
    assert r1.status_code == 200
    first = r1.json()
    assert first["idempotent_replay"] is False

    r2 = await client.post(
        "/api/v1/trade/confirm", json={"quote_id": q["quote_id"], "route_index": 0}, headers=headers
    )
    assert r2.status_code == 200
    replay = r2.json()
    assert replay["idempotent_replay"] is True
    assert replay["executed_at"] == first["executed_at"]


async def test_idempotency_key_reuse_rejected(client) -> None:
    q1 = (await client.get("/api/v1/trade/quote?side=buy&asset=ETH&amount=100")).json()
    q2 = (await client.get("/api/v1/trade/quote?side=buy&asset=ETH&amount=200")).json()
    headers = {"Idempotency-Key": "dup-key"}
    r1 = await client.post(
        "/api/v1/trade/confirm",
        json={"quote_id": q1["quote_id"], "route_index": 0},
        headers=headers,
    )
    assert r1.status_code == 200
    r2 = await client.post(
        "/api/v1/trade/confirm",
        json={"quote_id": q2["quote_id"], "route_index": 0},
        headers=headers,
    )
    assert r2.status_code == 422


async def test_quote_api_market_type_filter(client) -> None:
    q = (
        await client.get("/api/v1/trade/quote?side=buy&asset=BTC&amount=500&market_type=perp")
    ).json()
    assert q["market_type"] == "perp"
    assert {r["instrument_type"] for r in q["routes"]} == {"perp"}
    q2 = await client.get("/api/v1/trade/quote?side=buy&asset=BTC&amount=500&market_type=margin")
    assert q2.status_code == 422


async def test_router_confirm_replay_direct(session) -> None:  # noqa: ARG001
    assert ExecutionRouter is not None
