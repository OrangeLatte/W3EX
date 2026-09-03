from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np

UTC = UTC


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def recency_score(
    ts: datetime, now: datetime | None = None, half_life_hours: float = 24.0
) -> float:
    """指数衰减：t=0 时 1.0，经过一个半衰期降到 0.5。范围 (0,1]。"""
    now = _as_utc(now or datetime.now(UTC))
    age_seconds = max(0.0, (now - _as_utc(ts)).total_seconds())
    half_life_seconds = half_life_hours * 3600.0
    return float(math.exp(-math.log(2) * age_seconds / max(1.0, half_life_seconds)))


def impact_score(amount_usd: float, typical_usd: float) -> float:
    """相对典型规模的冲击分，对数压缩到 (0,1]。amount 为 10x 典型值时 ~0.6。"""
    if amount_usd <= 0 or typical_usd <= 0:
        return 0.0
    ratio = amount_usd / typical_usd
    return float(1.0 - math.exp(-math.log1p(ratio) / 6.0))


def novelty_score(zscore: float) -> float:
    """基于 z 分数的新颖度：>3σ 接近 1。"""
    return float(1.0 - math.exp(-abs(zscore) / 3.0))


def confidence_score(base: float, evidence_count: int, decay: float = 0.3) -> float:
    """置信度 = base 与证据数量共同决定，证据越多越趋近 1。"""
    evidence_factor = 1.0 - math.exp(-evidence_count * decay)
    return float(min(1.0, base * 0.6 + evidence_factor * 0.4))


def priority_score(impact: float, novelty: float, confidence: float, recency: float) -> float:
    """Priority = Impact × Novelty × Confidence × Recency（透明、可解释）。"""
    return float(impact * novelty * confidence * recency)


def zscore(series: list[float], value: float) -> float:
    """样本 z 分数；std 为 0 时返回 0。"""
    arr = np.asarray(series, dtype=float)
    if arr.size < 2:
        return 0.0
    mean = float(arr.mean())
    std = float(arr.std(ddof=1))
    if std == 0:
        return 0.0
    return (value - mean) / std


def momentum_from_returns(returns_pct: list[float], half_life_hours: float = 12.0) -> float:
    """指数加权近期收益 → 0..100 动量分。近期权重更高，全部为负时为低分。"""
    if not returns_pct:
        return 50.0
    weights = [
        math.exp(-math.log(2) * i / max(1, len(returns_pct) // 2)) for i in range(len(returns_pct))
    ]
    w = np.asarray(weights[::-1], dtype=float)
    w /= w.sum()
    score = float(np.dot(np.asarray(returns_pct, dtype=float), w))
    return float(min(100.0, max(0.0, 50.0 + score * 5.0)))


def trend_from_scores(score_now: float, score_before: float, threshold: float = 3.0) -> str:
    if score_now - score_before > threshold:
        return "rising"
    if score_before - score_now > threshold:
        return "falling"
    return "flat"


def stablecoin_flow_score(inflow_usd: float, outflow_usd: float) -> float:
    """稳定币净流入比 -> -1..1，正表示资金流入生态。"""
    total = inflow_usd + outflow_usd
    if total <= 0:
        return 0.0
    return (inflow_usd - outflow_usd) / total
