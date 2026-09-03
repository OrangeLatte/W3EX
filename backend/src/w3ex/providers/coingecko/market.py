"""CoinGecko Provider（免费公开 API，无需 Key，限速友好靠 TTL 缓存）。

负责聚合面数据：全局市值统计 / Top-250 行情 / 资产元数据。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from w3ex.core.schemas import Candle, LiquidationEvent, MarketRegime, PriceQuote, Ticker
from w3ex.providers.base import MarketDataProvider, ProviderUnavailable
from w3ex.providers.http import fetch_json

BASE = "https://api.coingecko.com/api/v3"

TICKERS_TTL = 60  # 免费 tier 限速 ~10-30 req/min，必须靠缓存


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# 常用 symbol → coingecko id 映射（Top 250 内无法直接按 symbol 查详情）
SYMBOL_TO_ID: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "USDC": "usd-coin",
    "USDT": "tether",
    "DAI": "dai",
    "AAVE": "aave",
    "UNI": "uniswap",
    "LINK": "chainlink",
    "JUP": "jupiter-exchange-solana",
    "HYPE": "hyperliquid",
    "PEPE": "pepe",
    "WIF": "dogwifcoin",
    "JTO": "jito-governance-token",
    "PYTH": "pyth-network",
    "OP": "optimism",
    "ARB": "arbitrum",
    "MKR": "maker",
    "LDO": "lido-dao",
    "RENDER": "render-token",
    "WLD": "worldcoin-wld",
    "ATOM": "cosmos",
    "DOT": "polkadot",
    "INJ": "injective-protocol",
    "ENA": "ethena",
    "BONK": "bonk",
    "RAY": "raydium",
    "TIA": "celestia",
    "SUI": "sui",
    "APT": "aptos",
    "NEAR": "near",
    "AVAX": "avalanche-2",
    "TRX": "tron",
    "XRP": "ripple",
    "BNB": "binancecoin",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "FIL": "filecoin",
    "STX": "blockstack",
    "PENGU": "pudgy-penguins",
}


class CoinGeckoProvider(MarketDataProvider):
    name = "coingecko"

    async def _markets(self, per_page: int = 250) -> list[dict]:
        return await fetch_json(
            f"{BASE}/coins/markets",
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": 1,
                "price_change_percentage": "24h",
                "sparkline": "false",
            },
            ttl=TICKERS_TTL,
            cache_key="coingecko:markets:250",
        )

    async def get_tickers(self, assets: list[str] | None = None) -> list[Ticker]:
        rows = await self._markets()
        wanted = {a.upper() for a in assets} if assets else None
        out: list[Ticker] = []
        seen: set[str] = set()
        for r in rows:
            sym = (r.get("symbol") or "").upper()
            if wanted is not None and sym not in wanted:
                continue
            # coingecko 同 symbol 多条目（不同 id）会重复；rows 按市值降序，保留市值最高的一条
            if sym in seen:
                continue
            seen.add(sym)
            change = r.get("price_change_percentage_24h_in_currency")
            if change is None:
                change = r.get("price_change_percentage_24h") or 0.0
            price = r.get("current_price") or 0
            out.append(
                Ticker(
                    symbol=sym,
                    last=Decimal(str(price)),
                    bid=Decimal(str(price)),
                    ask=Decimal(str(price)),
                    high_24h=Decimal(str(r.get("high_24h") or price)),
                    low_24h=Decimal(str(r.get("low_24h") or price)),
                    volume_24h=Decimal(str(r.get("total_volume") or 0)),
                    change_24h_pct=float(change),
                    funding_rate=None,
                    ts=_now(),
                )
            )
        if not out:
            raise ProviderUnavailable("coingecko tickers 无匹配资产")
        return out

    async def get_price(self, asset: str) -> PriceQuote:
        tickers = await self.get_tickers([asset])
        t = tickers[0]
        return PriceQuote(
            symbol=t.symbol,
            price=t.last,
            bid=t.bid,
            ask=t.ask,
            volume_24h=t.volume_24h,
            change_24h_pct=t.change_24h_pct,
            ts=t.ts,
        )

    async def get_candles(self, asset: str, interval: str = "1h", limit: int = 100) -> list[Candle]:
        # CoinGecko 免费档无 OHLC K 线（只有 price 序列），交给回退链
        raise ProviderUnavailable("coingecko 免费档不提供 OHLC K 线")

    async def get_funding(self, asset: str) -> float | None:
        raise ProviderUnavailable("coingecko 不提供资金费率")

    async def get_liquidations(self, hours: int = 24) -> list[LiquidationEvent]:
        raise ProviderUnavailable("coingecko 不提供强平数据")

    async def get_market_regime(self) -> MarketRegime:
        tickers = await self.get_tickers(["BTC", "ETH", "SOL"])
        by_sym = {t.symbol: t.change_24h_pct for t in tickers}
        btc, eth, sol = by_sym.get("BTC", 0.0), by_sym.get("ETH", 0.0), by_sym.get("SOL", 0.0)
        score = max(-100.0, min(100.0, btc * 5 + eth * 3 + sol * 2))
        if score >= 20:
            regime, label = "risk_on", "Risk-On: 主要资产普涨，风险偏好回升"
        elif score <= -20:
            regime, label = "risk_off", "Risk-Off: 主要资产走弱，避险情绪主导"
        else:
            regime, label = "neutral", "Neutral: 市场方向不明确"
        return MarketRegime(
            regime=regime,
            score=round(score, 2),
            btc_change_24h_pct=btc,
            eth_change_24h_pct=eth,
            sol_change_24h_pct=sol,
            label=label,
            drivers=[f"BTC {btc:+.2f}%", f"ETH {eth:+.2f}%", f"SOL {sol:+.2f}%"],
        )

    async def get_global_stats(self) -> dict | None:
        data = (await fetch_json(f"{BASE}/global", ttl=TICKERS_TTL, cache_key="coingecko:global"))[
            "data"
        ]
        return {
            "total_market_cap_usd": float(data["total_market_cap"]["usd"]),
            "total_volume_24h_usd": float(data["total_volume"]["usd"]),
            "btc_dominance_pct": float(data["market_cap_percentage"]["btc"]),
            "eth_dominance_pct": float(data["market_cap_percentage"].get("eth", 0.0)),
            "mcap_change_24h_pct": float(data.get("market_cap_change_percentage_24h_usd", 0.0)),
            "active_cryptocurrencies": int(data.get("active_cryptocurrencies", 0)),
            "source": "coingecko",
            "ts": _now().isoformat(),
        }

    async def get_asset_meta(self, asset: str) -> dict | None:
        symbol = asset.upper()
        coin_id = SYMBOL_TO_ID.get(symbol)
        rows = await self._markets()
        for r in rows:
            if (r.get("symbol") or "").upper() == symbol and (
                coin_id is None or r.get("id") == coin_id
            ):
                return {
                    "symbol": symbol,
                    "name": r.get("name"),
                    "market_cap": r.get("market_cap"),
                    "market_cap_rank": r.get("market_cap_rank"),
                    "volume_24h": r.get("total_volume"),
                    "circulating_supply": r.get("circulating_supply"),
                    "high_24h": r.get("high_24h"),
                    "low_24h": r.get("low_24h"),
                    "source": "coingecko",
                }
        raise ProviderUnavailable(f"coingecko 无 {symbol} 元数据")
