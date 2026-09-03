from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from w3ex.core.schemas import (
    Candle,
    ChainTransaction,
    ExchangeFlow,
    HolderStats,
    LiquidationEvent,
    MarketRegime,
    NewsItem,
    PriceQuote,
    ProtocolMetric,
    Ticker,
    WalletBalance,
)

UTC = UTC

ASSETS: list[dict] = [
    # symbol, name, category, chain, base_price, market_cap(USD), vol24/price ratio
    dict(
        symbol="BTC",
        name="Bitcoin",
        category="store_of_value",
        chain="ethereum",
        price=120_000,
        mcap=2_360e9,
        vol_ratio=0.012,
    ),
    dict(
        symbol="ETH",
        name="Ethereum",
        category="smart_contract_platform",
        chain="ethereum",
        price=5_200,
        mcap=625e9,
        vol_ratio=0.020,
    ),
    dict(
        symbol="SOL",
        name="Solana",
        category="smart_contract_platform",
        chain="solana",
        price=260,
        mcap=125e9,
        vol_ratio=0.030,
    ),
    dict(
        symbol="USDC",
        name="USD Coin",
        category="stablecoin",
        chain="ethereum",
        price=1.0,
        mcap=52e9,
        vol_ratio=0.050,
    ),
    dict(
        symbol="USDT",
        name="Tether",
        category="stablecoin",
        chain="ethereum",
        price=1.0,
        mcap=130e9,
        vol_ratio=0.060,
    ),
    dict(
        symbol="DAI",
        name="Dai",
        category="stablecoin",
        chain="ethereum",
        price=1.0,
        mcap=5.2e9,
        vol_ratio=0.010,
    ),
    dict(
        symbol="AAVE",
        name="Aave",
        category="lending",
        chain="ethereum",
        price=380,
        mcap=5.6e9,
        vol_ratio=0.028,
    ),
    dict(
        symbol="UNI",
        name="Uniswap",
        category="dex",
        chain="ethereum",
        price=14,
        mcap=8.4e9,
        vol_ratio=0.035,
    ),
    dict(
        symbol="LINK",
        name="Chainlink",
        category="oracle",
        chain="ethereum",
        price=26,
        mcap=16e9,
        vol_ratio=0.025,
    ),
    dict(
        symbol="JUP",
        name="Jupiter",
        category="dex",
        chain="solana",
        price=1.9,
        mcap=2.6e9,
        vol_ratio=0.060,
    ),
    dict(
        symbol="HYPE",
        name="Hyperliquid",
        category="perpetual_dex",
        chain="ethereum",
        price=42,
        mcap=13e9,
        vol_ratio=0.040,
    ),
    dict(
        symbol="PEPE",
        name="Pepe",
        category="memecoin",
        chain="ethereum",
        price=0.000021,
        mcap=8.8e9,
        vol_ratio=0.080,
    ),
    dict(
        symbol="WIF",
        name="dogwifhat",
        category="memecoin",
        chain="solana",
        price=3.4,
        mcap=3.4e9,
        vol_ratio=0.090,
    ),
    dict(
        symbol="DOGE",
        name="Dogecoin",
        category="memecoin",
        chain="ethereum",
        price=0.28,
        mcap=42e9,
        vol_ratio=0.045,
    ),
    dict(
        symbol="SHIB",
        name="Shiba Inu",
        category="memecoin",
        chain="ethereum",
        price=0.000029,
        mcap=17e9,
        vol_ratio=0.050,
    ),
    dict(
        symbol="JTO",
        name="Jito",
        category="restaking",
        chain="solana",
        price=4.2,
        mcap=5.2e9,
        vol_ratio=0.050,
    ),
    dict(
        symbol="EIGEN",
        name="EigenLayer",
        category="restaking",
        chain="ethereum",
        price=3.2,
        mcap=6.4e9,
        vol_ratio=0.040,
    ),
    dict(
        symbol="PYTH",
        name="Pyth Network",
        category="oracle",
        chain="solana",
        price=0.9,
        mcap=3.2e9,
        vol_ratio=0.045,
    ),
    dict(
        symbol="OP",
        name="Optimism",
        category="layer2",
        chain="ethereum",
        price=2.1,
        mcap=2.9e9,
        vol_ratio=0.040,
    ),
    dict(
        symbol="ARB",
        name="Arbitrum",
        category="layer2",
        chain="ethereum",
        price=1.2,
        mcap=4.6e9,
        vol_ratio=0.045,
    ),
    dict(
        symbol="STRK",
        name="Starknet",
        category="layer2",
        chain="ethereum",
        price=0.7,
        mcap=1.5e9,
        vol_ratio=0.030,
    ),
    dict(
        symbol="MKR",
        name="Maker",
        category="stablecoin",
        chain="ethereum",
        price=2400,
        mcap=2.3e9,
        vol_ratio=0.015,
    ),
    dict(
        symbol="ENA",
        name="Ethena",
        category="restaking",
        chain="ethereum",
        price=0.9,
        mcap=1.4e9,
        vol_ratio=0.060,
    ),
    dict(
        symbol="LDO",
        name="Lido DAO",
        category="liquid_staking",
        chain="ethereum",
        price=2.8,
        mcap=2.5e9,
        vol_ratio=0.030,
    ),
    dict(
        symbol="RENDER",
        name="Render",
        category="ai",
        chain="ethereum",
        price=9.5,
        mcap=3.9e9,
        vol_ratio=0.060,
    ),
    dict(
        symbol="WLD",
        name="Worldcoin",
        category="ai",
        chain="ethereum",
        price=4.4,
        mcap=3.1e9,
        vol_ratio=0.070,
    ),
    dict(
        symbol="TAO",
        name="Bittensor",
        category="ai",
        chain="ethereum",
        price=620,
        mcap=5.7e9,
        vol_ratio=0.040,
    ),
    dict(
        symbol="FET",
        name="Artificial Superintelligence Alliance",
        category="ai",
        chain="ethereum",
        price=2.6,
        mcap=6.6e9,
        vol_ratio=0.050,
    ),
    dict(
        symbol="INJ",
        name="Injective",
        category="ai",
        chain="ethereum",
        price=28,
        mcap=2.8e9,
        vol_ratio=0.050,
    ),
    dict(
        symbol="ONDO",
        name="Ondo",
        category="rwa",
        chain="ethereum",
        price=1.8,
        mcap=2.8e9,
        vol_ratio=0.055,
    ),
    dict(
        symbol="CRV",
        name="Curve DAO",
        category="dex",
        chain="ethereum",
        price=0.9,
        mcap=1.1e9,
        vol_ratio=0.045,
    ),
    dict(
        symbol="PENDLE",
        name="Pendle",
        category="restaking",
        chain="ethereum",
        price=6.5,
        mcap=1.6e9,
        vol_ratio=0.050,
    ),
    dict(
        symbol="ATOM",
        name="Cosmos",
        category="layer1",
        chain="ethereum",
        price=9.0,
        mcap=3.5e9,
        vol_ratio=0.020,
    ),
    dict(
        symbol="DOT",
        name="Polkadot",
        category="layer1",
        chain="ethereum",
        price=8.5,
        mcap=12e9,
        vol_ratio=0.025,
    ),
    dict(
        symbol="SUI",
        name="Sui",
        category="layer1",
        chain="ethereum",
        price=4.4,
        mcap=11e9,
        vol_ratio=0.050,
    ),
    dict(
        symbol="BONK",
        name="Bonk",
        category="memecoin",
        chain="solana",
        price=0.000039,
        mcap=3.0e9,
        vol_ratio=0.070,
    ),
]

NARRATIVES = [
    "AI + Crypto",
    "Stablecoins",
    "Memecoins",
    "DeFi",
    "Solana Ecosystem",
    "RWA",
    "Restaking",
    "Layer2",
]

NARRATIVE_MEMBERS: dict[str, list[str]] = {
    "AI + Crypto": ["RENDER", "WLD", "TAO", "FET", "INJ", "LINK"],
    "Stablecoins": ["USDC", "USDT", "DAI", "ENA", "MKR"],
    "Memecoins": ["PEPE", "WIF", "DOGE", "SHIB", "BONK"],
    "DeFi": ["AAVE", "UNI", "HYPE", "MKR", "CRV", "PENDLE"],
    "Solana Ecosystem": ["SOL", "JUP", "JTO", "PYTH", "WIF", "BONK"],
    "RWA": ["ONDO", "MKR"],
    "Restaking": ["JTO", "EIGEN", "ENA", "PENDLE", "LDO"],
    "Layer2": ["OP", "ARB", "STRK"],
}

EXCHANGES = ["Binance", "Coinbase", "OKX", "Kraken", "Bybit"]

PROTOCOLS: list[dict] = [
    dict(
        name="Uniswap",
        chain="ethereum",
        category="DEX",
        tvl=5.2e9,
        fees=1.2e7,
        users=320_000,
        volume=1.8e9,
    ),
    dict(
        name="Aave",
        chain="ethereum",
        category="Lending",
        tvl=14e9,
        fees=6.5e6,
        users=180_000,
        volume=0,
    ),
    dict(
        name="Lido",
        chain="ethereum",
        category="Liquid Staking",
        tvl=26e9,
        fees=8e6,
        users=410_000,
        volume=0,
    ),
    dict(
        name="MakerDAO",
        chain="ethereum",
        category="Stablecoin",
        tvl=6.8e9,
        fees=2.4e6,
        users=52_000,
        volume=0,
    ),
    dict(
        name="Hyperliquid",
        chain="ethereum",
        category="Perpetual DEX",
        tvl=2.1e9,
        fees=9.8e6,
        users=150_000,
        volume=3.2e9,
    ),
    dict(
        name="Jupiter",
        chain="solana",
        category="DEX",
        tvl=1.2e9,
        fees=2.8e6,
        users=260_000,
        volume=1.4e9,
    ),
    dict(
        name="Jito",
        chain="solana",
        category="Liquid Staking",
        tvl=3.4e9,
        fees=3.2e6,
        users=120_000,
        volume=0,
    ),
    dict(
        name="Ethena",
        chain="ethereum",
        category="Stablecoin",
        tvl=2.6e9,
        fees=2.1e6,
        users=40_000,
        volume=0,
    ),
    dict(
        name="Aerodrome",
        chain="base",
        category="DEX",
        tvl=1.5e9,
        fees=3.4e6,
        users=90_000,
        volume=0.9e9,
    ),
    dict(
        name="Pendle",
        chain="ethereum",
        category="Restaking",
        tvl=3.8e9,
        fees=2.9e6,
        users=35_000,
        volume=0,
    ),
]

NEWS_TEMPLATES: list[dict] = [
    dict(
        narrative="AI + Crypto",
        title="AI token complex rallies as GPU compute demand surges",
        sentiment=0.7,
        importance=0.85,
        entities=["RENDER", "TAO", "FET"],
    ),
    dict(
        narrative="AI + Crypto",
        title="Bittensor network upgrades staking rewards structure",
        sentiment=0.4,
        importance=0.6,
        entities=["TAO"],
    ),
    dict(
        narrative="AI + Crypto",
        title="Worldcoin expands World ID verification to new markets",
        sentiment=0.3,
        importance=0.55,
        entities=["WLD"],
    ),
    dict(
        narrative="AI + Crypto",
        title="Chainlink launches new data feeds for AI inference market",
        sentiment=0.5,
        importance=0.65,
        entities=["LINK"],
    ),
    dict(
        narrative="Stablecoins",
        title="Stablecoin market cap hits all-time high as inflows accelerate",
        sentiment=0.8,
        importance=0.9,
        entities=["USDC", "USDT"],
    ),
    dict(
        narrative="Stablecoins",
        title="Tether adds $2B to treasury reserves",
        sentiment=0.4,
        importance=0.7,
        entities=["USDT"],
    ),
    dict(
        narrative="Stablecoins",
        title="MakerDAO raises DAI savings rate to 8%",
        sentiment=0.6,
        importance=0.7,
        entities=["MKR", "DAI"],
    ),
    dict(
        narrative="Memecoins",
        title="PEPE leads memecoin rotation as retail flows return",
        sentiment=0.6,
        importance=0.75,
        entities=["PEPE"],
    ),
    dict(
        narrative="Memecoins",
        title="WIF breaks out on Solana as meme season heats up",
        sentiment=0.55,
        importance=0.7,
        entities=["WIF"],
    ),
    dict(
        narrative="Memecoins",
        title="Memecoin volume share rises to 22% of DEX volume",
        sentiment=0.3,
        importance=0.65,
        entities=["PEPE", "WIF", "DOGE"],
    ),
    dict(
        narrative="DeFi",
        title="Aave v4 proposal passes; unlocks cross-chain unified liquidity",
        sentiment=0.7,
        importance=0.8,
        entities=["AAVE"],
    ),
    dict(
        narrative="DeFi",
        title="Uniswap v4 hooks drive record DEX fee generation",
        sentiment=0.6,
        importance=0.7,
        entities=["UNI"],
    ),
    dict(
        narrative="DeFi",
        title="Hyperliquid open interest reaches new record above $5B",
        sentiment=0.7,
        importance=0.8,
        entities=["HYPE"],
    ),
    dict(
        narrative="Solana Ecosystem",
        title="Solana daily active addresses hit 8M milestone",
        sentiment=0.75,
        importance=0.85,
        entities=["SOL"],
    ),
    dict(
        narrative="Solana Ecosystem",
        title="Jupiter aggregates $1.4B daily volume across Solana DEXs",
        sentiment=0.65,
        importance=0.7,
        entities=["SOL", "JUP"],
    ),
    dict(
        narrative="Solana Ecosystem",
        title="Jito restaking TVL surpasses $3B",
        sentiment=0.55,
        importance=0.6,
        entities=["JTO"],
    ),
    dict(
        narrative="RWA",
        title="Ondo expands tokenized treasury to Base chain",
        sentiment=0.6,
        importance=0.7,
        entities=["ONDO"],
    ),
    dict(
        narrative="RWA",
        title="Tokenized US treasuries reach $8B market cap",
        sentiment=0.7,
        importance=0.8,
        entities=["ONDO"],
    ),
    dict(
        narrative="Restaking",
        title="EigenLayer TVL grows 15% week-over-week",
        sentiment=0.6,
        importance=0.7,
        entities=["EIGEN"],
    ),
    dict(
        narrative="Restaking",
        title="Ethena sUSDe yield premium draws institutional flows",
        sentiment=0.5,
        importance=0.65,
        entities=["ENA"],
    ),
    dict(
        narrative="Layer2",
        title="Base TVL crosses $5B, leading L2 growth",
        sentiment=0.7,
        importance=0.75,
        entities=["OP", "ARB"],
    ),
    dict(
        narrative="Layer2",
        title="Arbitrum Orbit adoption grows among game chains",
        sentiment=0.45,
        importance=0.6,
        entities=["ARB"],
    ),
]

# 12 个画像化钱包
WALLET_PROFILES: list[dict] = [
    dict(
        name="Binance Hot Wallet",
        address="0x28C6c06298d514Db089934071355E5743bf21d60",
        verified="Binance Hot Wallet",
        classification="whale",
        tags=["Exchange Hot Wallet", "High Volume"],
        freq=420.0,
        favorites=["BTC", "ETH", "USDT", "SOL"],
        pnl=None,
    ),
    dict(
        name="Whale Accumulator",
        address="0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE",
        verified=None,
        classification="whale",
        tags=["Whale", "Long-Term Holder", "Accumulator"],
        freq=0.8,
        favorites=["ETH", "SOL", "AAVE"],
        pnl=18_400_000,
    ),
    dict(
        name="Active DEX Trader",
        address="0x8a2d0E1b2C3d4f5A6B7c8D9e0F1a2b3C4d5E6F70",
        verified=None,
        classification="active_trader",
        tags=["Active Trader", "DEX Trader"],
        freq=12.0,
        favorites=["ETH", "UNI", "AAVE"],
        pnl=420_000,
    ),
    dict(
        name="High-Frequency Arb",
        address="0x5E4d3C2b1A9f8E7D6c5B4a39281706f5e4d3C2b1",
        verified=None,
        classification="high_frequency",
        tags=["High Frequency", "Arbitrage"],
        freq=95.0,
        favorites=["USDC", "ETH", "SOL"],
        pnl=2_100_000,
    ),
    dict(
        name="New Wallet Accumulator",
        address="0x7a1b2C3d4E5f60718293a4B5C6d7E8f90123a4B5",
        verified=None,
        classification="new_wallet",
        tags=["New Wallet", "Accumulator"],
        freq=1.5,
        favorites=["SOL", "JUP"],
        pnl=None,
    ),
    dict(
        name="Ethereum Whale Fund",
        address="0x9F8e7D6c5B4a39281706f5e4d3C2b1A0f9E8d7C6",
        verified=None,
        classification="whale",
        tags=["Whale", "DEX Trader"],
        freq=6.0,
        favorites=["ETH", "PEPE", "LINK"],
        pnl=9_800_000,
    ),
    dict(
        name="Solana Whale",
        address="0x4B5C6D7E8F90123A4B5C6D7E8F90123A4B5C6D7E8",
        verified=None,
        classification="whale",
        tags=["Whale", "Solana Ecosystem"],
        freq=4.0,
        favorites=["SOL", "JUP", "WIF"],
        pnl=15_200_000,
    ),
    dict(
        name="DeFi Yield Seeker",
        address="0x1A2B3C4D5E6F708192a3B4c5D6E7F801a2B3C4D5",
        verified=None,
        classification="active_trader",
        tags=["Active Trader", "Yield Farming"],
        freq=8.0,
        favorites=["AAVE", "LDO", "ENA", "PENDLE"],
        pnl=640_000,
    ),
    dict(
        name="Memecoin Speculator",
        address="0x6C5d4e3F2A1b0c9D8e7F6A5B4C3D2E1F0a9B8C7D",
        verified=None,
        classification="high_frequency",
        tags=["High Frequency", "Memecoin"],
        freq=60.0,
        favorites=["PEPE", "WIF", "SHIB"],
        pnl=-180_000,
    ),
    dict(
        name="Long-Term BTC Holder",
        address="0x0E1F2A3B4C5D6E7F8091a2B3C4D5E6F70A1b2C3D4",
        verified=None,
        classification="long_term_holder",
        tags=["Long-Term Holder"],
        freq=0.05,
        favorites=["BTC"],
        pnl=34_000_000,
    ),
    dict(
        name="Smart Money Risk Desk",
        address="0x2B3C4D5E6F708192a3B4c5D6E7F801a2B3C4D5E6",
        verified=None,
        classification="whale",
        tags=["Whale", "Active Trader", "DEX Trader"],
        freq=15.0,
        favorites=["HYPE", "SOL", "RENDER", "AAVE"],
        pnl=27_500_000,
    ),
    dict(
        name="Stablecoin Accumulator",
        address="0x3C4D5E6F708192a3B4c5D6E7F801a2B3C4D5E6F70",
        verified=None,
        classification="long_term_holder",
        tags=["Long-Term Holder", "Stablecoin"],
        freq=0.4,
        favorites=["USDC", "USDT", "DAI"],
        pnl=None,
    ),
]


def _stable_rng(seed_text: str) -> random.Random:
    digest = hashlib.sha256(seed_text.encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _addr(rng: random.Random) -> str:
    return "0x" + rng.getrandbits(160).to_bytes(20, "big").hex()


def anchored_now() -> datetime:
    now = datetime.now(UTC)
    return now.replace(minute=0, second=0, microsecond=0)


class MockDataset:
    """确定性 mock 数据集：锚定到当前整点，RNG 固定 seed，多 provider 共享同一数据源。"""

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.now = anchored_now()
        self.asset_by_symbol: dict[str, dict] = {a["symbol"]: a for a in ASSETS}
        self._candle_cache: dict[str, list[Candle]] = {}
        self._event_cache: list[dict] | None = None
        self._wallet_holdings_cache: dict[str, list[WalletBalance]] = {}

    # ---------- candles / tickers ----------

    def candles(self, symbol: str, interval: str = "1h", limit: int = 48) -> list[Candle]:
        if symbol not in self._candle_cache:
            self._candle_cache[symbol] = self._build_candles(symbol)
        return self._candle_cache[symbol][-limit:]

    def _build_candles(self, symbol: str) -> list[Candle]:
        asset = self.asset_by_symbol[symbol]
        base_price = float(asset["price"])
        vol = 0.018 + 0.014 * hash(symbol) % 1000 / 1000.0
        drift = (hash(symbol) % 100 - 50) / 1000.0  # -0.05..0.05
        rng = _stable_rng(f"{self.seed}:candles:{symbol}")
        prices: list[float] = []
        p = base_price * (1 + drift * 24)
        for _ in range(48):
            shock = rng.gauss(0, 1)
            p *= 1 + drift / 24.0 + vol / (24.0**0.5) * shock  # 24h 内的每小时收益
            prices.append(p)
        scale = base_price / prices[-1]
        prices = [x * scale for x in prices]
        out: list[Candle] = []
        vol_base = float(asset["price"]) * float(asset["mcap"]) * float(asset["vol_ratio"]) / 24.0
        for i, cp in enumerate(prices):
            ts = self.now - timedelta(hours=47 - i)
            o = prices[max(0, i - 1)]
            h = max(o, cp) * (1 + abs(rng.gauss(0, 0.001)))
            lo = min(o, cp) * (1 - abs(rng.gauss(0, 0.001)))
            v = vol_base * (0.7 + 0.6 * rng.random())
            out.append(
                Candle(
                    symbol=symbol,
                    ts=ts,
                    open=Decimal(str(round(o, 12))),
                    high=Decimal(str(round(h, 12))),
                    low=Decimal(str(round(lo, 12))),
                    close=Decimal(str(round(cp, 12))),
                    volume=Decimal(str(round(v, 2))),
                )
            )
        return out

    def price(self, symbol: str) -> PriceQuote:
        c = self.candles(symbol, limit=2)
        last = c[-1].close
        change = float((c[-1].close - c[0].open) / c[0].open * 100)
        asset = self.asset_by_symbol[symbol]
        vol = float(asset["price"]) * float(asset["mcap"]) * float(asset["vol_ratio"])
        spread = 0.0005
        return PriceQuote(
            symbol=symbol,
            price=last,
            bid=Decimal(str(float(last) * (1 - spread))),
            ask=Decimal(str(float(last) * (1 + spread))),
            volume_24h=Decimal(str(round(vol, 2))),
            change_24h_pct=round(change, 2),
            ts=self.now,
        )

    def ticker(self, symbol: str) -> Ticker:
        c = self.candles(symbol, limit=48)
        q = self.price(symbol)
        high = max(x.high for x in c)
        low = min(x.low for x in c)
        return Ticker(
            symbol=symbol,
            last=q.price,
            bid=q.bid,
            ask=q.ask,
            high_24h=high,
            low_24h=low,
            volume_24h=q.volume_24h,
            change_24h_pct=q.change_24h_pct,
            funding_rate=float(_stable_rng(f"{self.seed}:funding:{symbol}").gauss(0.0001, 0.0004)),
            ts=self.now,
        )

    def market_regime(self) -> MarketRegime:
        changes = {s: self.price(s).change_24h_pct for s in ("BTC", "ETH", "SOL")}
        avg = sum(changes.values()) / 3.0
        volume_bias = _stable_rng(f"{self.seed}:regime").random()
        score = avg * 3.0 + (volume_bias - 0.5) * 20.0
        score = max(-100.0, min(100.0, score))
        if score > 15:
            regime = "risk_on"
            label = "Risk-On: 主要资产上涨，资金偏好风险资产"
        elif score < -15:
            regime = "risk_off"
            label = "Risk-Off: 主要资产承压，防御性资产受青睐"
        else:
            regime = "neutral"
            label = "Neutral: 市场横盘整理，缺乏方向性动能"
        drivers = [
            f"BTC {changes['BTC']:+.1f}%",
            f"ETH {changes['ETH']:+.1f}%",
            f"SOL {changes['SOL']:+.1f}%",
        ]
        return MarketRegime(
            regime=regime,
            score=round(score, 2),
            btc_change_24h_pct=changes["BTC"],
            eth_change_24h_pct=changes["ETH"],
            sol_change_24h_pct=changes["SOL"],
            label=label,
            drivers=drivers,
        )

    def liquidations(self, hours: int = 24) -> list[LiquidationEvent]:
        out: list[LiquidationEvent] = []
        rng = _stable_rng(f"{self.seed}:liq")
        for _ in range(28):
            symbol = rng.choice(["BTC", "ETH", "SOL", "HYPE", "PEPE", "SOL"])
            side = rng.choice(["long", "short"])
            amount = rng.uniform(200_000, 12_000_000)
            ts = self.now - timedelta(seconds=rng.uniform(0, hours * 3600))
            price = float(self.price(symbol).price)
            out.append(
                LiquidationEvent(
                    symbol=symbol,
                    side=side,
                    amount_usd=Decimal(str(round(amount, 2))),
                    price=Decimal(str(round(price, 6))),
                    ts=ts,
                )
            )
        return sorted(out, key=lambda e: e.ts, reverse=True)

    # ---------- on-chain events ----------

    def _build_events(self) -> list[dict]:
        if self._event_cache is not None:
            return self._event_cache
        rng = _stable_rng(f"{self.seed}:events")
        events: list[dict] = []
        exchange_addresses = {ex: _addr(rng) for ex in EXCHANGES}
        typical = {
            "BTC": 5_000_000,
            "ETH": 2_000_000,
            "SOL": 1_000_000,
            "USDT": 5_000_000,
            "USDC": 5_000_000,
            "AAVE": 200_000,
            "UNI": 150_000,
            "PEPE": 300_000,
            "WIF": 200_000,
            "RENDER": 150_000,
            "HYPE": 400_000,
        }
        event_types = [
            "large_transfer",
            "exchange_inflow",
            "exchange_outflow",
            "whale_move",
            "new_wallet_accumulation",
            "dex_spike",
            "holder_change",
            "protocol_usage_spike",
        ]
        symbols = list(ASSETS)
        for _ in range(560):
            symbol = rng.choice(symbols)["symbol"]
            amount = rng.uniform(0.3, 3.0) * typical.get(symbol, 100_000)
            etype = rng.choice(event_types)
            if etype in ("exchange_inflow", "exchange_outflow"):
                ex = rng.choice(EXCHANGES)
                from_e = exchange_addresses[ex]
                to_e = exchange_addresses[ex]
                if etype == "exchange_inflow":
                    from_e, to_e = _addr(rng), exchange_addresses[ex]
                else:
                    from_e, to_e = exchange_addresses[ex], _addr(rng)
            else:
                from_e, to_e = _addr(rng), _addr(rng)
            significance = round(
                min(1.0, max(0.15, amount / (4 * typical.get(symbol, 100_000)))), 3
            )
            ts = self.now - timedelta(hours=rng.uniform(0, 24))
            tx_hash = "0x" + rng.getrandbits(256).to_bytes(32, "big").hex()
            events.append(
                dict(
                    chain=rng.choice(["ethereum", "solana", "base"]),
                    tx_hash=tx_hash,
                    event_type=etype,
                    asset_symbol=symbol,
                    amount=Decimal(str(round(amount, 6))),
                    from_entity=from_e,
                    to_entity=to_e,
                    value_usd=Decimal(str(round(amount * float(self.price(symbol).price), 2))),
                    significance=significance,
                    ts=ts,
                    source="mock",
                )
            )
        events.sort(key=lambda e: e["ts"], reverse=True)
        self._event_cache = events
        return events

    def events(
        self, asset: str | None = None, event_type: str | None = None, hours: int = 24
    ) -> list[dict]:
        evs = self._build_events()
        cutoff = self.now - timedelta(hours=hours)
        out = [e for e in evs if e["ts"] >= cutoff]
        if asset:
            out = [e for e in out if e["asset_symbol"] == asset]
        if event_type:
            out = [e for e in out if e["event_type"] == event_type]
        return out

    # ---------- wallets ----------

    def _wallet_holdings(self, address: str) -> list[WalletBalance]:
        if address in self._wallet_holdings_cache:
            return self._wallet_holdings_cache[address]
        profile = next((w for w in WALLET_PROFILES if w["address"] == address), None)
        rng = _stable_rng(f"{self.seed}:holdings:{address}")
        if profile is None:
            favorites = [rng.choice(["BTC", "ETH", "SOL"]) for _ in range(3)]
        else:
            favorites = profile["favorites"]
        out: list[WalletBalance] = []
        for sym in favorites:
            price = float(self.price(sym).price)
            bal = (
                10 ** rng.uniform(1, 3)
                * rng.uniform(0.1, 1.0)
                / price
                * 1000
                * (1 if sym == "SOL" else 1)
            )
            if profile and profile["classification"] == "whale":
                bal *= rng.uniform(50, 400)
            bal = Decimal(str(round(bal, 8)))
            out.append(
                WalletBalance(
                    asset_symbol=sym,
                    balance=bal,
                    price=Decimal(str(price)),
                    value_usd=Decimal(str(round(float(bal) * price, 2))),
                )
            )
        out.sort(key=lambda b: b.value_usd or 0, reverse=True)
        self._wallet_holdings_cache[address] = out
        return out

    def wallet_transactions(self, address: str, limit: int = 50) -> list[ChainTransaction]:
        profile = next((w for w in WALLET_PROFILES if w["address"] == address), None)
        rng = _stable_rng(f"{self.seed}:txns:{address}")
        holdings = self._wallet_holdings(address)
        favorites = [h.asset_symbol for h in holdings] or ["ETH"]
        out: list[ChainTransaction] = []
        count = limit if profile else 12
        for _ in range(count):
            sym = rng.choice(favorites)
            price = float(self.price(sym).price)
            amount = rng.uniform(0.05, 5.0) * 1000 / price * 1000
            ts = self.now - timedelta(hours=rng.uniform(0, 72))
            out.append(
                ChainTransaction(
                    tx_hash=_addr(rng),
                    chain=rng.choice(["ethereum", "solana", "base"]),
                    from_address=_addr(rng),
                    to_address=address,
                    value=Decimal(str(round(amount, 8))),
                    asset_symbol=sym,
                    value_usd=Decimal(str(round(amount * price, 2))),
                    ts=ts,
                )
            )
        return sorted(out, key=lambda t: t.ts, reverse=True)[:limit]

    def exchange_flow(self, asset: str, hours: int = 24) -> list[ExchangeFlow]:
        rng = _stable_rng(f"{self.seed}:flow:{asset}")
        out: list[ExchangeFlow] = []
        for ex in EXCHANGES:
            inflow = rng.uniform(5e6, 80e6)
            outflow = rng.uniform(5e6, 80e6)
            out.append(
                ExchangeFlow(
                    asset_symbol=asset,
                    exchange_name=ex,
                    inflow_usd=Decimal(str(round(inflow, 2))),
                    outflow_usd=Decimal(str(round(outflow, 2))),
                    net_usd=Decimal(str(round(inflow - outflow, 2))),
                    ts=self.now,
                )
            )
        return out

    def holder_stats(self, asset: str) -> HolderStats:
        rng = _stable_rng(f"{self.seed}:holders:{asset}")
        total = int(rng.uniform(200_000, 4_000_000))
        change = int(rng.gauss(0, 2500))
        return HolderStats(
            asset_symbol=asset,
            total_holders=total,
            holders_24h_change=change,
            top10_concentration_pct=round(rng.uniform(8, 45), 2),
            ts=self.now,
        )

    # ---------- protocols / news ----------

    def protocol_metrics(self, protocol: str) -> list[ProtocolMetric]:
        rng = _stable_rng(f"{self.seed}:proto:{protocol}")
        p = next((x for x in PROTOCOLS if x["name"] == protocol), None)
        if p is None:
            return []
        out: list[ProtocolMetric] = []
        for metric, base in (
            ("tvl", p["tvl"]),
            ("fees", p["fees"]),
            ("users", p["users"]),
            ("volume", p["volume"]),
        ):
            for i in range(24):
                ts = self.now - timedelta(hours=23 - i)
                value = base * (0.9 + 0.2 * rng.random()) * (1 + i * 0.002)
                out.append(
                    ProtocolMetric(protocol=protocol, metric=metric, value=round(value, 2), ts=ts)
                )
        return out

    def news(self, hours: int = 24, limit: int = 50) -> list[NewsItem]:
        out: list[NewsItem] = []
        for i, t in enumerate(NEWS_TEMPLATES):
            ts = self.now - timedelta(hours=(i * 2) % 24)
            out.append(
                NewsItem(
                    title=t["title"],
                    summary=f"{t['title']} — mock news aligned to {t['narrative']} narrative.",
                    url=None,
                    source="MockNews",
                    sentiment=t["sentiment"],
                    importance=t["importance"],
                    entity_symbols=t["entities"],
                    ts=ts,
                )
            )
        out.sort(key=lambda n: n.ts, reverse=True)
        return out[:limit]
