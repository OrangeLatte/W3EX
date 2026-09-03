from __future__ import annotations

from datetime import timedelta

from w3ex.core.schemas import (
    Candle,
    ChainTransaction,
    ExchangeFlow,
    HolderStats,
    LiquidationEvent,
    MarketRegime,
    PriceQuote,
    Ticker,
)
from w3ex.providers.base import MarketDataProvider, OnchainProvider
from w3ex.providers.mock.generator import MockDataset, _stable_rng


class MockMarketProvider(MarketDataProvider):
    name = "mock"

    def __init__(self, dataset: MockDataset | None = None) -> None:
        self.ds = dataset or MockDataset()

    async def get_price(self, asset: str) -> PriceQuote:
        return self.ds.price(asset.upper())

    async def get_candles(self, asset: str, interval: str = "1h", limit: int = 100) -> list[Candle]:
        return self.ds.candles(asset.upper(), interval=interval, limit=limit)

    async def get_tickers(self, assets: list[str] | None = None) -> list[Ticker]:
        symbols = assets or [a["symbol"] for a in MockDataset().asset_by_symbol.values()]
        return [self.ds.ticker(s.upper()) for s in symbols]

    async def get_funding(self, asset: str) -> float | None:
        return self.ds.ticker(asset.upper()).funding_rate

    async def get_liquidations(self, hours: int = 24) -> list[LiquidationEvent]:
        return self.ds.liquidations(hours)

    async def get_market_regime(self) -> MarketRegime:
        return self.ds.market_regime()

    async def get_depth(self, asset: str, limit: int = 20) -> dict | None:
        symbol = asset.upper()
        if symbol not in self.ds.asset_by_symbol:
            return None
        mid = float(self.ds.price(symbol).price)
        rng = _stable_rng(f"depth:{symbol}")
        step_pct = 0.0002
        bids: list[list[float]] = []
        asks: list[list[float]] = []
        for i in range(1, limit + 1):
            size_b = rng.uniform(0.2, 2.5) * 10 ** (0 if mid > 100 else 2)
            size_a = rng.uniform(0.2, 2.5) * 10 ** (0 if mid > 100 else 2)
            bids.append([round(mid * (1 - step_pct * i), 8), round(size_b, 6)])
            asks.append([round(mid * (1 + step_pct * i), 8), round(size_a, 6)])
        return {
            "bids": bids,
            "asks": asks,
            "ts": (self.ds.now + timedelta(minutes=1)).isoformat(),
            "source": "mock",
        }

    async def get_global_stats(self) -> dict | None:
        total_mcap = sum(float(a["mcap"]) for a in self.ds.asset_by_symbol.values())
        btc_mcap = float(self.ds.asset_by_symbol["BTC"]["mcap"])
        total_vol = sum(
            float(a["price"]) * float(a["mcap"]) * float(a["vol_ratio"])
            for a in self.ds.asset_by_symbol.values()
        )
        regime = self.ds.market_regime()
        return {
            "total_market_cap_usd": total_mcap,
            "total_volume_24h_usd": total_vol,
            "btc_dominance_pct": round(btc_mcap / total_mcap * 100, 2),
            "eth_dominance_pct": round(
                float(self.ds.asset_by_symbol["ETH"]["mcap"]) / total_mcap * 100, 2
            ),
            "mcap_change_24h_pct": regime.btc_change_24h_pct,
            "active_cryptocurrencies": len(self.ds.asset_by_symbol),
            "source": "mock",
            "ts": self.ds.now.isoformat(),
        }

    async def get_asset_meta(self, asset: str) -> dict | None:
        symbol = asset.upper()
        a = self.ds.asset_by_symbol.get(symbol)
        if a is None:
            return None
        t = self.ds.ticker(symbol)
        ranked = sorted(
            self.ds.asset_by_symbol.values(), key=lambda x: float(x["mcap"]), reverse=True
        )
        return {
            "symbol": symbol,
            "name": a["name"],
            "market_cap": float(a["mcap"]),
            "market_cap_rank": next(
                (i + 1 for i, x in enumerate(ranked) if x["symbol"] == symbol), None
            ),
            "volume_24h": float(t.volume_24h),
            "circulating_supply": None,
            "high_24h": float(t.high_24h),
            "low_24h": float(t.low_24h),
            "source": "mock",
        }

    async def get_funding_summary(self, limit: int = 15) -> list[dict] | None:
        rows = [
            {
                "symbol": s,
                "rate": t.funding_rate,
                "mark_price": float(t.last),
                "ts": t.ts.isoformat(),
            }
            for s, t in ((sym, self.ds.ticker(sym)) for sym in self.ds.asset_by_symbol)
            if t.funding_rate is not None
        ]
        rows.sort(key=lambda x: abs(x["rate"]), reverse=True)
        return rows[:limit]


class MockOnchainProvider(OnchainProvider):
    name = "mock"

    def __init__(self, dataset: MockDataset | None = None) -> None:
        self.ds = dataset or MockDataset()

    async def get_transactions(self, address: str, limit: int = 50) -> list[ChainTransaction]:
        return self.ds.wallet_transactions(address, limit)

    async def get_balances(self, address: str) -> list:
        return self.ds._wallet_holdings(address)

    async def get_large_transfers(
        self, asset: str | None = None, hours: int = 24
    ) -> list[ChainTransaction]:
        evs = self.ds.events(asset=asset, event_type="large_transfer", hours=hours)
        out = []
        for e in evs[:40]:
            out.append(
                ChainTransaction(
                    tx_hash=e["tx_hash"],
                    chain=e["chain"],
                    from_address=e["from_entity"],
                    to_address=e["to_entity"],
                    value=e["amount"],
                    asset_symbol=e["asset_symbol"],
                    value_usd=e["value_usd"],
                    ts=e["ts"],
                )
            )
        return out

    async def get_dex_swaps(
        self, asset: str | None = None, hours: int = 24
    ) -> list[ChainTransaction]:
        evs = self.ds.events(asset=asset, event_type="dex_spike", hours=hours)
        return [
            ChainTransaction(
                tx_hash=e["tx_hash"],
                chain=e["chain"],
                from_address=e["from_entity"],
                to_address=e["to_entity"],
                value=e["amount"],
                asset_symbol=e["asset_symbol"],
                value_usd=e["value_usd"],
                ts=e["ts"],
            )
            for e in evs[:40]
        ]

    async def get_holder_stats(self, asset: str) -> HolderStats:
        return self.ds.holder_stats(asset.upper())

    async def get_exchange_flow(self, asset: str, hours: int = 24) -> list[ExchangeFlow]:
        return self.ds.exchange_flow(asset.upper(), hours)
