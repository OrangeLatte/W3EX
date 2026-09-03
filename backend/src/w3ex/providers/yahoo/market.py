"""Yahoo Finance 公开行情：全球股指与大宗商品（免费无 Key，经系统代理可达）。

chart API: https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=&interval=
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from w3ex.providers.http import fetch_json

BASE = "https://query1.finance.yahoo.com/v8/finance/chart"

# 全球主要股指（展示名 → yahoo symbol）
INDEX_SYMBOLS: dict[str, str] = {
    "SPX": "^GSPC",  # 标普500
    "NDX": "^IXIC",  # 纳斯达克
    "DJI": "^DJI",  # 道琼斯
    "DAX": "^GDAXI",  # 德国DAX
    "FTSE": "^FTSE",  # 英国富时100
    "N225": "^N225",  # 日经225
    "HSI": "^HSI",  # 恒生指数
}

# 主要大宗商品期货
COMMODITY_SYMBOLS: dict[str, str] = {
    "XAU": "GC=F",  # 黄金
    "XAG": "SI=F",  # 白银
    "WTI": "CL=F",  # WTI 原油
    "BRENT": "BZ=F",  # 布伦特原油
    "NATGAS": "NG=F",  # 天然气
    "COPPER": "HG=F",  # 铜
}

NAME_ZH: dict[str, str] = {
    "SPX": "标普500",
    "NDX": "纳斯达克",
    "DJI": "道琼斯",
    "DAX": "德国DAX",
    "FTSE": "富时100",
    "N225": "日经225",
    "HSI": "恒生指数",
    "XAU": "黄金",
    "XAG": "白银",
    "WTI": "WTI原油",
    "BRENT": "布伦特原油",
    "NATGAS": "天然气",
    "COPPER": "铜",
}


class YahooProvider:
    """股指 / 大宗商品快照与历史序列。不参与加密货币行情链路。"""

    name = "yahoo"

    async def _chart(self, yahoo_symbol: str, rng: str, interval: str) -> dict[str, Any]:
        data = await fetch_json(
            f"{BASE}/{yahoo_symbol}",
            params={"range": rng, "interval": interval, "includePrePost": "false"},
            ttl=60,
        )
        result = (data.get("chart") or {}).get("result") or []
        if not result:
            raise ValueError(f"yahoo chart empty: {yahoo_symbol}")
        return result[0]

    async def get_group_quotes(self, group: dict[str, str]) -> list[dict[str, Any]]:
        """并发抓取一组 yahoo symbol 的快照：[{symbol, name, price, change_pct, ts}]。"""
        import asyncio

        async def one(key: str, ys: str) -> dict[str, Any] | None:
            try:
                r = await self._chart(ys, "5d", "1d")
                meta = r.get("meta") or {}
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                if price is None or prev in (None, 0):
                    return None
                return {
                    "symbol": key,
                    "yahoo_symbol": ys,
                    "name": NAME_ZH.get(key, key),
                    "price": round(float(price), 2),
                    "change_pct": round((float(price) - float(prev)) / float(prev) * 100, 2),
                    "ts": datetime.utcnow().isoformat(),
                }
            except Exception:  # noqa: BLE001 — 单个标的失败不阻塞整组
                return None

        pairs = list(group.items())
        results = await asyncio.gather(*(one(k, v) for k, v in pairs))
        return [r for r in results if r is not None]

    async def get_indices(self) -> list[dict[str, Any]]:
        return await self.get_group_quotes(INDEX_SYMBOLS)

    async def get_commodities(self) -> list[dict[str, Any]]:
        return await self.get_group_quotes(COMMODITY_SYMBOLS)

    async def get_history(
        self, yahoo_symbol: str, rng: str = "1mo", interval: str = "1d"
    ) -> list[dict[str, Any]]:
        """历史收盘序列（供动态图表）：[{ts, close}]。"""
        r = await self._chart(yahoo_symbol, rng, interval)
        ts_list = r.get("timestamp") or []
        closes = ((r.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
        out: list[dict[str, Any]] = []
        for ts, c in zip(ts_list, closes, strict=False):
            if c is None:
                continue
            out.append(
                {
                    "ts": datetime.utcfromtimestamp(int(ts)).isoformat(),  # noqa: DTZ006
                    "close": round(float(c), 4),
                }
            )
        return out

    async def get_ohlc(
        self, yahoo_symbol: str, rng: str = "1mo", interval: str = "1d"
    ) -> list[dict[str, Any]]:
        """宏观标的 K 线：[{ts,o,h,l,c,v}]，形状对齐 Candle 前端契约。"""
        r = await self._chart(yahoo_symbol, rng, interval)
        ts_list = r.get("timestamp") or []
        quote = ((r.get("indicators") or {}).get("quote") or [{}])[0]
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        vols = quote.get("volume") or []
        out: list[dict[str, Any]] = []
        for i, ts in enumerate(ts_list):
            if i >= len(closes) or None in (opens[i], highs[i], lows[i], closes[i]):
                continue
            out.append(
                {
                    "ts": datetime.utcfromtimestamp(int(ts)).isoformat(),  # noqa: DTZ006
                    "o": round(float(opens[i]), 4),
                    "h": round(float(highs[i]), 4),
                    "l": round(float(lows[i]), 4),
                    "c": round(float(closes[i]), 4),
                    "v": round(float(vols[i]), 2) if i < len(vols) and vols[i] else 0.0,
                }
            )
        return out
