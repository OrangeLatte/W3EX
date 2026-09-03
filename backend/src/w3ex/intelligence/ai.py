"""AI 智能层：绑定管理 + Regime 技术分析简报 + 标的对话分析。

无绑定或调用失败时回退到规则引擎（确定性技术摘要），
响应始终标注 source（llm|rule）与免责声明——不把规则分析冒充 AI 输出。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.db.models import AiBinding
from w3ex.providers.llm.client import LLMClient, LLMError

DISCLAIMER = "以上内容由模型生成，仅供研究参考，不构成任何投资建议。"


# ---------- 绑定管理 ----------


async def get_active_binding(session: AsyncSession) -> AiBinding | None:
    result = await session.execute(select(AiBinding).order_by(AiBinding.created_at.desc()).limit(1))
    return result.scalar_one_or_none()


def client_from_binding(b: AiBinding) -> LLMClient:
    return LLMClient(provider=b.provider, base_url=b.base_url, api_key=b.api_key, model=b.model)


def mask_key(key: str) -> str:
    if len(key) <= 8:
        return "***"
    return f"{key[:4]}***{key[-4:]}"


async def binding_status(session: AsyncSession) -> dict[str, Any]:
    b = await get_active_binding(session)
    if b is None:
        return {"bound": False}
    return {
        "bound": True,
        "provider": b.provider,
        "label": b.label,
        "base_url": b.base_url,
        "api_key_masked": mask_key(b.api_key),
        "model": b.model,
        "status": b.status,
        "last_checked_at": b.last_checked_at.isoformat() if b.last_checked_at else None,
    }


# ---------- Prompt 组装 ----------

SYSTEM_BRIEF = (
    "你是资深加密市场技术分析师。基于给定数据输出简体中文简报。"
    "严格区分【事实】（引用具体数字）与【解读】（模式识别），"
    "结尾必须说明不确定性。不要给出具体买卖建议或目标价。"
    '输出 JSON：{"summary": [3条要点], "detail": "详细分析(300字内)", '
    '"uncertainty": "不确定性与数据局限"}'
)

SYSTEM_CHAT = (
    "你是加密资产技术分析助手，围绕用户提问、基于给定指标上下文回答。"
    "引用具体数据，区分事实与推测，不构成投资建议。用简体中文回答，简洁有条理。"
)


def _fmt_regime_context(ctx: dict[str, Any]) -> str:
    lines = [f"市场体制: {ctx.get('regime_label')} (score={ctx.get('regime_score')})"]
    for sym, chg in (ctx.get("majors") or {}).items():
        lines.append(f"{sym} 24h: {chg:+.2f}%")
    gainers = ", ".join(
        f"{g['symbol']} {g['change_24h_pct']:+.1f}%" for g in (ctx.get("gainers") or [])[:5]
    )
    losers = ", ".join(
        f"{g['symbol']} {g['change_24h_pct']:+.1f}%" for g in (ctx.get("losers") or [])[:5]
    )
    lines.append(f"领涨: {gainers}")
    lines.append(f"领跌: {losers}")
    if ctx.get("funding_extremes"):
        f_ = ", ".join(
            f"{f['symbol']} {f['rate'] * 100:+.4f}%" for f in ctx["funding_extremes"][:3]
        )
        lines.append(f"资金费率极值: {f_}")
    if ctx.get("macro_headline"):
        lines.append(f"宏观: {ctx['macro_headline']}")
    return "\n".join(lines)


async def regime_brief(session: AsyncSession, ctx: dict[str, Any]) -> dict[str, Any]:
    """市场体制 AI 简报。ctx 由调用方从 overview 数据中提取。"""
    context_text = _fmt_regime_context(ctx)
    b = await get_active_binding(session)
    if b is None:
        return {
            "source": "rule",
            "model": None,
            "summary": _rule_brief_summary(ctx),
            "detail": _rule_brief_detail(ctx),
            "uncertainty": "当前未绑定模型 API，展示规则引擎摘要（确定性计算）；绑定后可获得模型深度解读。",
            "disclaimer": DISCLAIMER,
        }
    client = client_from_binding(b)
    try:
        raw = await client.chat(
            [
                {"role": "system", "content": SYSTEM_BRIEF},
                {
                    "role": "user",
                    "content": f"请基于以下市场数据生成技术分析简报：\n{context_text}",
                },
            ],
            json_mode=True,
            max_tokens=4096,
        )
        import json

        parsed = json.loads(raw)
        return {
            "source": "llm",
            "model": b.model,
            "summary": parsed.get("summary") or [],
            "detail": parsed.get("detail") or "",
            "uncertainty": parsed.get("uncertainty") or "",
            "disclaimer": DISCLAIMER,
        }
    except (LLMError, ValueError) as exc:
        return {
            "source": "rule",
            "model": b.model,
            "summary": _rule_brief_summary(ctx),
            "detail": _rule_brief_detail(ctx),
            "uncertainty": f"模型调用失败（{exc}），已回退规则引擎摘要。",
            "disclaimer": DISCLAIMER,
        }


def _rule_brief_summary(ctx: dict[str, Any]) -> list[str]:
    majors = ctx.get("majors") or {}
    btc = majors.get("BTC", 0.0)
    score = ctx.get("regime_score", 0)
    out = [
        f"市场体制判定为「{ctx.get('regime_label')}」，加权动量分 {score:+.0f}。",
        f"BTC 24h {btc:+.2f}%，主导方向与体制得分一致。",
    ]
    gainers = ctx.get("gainers") or []
    if gainers:
        out.append(
            f"资金聚焦 {gainers[0]['symbol']}（{gainers[0]['change_24h_pct']:+.1f}%），长尾活跃度"
            + ("偏高" if len(gainers) >= 3 and gainers[2]["change_24h_pct"] > 8 else "温和")
            + "。"
        )
    return out


def _rule_brief_detail(ctx: dict[str, Any]) -> str:
    majors = ctx.get("majors") or {}
    parts = [
        f"体制加权分 {ctx.get('regime_score', 0):+.0f} 由 BTC(×5)/ETH(×3)/SOL(×2) 24h 变动合成，"
        f"当前读数对应「{ctx.get('regime_label')}」。"
    ]
    for sym in ("BTC", "ETH", "SOL"):
        if sym in majors:
            parts.append(f"{sym} 24h {majors[sym]:+.2f}%")
    funding = ctx.get("funding_extremes") or []
    if funding:
        top = funding[0]
        lean = "多头拥挤" if top["rate"] > 0 else "空头拥挤"
        parts.append(
            f"永续资金费率极值 {top['symbol']} {top['rate'] * 100:+.4f}%，杠杆情绪偏{lean}。"
        )
    parts.append("结构性解读：领涨榜集中度反映资金偏好，需结合成交量确认趋势质量。")
    return " ".join(parts)


# ---------- 标的对话分析 ----------


def _fmt_asset_context(sym: str, snapshot: dict[str, Any]) -> str:
    lines = [f"标的: {sym}，现价 {snapshot.get('price')}"]
    stats = snapshot.get("stats") or {}
    lines.append(
        f"24h: 开 {stats.get('open')} / 高 {stats.get('high')} / 低 {stats.get('low')} / "
        f"涨跌 {snapshot.get('change_24h_pct'):+.2f}% / 振幅 {stats.get('amplitude_pct')}%"
    )
    ind = snapshot.get("indicators") or {}
    for k, v in ind.items():
        if v is not None:
            lines.append(f"{k}: {v}")
    if snapshot.get("funding_rate") is not None:
        lines.append(f"永续资金费率: {snapshot['funding_rate'] * 100:+.4f}%")
    if snapshot.get("data_quality") == "mock_candles":
        lines.append(
            "⚠️ 数据质量警告: 历史K线与现价量级严重不符（K线疑似模拟回退数据），"
            "请明确指出数据异常，仅基于现价与涨跌做保守分析，不要基于K线指标下结论。"
        )
    return "\n".join(lines)


async def asset_chat(
    session: AsyncSession,
    symbol: str,
    message: str,
    snapshot: dict[str, Any],
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """标的 AI 对话：绑定模型则走 LLM，否则规则引擎从指标生成确定性解读。"""
    context_text = _fmt_asset_context(symbol.upper(), snapshot)
    b = await get_active_binding(session)
    if b is None:
        return {
            "source": "rule",
            "model": None,
            "reply": _rule_asset_reply(symbol.upper(), snapshot, message),
            "disclaimer": DISCLAIMER,
        }
    client = client_from_binding(b)
    msgs: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_CHAT + f"\n\n指标上下文：\n{context_text}"}
    ]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant"):
            msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": message})
    try:
        reply = await client.chat(msgs, max_tokens=4096)
        return {"source": "llm", "model": b.model, "reply": reply, "disclaimer": DISCLAIMER}
    except LLMError as exc:
        return {
            "source": "rule",
            "model": b.model,
            "reply": _rule_asset_reply(symbol.upper(), snapshot, message)
            + f"\n\n（模型调用失败：{exc}，已回退规则引擎）",
            "disclaimer": DISCLAIMER,
        }


async def asset_chat_stream(
    session: AsyncSession,
    symbol: str,
    message: str,
    snapshot: dict[str, Any],
    history: list[dict[str, str]] | None = None,
    stall_seconds: float = 30.0,
):
    """标的 AI 对话流式版：yield {type: step|delta|done|error} 事件。

    步骤事件让前端展示分析阶段；单次等块超过 stall_seconds 判定卡住，
    立即回退规则引擎（容错：不输出一半就沉默）。无绑定直接规则引擎。
    """
    import asyncio

    sym = symbol.upper()
    yield {"type": "step", "stage": "context", "message": "已生成指标上下文"}
    rule_reply = _rule_asset_reply(sym, snapshot, message)
    b = await get_active_binding(session)
    if b is None:
        yield {"type": "delta", "text": rule_reply}
        yield {"type": "done", "source": "rule", "model": None, "disclaimer": DISCLAIMER}
        return
    client = client_from_binding(b)
    context_text = _fmt_asset_context(sym, snapshot)
    msgs: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_CHAT + f"\n\n指标上下文：\n{context_text}"}
    ]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant"):
            msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": message})

    yield {"type": "step", "stage": "generating", "message": "模型生成中"}
    emitted = False
    try:
        agen = client.chat_stream(msgs, max_tokens=4096)
        while True:
            try:
                piece = await asyncio.wait_for(agen.__anext__(), timeout=stall_seconds)
            except StopAsyncIteration:
                break
            except TimeoutError:
                raise LLMError(f"流式输出超过 {stall_seconds:.0f}s 无新内容，疑似卡住") from None
            emitted = True
            yield {"type": "delta", "text": piece}
        if not emitted:
            raise LLMError("模型返回空内容")
        yield {"type": "done", "source": "llm", "model": b.model, "disclaimer": DISCLAIMER}
    except LLMError as exc:
        if emitted:
            yield {"type": "error", "message": f"输出中断：{exc}（以下为规则引擎补充）"}
        else:
            yield {
                "type": "delta",
                "text": rule_reply + f"\n\n（模型调用失败：{exc}，已回退规则引擎）",
            }
        yield {"type": "done", "source": "rule", "model": b.model, "disclaimer": DISCLAIMER}


def _rule_asset_reply(sym: str, snapshot: dict[str, Any], message: str) -> str:
    """规则引擎：从指标快照生成确定性技术解读（无 LLM 时的兜底）。"""
    stats = snapshot.get("stats") or {}
    ind = snapshot.get("indicators") or {}
    chg = snapshot.get("change_24h_pct") or 0.0
    amp = stats.get("amplitude_pct")
    rsi = ind.get("RSI(14)")
    macd = ind.get("MACD")
    lines = [f"{sym} 技术快照（规则引擎，非模型输出）："]
    trend = "上行" if chg > 1 else ("下行" if chg < -1 else "震荡")
    lines.append(f"· 24h 方向偏{trend}（{chg:+.2f}%），日内振幅 {amp}%。")
    if rsi is not None:
        zone = "超买区" if rsi >= 70 else ("超卖区" if rsi <= 30 else "中性区")
        lines.append(f"· RSI(14)={rsi}，处于{zone}。")
    if macd is not None:
        lines.append(f"· MACD 柱={macd}，" + ("动能偏多。" if macd > 0 else "动能偏空。"))
    ma20 = ind.get("MA(20)")
    if ma20 is not None and snapshot.get("price"):
        pos = "上方" if snapshot["price"] > ma20 else "下方"
        lines.append(f"· 现价位于 MA20 {pos}（{ma20}）。")
    lines.append(
        f"针对你的问题「{message}」：以上为基于指标的事实性描述与模式识别，具体决策请结合仓位管理与风险承受能力。"
    )
    return "\n".join(lines)
