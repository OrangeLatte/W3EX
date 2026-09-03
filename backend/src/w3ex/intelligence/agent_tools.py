"""AI 教练工具注册表：让 Agent 通过 Function Calling 操作行情/账户/交易/复盘。

设计原则（评审 PDF 6.2 风险优先执行）：
- 交易类工具双阶段：confirmed=false 只返回预览（价格/数量/费用/风险）；
  confirmed=true 才真正执行，且系统提示要求模型必须在用户明确确认后才能置 true。
- 全部工具只读/操作**模拟盘**（PaperEngine），不触及真实资金。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.providers.base import MarketDataProvider


def build_tools(
    session: AsyncSession, market: MarketDataProvider | None, user_key: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """返回 (openai tools schema 列表, dispatch 表)。dispatch[name] 为 async handler(args)->str。"""
    from w3ex.execution.paper import PaperEngine, account_summary
    from w3ex.intelligence.assets import build_asset_detail
    from w3ex.intelligence.market import build_market_overview

    schemas: list[dict[str, Any]] = []
    dispatch: dict[str, Any] = {}

    def tool(name: str, description: str, parameters: dict[str, Any]):
        """注册装饰器：handler 进 dispatch，schema 进 schemas。"""

        def deco(fn):
            dispatch[name] = fn
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    },
                }
            )
            return fn

        return deco

    @tool(
        "get_market_overview",
        "获取全市场总览：市场状态（Risk-on/off）、主要资产涨跌、领涨领跌 Top5、资金费率",
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_market_overview(_args: dict) -> str:
        if market is None:
            return "行情源不可用"
        ov = await build_market_overview(market)
        r = ov.get("regime") or {}
        return "\n".join(
            [
                f"市场状态: {r.get('label')} score={r.get('score')}",
                "主要资产: "
                + ", ".join(f"{k} {v:+.2f}%" for k, v in (ov.get("indices") or {}).items()),
                "领涨: "
                + ", ".join(
                    f"{g['symbol']} {g['change_24h_pct']:+.1f}%"
                    for g in (ov.get("gainers") or [])[:5]
                ),
                "领跌: "
                + ", ".join(
                    f"{g['symbol']} {g['change_24h_pct']:+.1f}%"
                    for g in (ov.get("losers") or [])[:5]
                ),
                "资金费率: "
                + ", ".join(
                    f"{f['symbol']} {f['rate']:+.4%}" for f in (ov.get("funding") or [])[:3]
                ),
            ]
        )

    @tool(
        "get_asset_snapshot",
        "获取单标的详情快照：现价/24h 涨跌/振幅/资金费率/数据源。分析任何币种前先调用本工具。",
        {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "如 BTC、ETH、SOL"},
                "interval": {"type": "string", "enum": ["1m", "5m", "15m", "1h", "4h", "1d"]},
            },
            "required": ["symbol"],
        },
    )
    async def get_asset_snapshot(args: dict) -> str:
        if market is None:
            return "行情源不可用"
        d = await build_asset_detail(args["symbol"], market, interval=args.get("interval", "1h"))
        st = d.get("stats") or {}
        fr = d.get("funding_rate")
        return (
            f"{d['symbol']} 现价 ${d['price']} 24h {d.get('change_24h_pct'):+.2f}%\n"
            f"24h 高/低: {st.get('high_24h')}/{st.get('low_24h')} "
            f"振幅 {st.get('amplitude_pct')}%\n"
            f"资金费率: {fr if fr is not None else 'N/A'}\n"
            f"数据源: {(d.get('sources') or {}).get('market')}"
        )

    @tool(
        "get_account",
        "获取用户模拟交易账户：权益/已实现/未实现盈亏/占用保证金/可用资金/开放仓位明细",
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_account(_args: dict) -> str:
        s = await account_summary(session, user_key, market=market)
        positions = await PaperEngine(market).list_positions(
            session, status="open", user_key=user_key
        )
        lines = [
            f"权益 ${s['equity_usd']} | 已实现 {s['realized_pnl_usd']} | 未实现 {s['unrealized_pnl_usd']}",
            f"占用保证金 {s['margin_used_usd']} | 可用 {s['available_usd']} | 委托数 {s['orders_count']}",
        ]
        for p in positions[:6]:
            lines.append(
                f"- {p['asset']} {p['side']} {p['quantity']} @ {p['entry_price']} {p['leverage']}x"
                f" 未实现 {p.get('unrealized_pnl_usd', 'N/A')}"
            )
        return "\n".join(lines)

    @tool(
        "get_trade_history",
        "获取用户模拟交易历史订单（最近 20 笔）：时间/方向/资产/类型/成交价/状态",
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_trade_history(_args: dict) -> str:
        engine = PaperEngine(market)
        rows = await engine.list_orders(session, status="all", limit=20, user_key=user_key)
        if not rows:
            return "暂无交易记录"
        return "\n".join(
            f"- {r['ts'][:16]} {r['side']} {r['asset']} {r['order_type']} "
            f"qty={r['quantity']} @ {r['fill_price'] or r['limit_price']} {r['status']}"
            for r in rows
        )

    @tool(
        "place_order",
        "在模拟盘下单（双阶段）。第一步 confirmed=false 获取预览（价格/数量/费用/风险）；"
        "必须先把预览展示给用户、得到明确同意后才能以 confirmed=true 执行。"
        "现货用 market_type=spot（杠杆固定 1），永续用 perp 并指定 leverage(1/2/5/10/20)。",
        {
            "type": "object",
            "properties": {
                "side": {"type": "string", "enum": ["buy", "sell"]},
                "asset": {"type": "string", "description": "如 BTC、ETH"},
                "order_type": {"type": "string", "enum": ["market", "limit"]},
                "amount_usd": {"type": "string", "description": "金额（美元，字符串）"},
                "market_type": {"type": "string", "enum": ["spot", "perp"]},
                "leverage": {"type": "integer", "enum": [1, 2, 5, 10, 20]},
                "limit_price": {"type": "string"},
                "confirmed": {
                    "type": "boolean",
                    "description": "仅当用户在对话中明确同意该笔预览后才可 true",
                },
            },
            "required": ["side", "asset", "order_type", "amount_usd", "market_type", "confirmed"],
        },
    )
    async def place_order(args: dict) -> str:
        if market is None:
            return "行情源不可用，无法下单"
        engine = PaperEngine(market)
        a: dict[str, Any] = {
            "side": args["side"],
            "asset": args["asset"].upper(),
            "order_type": args.get("order_type", "market"),
            "amount_usd": Decimal(str(args["amount_usd"])),
            "market_type": args.get("market_type", "spot"),
            "leverage": int(args.get("leverage", 1)),
            "limit_price": Decimal(str(args["limit_price"])) if args.get("limit_price") else None,
        }
        if not args.get("confirmed"):
            try:
                px = await market.get_price(a["asset"])
                ref = px.ask if a["side"] == "buy" else px.bid
                qty = a["amount_usd"] / ref
                fee = a["amount_usd"] * Decimal("0.001")
                lev = a["leverage"] if a["market_type"] == "perp" else 1
                return (
                    f"[下单预览·未执行] {a['side']} {a['asset']} ${a['amount_usd']} "
                    f"{a['market_type']} {lev}x\n"
                    f"参考价 ${ref} 数量 ≈{qty:.6f} 预估手续费 ${fee:.2f}\n"
                    "请向用户展示以上预览，获得明确确认后以 confirmed=true 重新调用本工具。"
                )
            except Exception as exc:  # noqa: BLE001
                return f"[预览失败] {exc!r}"
        try:
            order = await engine.create_order(session, user_key=user_key, **a)
        except ValueError as exc:
            return f"[下单被拒绝] {exc}"
        return (
            f"[已执行] 订单 {order['order_id'][:8]} {order['side']} {order['asset']} "
            f"qty={order['quantity']} @ {order.get('fill_price')} {order['status']}"
        )

    @tool(
        "get_review_report",
        "获取复盘统计：交易笔数/平仓数/已实现盈亏合计/胜率/最近交易明细",
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_review_report(_args: dict) -> str:
        from w3ex.intelligence.agent import _fmt_review_ctx

        return await _fmt_review_ctx(session, user_key)

    @tool(
        "get_macro_overview",
        "获取宏观面板：全球股指/大宗商品行情与数据源",
        {"type": "object", "properties": {}, "required": []},
    )
    async def get_macro_overview(_args: dict) -> str:
        from w3ex.api.routes.macro import build_macro_overview

        ov = await build_macro_overview()
        idx = ", ".join(
            f"{i['symbol']} {i['change_pct']:+.2f}%" for i in (ov.get("indices") or [])[:5]
        )
        com = ", ".join(
            f"{c['symbol']} {c['change_pct']:+.2f}%" for c in (ov.get("commodities") or [])[:5]
        )
        return f"股指: {idx}\n商品: {com}\n数据源: {ov.get('sources')}"

    return schemas, dispatch
