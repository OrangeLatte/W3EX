"""AI 交易教练：四类 Agent（评审 PDF 6.2）。

导师（苏格拉底式提问）/ 市场侦察（主动行情简报）/
风险教练（账户与仓位风险体检）/ 复盘（历史交易报告）。

无 LLM 绑定时全部回退到确定性规则引擎（数据真实，只有措辞降级）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.db.models import AiBinding, Positions
from w3ex.intelligence.ai import DISCLAIMER, client_from_binding
from w3ex.providers.base import MarketDataProvider

AGENT_KINDS = ("mentor", "scout", "risk", "review")

AGENT_META = {
    "mentor": {"name": "交易导师", "en": "Mentor", "style": "socratic"},
    "scout": {"name": "市场侦察", "en": "Scout", "style": "briefing"},
    "risk": {"name": "风险教练", "en": "Risk Coach", "style": "checklist"},
    "review": {"name": "复盘教练", "en": "Reviewer", "style": "report"},
}

SYSTEMS = {
    "mentor": (
        "你是加密交易导师，用苏格拉底式提问引导用户自己思考，"
        "一次最多 3 个问题，不给买卖建议。区分事实/解读/假设。"
    ),
    "scout": (
        "你是市场侦察兵，输出结构化简报：①市场状态 ②异动 ③值得关注的信号。"
        "遇到行情/宏观问题先用 get_market_overview 或 get_asset_snapshot 取真实数据再回答。不构成投资建议。"
    ),
    "risk": (
        "你是风险教练，对用户账户做风险体检：杠杆暴露、集中度、强平距离、缺失的止损。"
        "回答账户/持仓问题前先用 get_account 取真实数据。只评估不预测价格。"
    ),
    "review": (
        "你是复盘教练，基于历史交易生成复盘报告：胜率、已实现盈亏、改进点。"
        "回答复盘问题前先用 get_review_report 或 get_trade_history 取真实数据。引用具体交易事实，不臆测。"
    ),
}

TOOL_RULE = (
    "\n\n[工具使用规则]\n"
    "1. 涉及实时数据（行情/账户/持仓/历史/宏观）必须先调用对应工具取数，禁止编造数字。\n"
    "2. place_order 为模拟盘下单：先 confirmed=false 出预览，用户明确同意后才可 confirmed=true 执行；"
    "未经确认永远不得执行。\n"
    "3. 工具返回的是事实摘要，回答时引用并注明来源。"
)


def _fmt_market_ctx(overview: dict[str, Any]) -> str:
    r = overview.get("regime") or {}
    majors = overview.get("indices") or {}
    gainers = (overview.get("gainers") or [])[:3]
    losers = (overview.get("losers") or [])[:3]
    lines = [
        f"市场状态: {r.get('label')} ({r.get('regime')}, score={r.get('score')})",
        "主要资产: " + ", ".join(f"{k} {v:+.2f}%" for k, v in majors.items()),
        "领涨: " + ", ".join(f"{g['symbol']} {g['change_24h_pct']:+.2f}%" for g in gainers),
        "领跌: " + ", ".join(f"{g['symbol']} {g['change_24h_pct']:+.2f}%" for g in losers),
    ]
    return "\n".join(lines)


async def _fmt_account_ctx(session: AsyncSession, user_key: str) -> str:
    from w3ex.execution.paper import account_summary

    s = await account_summary(session, user_key)
    positions = (
        (
            await session.execute(
                select(Positions).where(Positions.user_key == user_key, Positions.status == "open")
            )
        )
        .scalars()
        .all()
    )
    lines = [
        f"账户权益: ${s['equity_usd']}（已实现 {s['realized_pnl_usd']} / 未实现 {s['unrealized_pnl_usd']}）",
        f"开放仓位: {len(positions)}",
    ]
    for p in positions[:5]:
        lines.append(
            f"- {p.asset_symbol} {p.side} {p.quantity} @ {p.entry_price} {p.leverage}x"
            f"（margin {p.margin_usd}）"
        )
    return "\n".join(lines)


def _rule_reply(kind: str, message: str, context: str) -> str:
    """规则引擎回退：输出真实数据摘要（措辞简单但事实准确）。"""
    if kind == "mentor":
        q = [
            "这笔交易你计划在什么情况下承认自己错了（失效条件）？",
            "你的仓位大小是基于固定比例还是主观判断？",
            "如果行情没有按预期走，你的第一步动作是什么？",
        ]
        return "先不急着下结论，请回答三个问题：\n" + "\n".join(q)
    if kind == "scout":
        return "当前市场简报（规则引擎）：\n" + context
    if kind == "risk":
        return "账户风险体检（规则引擎）：\n" + context
    return "历史交易复盘（规则引擎）：\n" + context


async def run_agent(
    session: AsyncSession,
    kind: str,
    message: str,
    history: list[dict[str, str]],
    market: MarketDataProvider | None,
    user_key: str = "default",
    use_tools: bool = True,
    lang: str = "zh",
) -> dict[str, Any]:
    """统一 Agent 入口：按 kind 组装上下文 → Function Calling 工具循环（绑定）或规则回退。

    工具循环（评审 6.2 工具调用）：LLM 请求 tool_calls → 执行真实工具 →
    结果回填 → 最多 5 轮 → 最终回复。tool_trace 记录每步调用供前端展示。
    """
    if kind not in AGENT_KINDS:
        raise ValueError(f"未知 Agent 类型：{kind}")

    from w3ex.intelligence.agent_tools import build_tools
    from w3ex.intelligence.market import build_market_overview

    context = ""
    if kind in ("scout", "mentor") and market is not None:
        try:
            context = _fmt_market_ctx(await build_market_overview(market))
        except Exception:  # noqa: BLE001 — 行情失败不阻塞 Agent
            context = "（行情数据暂不可用）"
    elif kind == "risk":
        context = await _fmt_account_ctx(session, user_key)
    elif kind == "review":
        context = await _fmt_review_ctx(session, user_key)

    meta = AGENT_META[kind]
    b: AiBinding | None = (
        (await session.execute(select(AiBinding).order_by(AiBinding.created_at.desc()).limit(1)))
        .scalars()
        .first()
    )
    if b is None:
        return {
            "agent": kind,
            "agent_name": meta["name"],
            "reply": _rule_reply(kind, message, context),
            "context": context,
            "source": "rule",
            "disclaimer": DISCLAIMER,
        }

    client = client_from_binding(b)
    _lang_name = {
        "zh": "中文",
        "en": "English",
        "fr": "Français",
        "es": "Español",
        "ar": "العربية",
        "ru": "Русский",
    }.get(lang, "中文")
    msgs: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": SYSTEMS[kind]
            + TOOL_RULE
            + f"\n\nIMPORTANT: Always write your entire reply in {_lang_name}.",
        }
    ]
    if context:
        msgs.append({"role": "system", "content": f"[上下文数据]\n{context}"})
    for h in history[-6:]:
        role = h.get("role")
        if role in ("user", "assistant") and h.get("content"):
            msgs.append({"role": role, "content": h["content"]})
    msgs.append({"role": "user", "content": message or "请输出你的观察"})

    schemas, dispatch = build_tools(session, market, user_key) if use_tools else ([], {})
    tool_trace: list[dict[str, Any]] = []
    try:
        reply = ""
        for _round in range(5):
            out = await client.chat_tools(msgs, tools=schemas or None, max_tokens=4096)
            calls = out.get("tool_calls") or []
            if not calls:
                reply = out.get("content") or out.get("reasoning") or ""
                break
            # 回填 assistant tool_calls 消息（openai 协议要求原样带回）
            msgs.append(
                {"role": "assistant", "content": out.get("content") or None, "tool_calls": calls}
            )
            for c in calls:
                fn = c.get("function") or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments") or "{}"
                try:
                    import json as _json

                    args = _json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except ValueError:
                    args = {}
                handler = dispatch.get(name)
                if handler is None:
                    result = f"[未知工具 {name}]"
                    ok = False
                else:
                    try:
                        result = await handler(args)
                        ok = True
                    except Exception as exc:  # noqa: BLE001 — 工具失败回填给模型自行处理
                        result = f"[工具执行失败] {exc!r}"
                        ok = False
                tool_trace.append(
                    {"tool": name, "args": args, "ok": ok, "summary": str(result)[:200]}
                )
                msgs.append(
                    {"role": "tool", "tool_call_id": c.get("id") or name, "content": result}
                )
        else:
            reply = reply or "（工具循环轮次用尽，请缩小问题范围重试）"
        source = f"llm:{b.model or ''}".rstrip(":")
    except Exception as exc:  # noqa: BLE001 — LLM 失败回退规则
        return {
            "agent": kind,
            "agent_name": meta["name"],
            "reply": _rule_reply(kind, message, context) + f"\n\n[模型调用失败：{exc}]",
            "context": context,
            "source": "rule",
            "disclaimer": DISCLAIMER,
        }
    if not reply:
        reply = _rule_reply(kind, message, context) + "\n\n[模型未返回文本，已回退规则引擎]"
        source = "rule"
    return {
        "agent": kind,
        "agent_name": meta["name"],
        "reply": reply,
        "context": context,
        "source": source,
        "disclaimer": DISCLAIMER,
        "tool_trace": tool_trace,
    }


async def _fmt_review_ctx(session: AsyncSession, user_key: str) -> str:
    """复盘上下文：按资产聚合已实现盈亏。"""
    rows = (
        (
            await session.execute(
                select(Positions)
                .where(Positions.user_key == user_key)
                .order_by(Positions.ts.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return "暂无历史交易。先在交易页完成模拟交易，再来复盘。"
    total = sum((p.realized_pnl for p in rows), start=0)
    closed = [p for p in rows if p.status == "closed"]
    wins = [p for p in closed if p.realized_pnl > 0]
    lines = [
        f"交易笔数: {len(rows)}（平仓 {len(closed)}）",
        f"已实现盈亏合计: ${total}",
        f"胜率: {len(wins)}/{len(closed)}" if closed else "暂无平仓记录",
    ]
    for p in rows[:5]:
        lines.append(
            f"- {p.asset_symbol} {p.side} {p.leverage}x {p.status} pnl={p.realized_pnl}"
            + (f" @ {p.closed_price}" if p.closed_price else "")
        )
    return "\n".join(lines)
