"""World Bank 公开宏观指标：主要经济体 GDP/通胀/失业率（免费无 Key，年频数据）。"""

from __future__ import annotations

from typing import Any

from w3ex.providers.http import fetch_json

BASE = "https://api.worldbank.org/v2"

# 主要经济体（iso3 → 中文名）
COUNTRIES: dict[str, str] = {
    "USA": "美国",
    "CHN": "中国",
    "EMU": "欧元区",
    "JPN": "日本",
    "DEU": "德国",
    "GBR": "英国",
    "IND": "印度",
    "KOR": "韩国",
}

# 指标代码 → 展示名（key 固定供前端映射）
INDICATORS: dict[str, str] = {
    "gdp_growth": "NY.GDP.MKTP.KD.ZG",  # GDP 年增速 %
    "inflation": "FP.CPI.TOTL.ZG",  # CPI 通胀 %
    "unemployment": "SL.UEM.TOTL.ZS",  # 失业率 %
    "policy_rate": "FR.INR.RINR",  # 实际利率（近似政策利率）
}

# 部分经济体利率用央行政策利率近似（World Bank 无统一字段时置 None）
TTL_SECONDS = 12 * 3600


class WorldBankProvider:
    """宏观指标快照：{countries: [{iso3, name, metrics: {key: {value, year}}}], source}。"""

    name = "worldbank"

    async def _indicator(self, iso3: str, code: str) -> dict[str, Any] | None:
        data = await fetch_json(
            f"{BASE}/country/{iso3}/indicator/{code}",
            params={"format": "json", "mrnev": 1, "per_page": 1},
            ttl=TTL_SECONDS,
        )
        if not isinstance(data, list) or len(data) < 2 or not data[1]:
            return None
        row = data[1][0]
        if row.get("value") is None:
            return None
        return {"value": round(float(row["value"]), 2), "year": str(row.get("date", ""))}

    async def get_macro_overview(self) -> dict[str, Any]:
        import asyncio

        async def country_block(iso3: str, zh: str) -> dict[str, Any]:
            keys = list(INDICATORS)
            results = await asyncio.gather(
                *(self._indicator(iso3, code) for code in INDICATORS.values())
            )
            metrics = {k: v for k, v in zip(keys, results, strict=True) if v is not None}
            return {"iso3": iso3, "name": zh, "metrics": metrics}

        blocks = await asyncio.gather(*(country_block(iso3, zh) for iso3, zh in COUNTRIES.items()))
        return {
            "countries": [b for b in blocks if b["metrics"]],
            "source": "worldbank",
            "note": "World Bank 年度数据，policy_rate 为实际利率近似值",
        }

    async def get_indicator_series(
        self, iso3: str, indicator_key: str, start_year: int = 1960
    ) -> dict[str, Any]:
        """单指标完整时间序列（1960 至今，供可点击展开的长周期图表）。"""
        code = INDICATORS.get(indicator_key)
        if code is None:
            raise ValueError(f"未知指标：{indicator_key}")
        data = await fetch_json(
            f"{BASE}/country/{iso3}/indicator/{code}",
            params={"format": "json", "date": f"{start_year}:2025", "per_page": 200},
            ttl=TTL_SECONDS,
        )
        series: list[dict[str, Any]] = []
        if isinstance(data, list) and len(data) >= 2 and data[1]:
            for row in data[1]:
                if row.get("value") is None:
                    continue
                series.append({"year": str(row["date"]), "value": round(float(row["value"]), 2)})
        series.sort(key=lambda x: x["year"])
        return {
            "iso3": iso3,
            "name": COUNTRIES.get(iso3, iso3),
            "indicator": indicator_key,
            "indicator_name": {
                "gdp_growth": "GDP 年增速 %",
                "inflation": "CPI 通胀 %",
                "unemployment": "失业率 %",
                "policy_rate": "实际利率 %（近似）",
            }.get(indicator_key, indicator_key),
            "series": series,
            "source": "worldbank",
        }
