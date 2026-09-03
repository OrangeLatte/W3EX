from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from time import perf_counter
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from w3ex.core.schemas import ExecutionQuoteResult
from w3ex.db.models import PaperOrders, TradeQuotes, Trades
from w3ex.execution.paper import PaperEngine
from w3ex.providers.base import ExecutionProvider


class ExecutionRouter:
    """执行路由：获取多通道报价 → 持久化 Quote → 用户确认 → paper fill。

    评审 P0-5：confirm 使用单条原子 UPDATE 抢占状态迁移（无行锁也幂等），
    支持 Idempotency-Key 重放：同一 key 重复确认只产生一笔 trade。
    """

    def __init__(
        self,
        provider: ExecutionProvider,
        session: AsyncSession,
        market_provider: Any | None = None,
    ) -> None:
        self.provider = provider
        self.session = session
        self.market_provider = market_provider

    @staticmethod
    def _execution_stages(kind: str) -> list[dict[str, Any]]:
        """Decision Workspace：分阶段完成状态（paper 模式全部为模拟阶段）。

        CEX：接单 → 撮合 → 结算；DEX：锁价 → 签名 → 广播 → 区块确认；
        永续：接单 → 撮合 → 仓位开立。真实链上阶段在接入钱包后逐级点亮。
        """
        now = datetime.utcnow().isoformat()
        plans = {
            "cex": [
                ("order_accepted", "订单已接收"),
                ("matched", "撮合成交"),
                ("settled", "结算完成"),
            ],
            "dex": [
                ("quote_locked", "报价锁定"),
                ("signed", "交易签名"),
                ("broadcast", "链上广播"),
                ("confirmed", "区块确认"),
            ],
            "perp": [
                ("order_accepted", "订单已接收"),
                ("matched", "撮合成交"),
                ("position_opened", "仓位开立"),
            ],
        }
        return [
            {"stage": s, "label": label, "status": "done", "ts": now, "simulated": True}
            for s, label in plans.get(kind, plans["cex"])
        ]

    @staticmethod
    def _normalize_route(route: Any, side: str, rtt_ms: int) -> dict[str, Any]:
        """路由 dict 规范化：兼容任意 provider（非 composite 不带 instrument_type 等 v2/v3 字段）。

        composite 已标记的 data_age_ms 保留（通道级更精确），否则用整体 RTT。
        """
        r = route.model_dump(mode="json")
        if not r.get("instrument_type"):
            r["instrument_type"] = "perp" if r.get("kind") == "perp" else "spot"
        if side == "sell" and r["instrument_type"] == "spot" and not r.get("net_proceeds_usd"):
            r["net_proceeds_usd"] = str(r["estimated_receive"])
            r["comparison_basis"] = "net_proceeds_usd"
        elif not r.get("comparison_basis"):
            r["comparison_basis"] = "total_cost_usd"
        if not r.get("data_age_ms"):
            r["data_age_ms"] = max(rtt_ms, 0)
        if r.get("worst_receive") is None:
            base = r.get("net_proceeds_usd") if side == "sell" else r.get("estimated_receive")
            if base:
                slip = float(r.get("slippage_pct") or 0) / 100
                r["worst_receive"] = str(round(float(base) * (1 - slip), 4))
        return r

    async def _fill_perp_risk(
        self, routes: list[dict[str, Any]], leverage: int, asset: str
    ) -> None:
        """perp 路由填充资金费率 / 保证金 / 强平距离（Decision Workspace 风险段）。"""
        funding_rate: float | None = None
        for r in routes:
            if r.get("instrument_type") != "perp":
                continue
            if funding_rate is None and self.market_provider is not None:
                try:
                    f = await self.market_provider.get_funding(asset)
                    funding_rate = float(f.rate) if f else None
                except Exception:  # noqa: BLE001 — 资金费率缺失不阻塞报价
                    funding_rate = None
            notional = float(Decimal(str(r.get("total_cost_usd") or 0)))
            lev = max(1, leverage)
            r["funding_rate"] = funding_rate
            r["margin_required_usd"] = str(round(notional / lev, 2))
            r["liquidation_distance_pct"] = round(100.0 / lev, 2)

    async def get_quote(
        self,
        side: str,
        asset: str,
        amount: Decimal,
        fiat_currency: str = "USD",
        market_type: str = "spot",
        max_slippage_bps: int = 0,
        max_data_age_ms: int = 0,
        leverage: int = 1,
    ) -> dict[str, Any]:
        if side not in ("buy", "sell"):
            raise ValueError("side 必须是 buy 或 sell")
        if amount <= 0:
            raise ValueError("amount 必须为正数")
        if market_type not in ("spot", "perp"):
            raise ValueError("market_type 必须是 spot 或 perp")
        if leverage not in (1, 2, 5, 10, 20):
            raise ValueError("leverage 必须是 1/2/5/10/20")

        constraints = {"max_slippage_bps": max_slippage_bps, "max_data_age_ms": max_data_age_ms}
        t0 = perf_counter()
        result: ExecutionQuoteResult = await self.provider.get_quote(
            side, asset, amount, fiat_currency, market_type, constraints
        )
        rtt_ms = int((perf_counter() - t0) * 1000)
        routes = [self._normalize_route(r, side, rtt_ms) for r in result.routes]

        # Decision Workspace：用户约束过滤（滑点上限 / 数据新鲜度）——对任意 provider 生效
        qualified: list[dict[str, Any]] = []
        filtered: list[dict[str, Any]] = []
        for r in routes:
            slip_bps = round(float(r["slippage_pct"]) * 100)
            if max_slippage_bps and slip_bps > max_slippage_bps:
                filtered.append(
                    {"route": r, "reason": f"滑点 {slip_bps}bps 超过上限 {max_slippage_bps}bps"}
                )
            elif max_data_age_ms and r["data_age_ms"] > max_data_age_ms:
                filtered.append(
                    {
                        "route": r,
                        "reason": f"报价数据年龄 {r['data_age_ms']}ms 超过上限 {max_data_age_ms}ms",
                    }
                )
            else:
                qualified.append(r)

        if not qualified:
            return {
                "quote_id": None,
                "side": side,
                "asset": result.asset_symbol,
                "fiat_amount": str(amount),
                "fiat_currency": fiat_currency,
                "market_type": result.market_type,
                "routes": [],
                "best_route_index": -1,
                "recommendation_reason": "所有路由均不满足约束条件，请放宽滑点或数据新鲜度上限后重新报价",
                "constraints": constraints,
                "filtered_routes": filtered,
                "expires_at": None,
                "status": "unqualified",
            }

        # P0-2：买入按全成本最低，卖出按净到手最高（仅在合格路由中重选）
        if side == "buy":
            best = min(range(len(qualified)), key=lambda i: float(qualified[i]["total_cost_usd"]))
            reason = f"全成本最低：${float(qualified[best]['total_cost_usd']):,.2f}（含价格/滑点/费用/Gas）"
        else:
            best = max(
                range(len(qualified)),
                key=lambda i: float(qualified[i]["net_proceeds_usd"] or 0),
            )
            reason = f"净到手最多：${float(qualified[best]['net_proceeds_usd'] or 0):,.2f}"

        await self._fill_perp_risk(qualified, leverage, result.asset_symbol)

        quote = TradeQuotes(
            id=uuid.uuid4(),
            side=side,
            asset_symbol=result.asset_symbol,
            fiat_amount=amount,
            fiat_currency=fiat_currency,
            routes=qualified,
            best_route_index=best,
            status="pending",
            leverage=leverage,
            expires_at=datetime.utcnow() + timedelta(seconds=result.expires_in_seconds),
            ts=datetime.utcnow(),
        )
        self.session.add(quote)
        await self.session.commit()
        await self.session.refresh(quote)

        return {
            "quote_id": str(quote.id),
            "side": quote.side,
            "asset": quote.asset_symbol,
            "fiat_amount": str(quote.fiat_amount),
            "fiat_currency": quote.fiat_currency,
            "market_type": result.market_type,
            "leverage": leverage,
            "routes": qualified,
            "best_route_index": quote.best_route_index,
            "recommendation_reason": reason,
            "constraints": constraints if (max_slippage_bps or max_data_age_ms) else None,
            "filtered_routes": filtered,
            "expires_at": quote.expires_at.isoformat(),
            "status": quote.status,
        }

    async def confirm(
        self,
        quote_id: str,
        route_index: int,
        idempotency_key: str | None = None,
        user_key: str = "default",
    ) -> dict[str, Any]:
        qid = uuid.UUID(quote_id)

        # 1) Idempotency-Key 重放：同一 key 已执行过 → 返回既有结果，不产生新 trade
        if idempotency_key:
            prior = (
                await self.session.execute(
                    select(TradeQuotes).where(TradeQuotes.idempotency_key == idempotency_key)
                )
            ).scalar_one_or_none()
            if prior is not None and prior.id != qid:
                raise ValueError("该 Idempotency-Key 已被其他报价使用")
            if prior is not None:
                return await self._replay_response(prior)

        quote = await self.session.get(TradeQuotes, qid)
        if quote is None:
            raise KeyError("quote 不存在")
        if quote.expires_at and quote.expires_at < datetime.utcnow():
            await self._mark_expired(qid)
            raise ValueError("quote 已过期，请重新报价")
        if route_index < 0 or route_index >= len(quote.routes):
            raise ValueError("route_index 越界")

        route = quote.routes[route_index]

        # 2) 原子抢占状态迁移：pending → executed（并发/重复请求只有一方成功）
        claim = await self.session.execute(
            update(TradeQuotes)
            .where(TradeQuotes.id == qid, TradeQuotes.status == "pending")
            .values(status="executed", selected_route=route, idempotency_key=idempotency_key)
        )
        if claim.rowcount != 1:
            await self.session.refresh(quote)
            if idempotency_key and quote.idempotency_key == idempotency_key:
                return await self._replay_response(quote)
            raise ValueError(f"quote 状态为 {quote.status}，不可确认")

        # 3) paper fill；失败回滚抢占
        try:
            q_result = ExecutionQuoteResult(
                side=quote.side,
                asset_symbol=quote.asset_symbol,
                fiat_amount=quote.fiat_amount,
                fiat_currency=quote.fiat_currency,
                routes=quote.routes,
                best_route_index=quote.best_route_index,
                expires_in_seconds=60,
                ts=datetime.utcnow(),
            )
            exec_result = await self.provider.execute(q_result, route_index)
        except Exception:
            await self.session.execute(
                update(TradeQuotes)
                .where(TradeQuotes.id == qid, TradeQuotes.status == "executed")
                .values(status="pending", selected_route=None, idempotency_key=None)
            )
            await self.session.commit()
            raise

        trade = Trades(
            quote_id=quote.id,
            status=exec_result.status,
            filled=exec_result.filled,
            paper=exec_result.paper,
            executed_at=datetime.utcnow(),
        )
        self.session.add(trade)
        # 需求⑥：报价确认成交同步计入模拟账户（PaperOrders 按用户隔离），
        # 否则账户卡看不到 quote/confirm 链路的交易
        route_kind = route.get("kind", "cex")
        try:
            price = Decimal(str(route.get("price") or 0))
            filled = exec_result.filled or {}
            receive = Decimal(str(filled.get("receive") or 0))
            qty = (
                receive
                if receive > 0
                else ((quote.fiat_amount / price) if price > 0 else Decimal("0"))
            )
            order_row = PaperOrders(
                side=quote.side,
                asset_symbol=quote.asset_symbol,
                market_type="perp" if route_kind == "perp" else "spot",
                order_type="market",
                quantity=qty.quantize(Decimal("0.00000001")),
                # 报价请求的杠杆落库于 TradeQuotes，confirm 按此杠杆记账（否则恒 1x）
                leverage=quote.leverage or 1,
                status="filled",
                entry_price=price if price > 0 else None,
                fill_price=price if price > 0 else None,
                filled_at=datetime.utcnow(),
                user_key=user_key,
                meta={"quote_id": str(quote.id), "venue": route.get("venue")},
                ts=datetime.utcnow(),
            )
            self.session.add(order_row)
            # perp 市价成交走 netting 开仓（positions 表），账户未实现盈亏链路才生效
            if route_kind == "perp" and self.market_provider is not None and price > 0:
                await self.session.flush()
                engine = PaperEngine(self.market_provider)
                await engine._apply_fill(self.session, order_row, price)
        except Exception:  # noqa: BLE001 — 账户记账失败不影响成交结果
            pass
        await self.session.commit()

        return {
            "quote_id": str(quote.id),
            "status": trade.status,
            "filled": trade.filled,
            "paper": trade.paper,
            "leverage": quote.leverage or 1,
            "selected_route": {
                "venue": route.get("venue"),
                "price": route.get("price"),
                "total_cost_usd": route.get("total_cost_usd"),
            },
            "execution_stages": self._execution_stages(route.get("kind", "cex")),
            "executed_at": trade.executed_at.isoformat(),
            "idempotent_replay": False,
        }

    async def replay(self, quote_id: str) -> dict[str, Any]:
        """Decision Workspace：Paper 演练回放。

        还原用户当时看到的全部路由、选择理由、实际成交，以及
        「如果选另一条路线会怎样」的反事实对比。
        """
        try:
            qid = uuid.UUID(quote_id)
        except ValueError as exc:
            raise ValueError("quote_id 格式非法") from exc
        quote = await self.session.get(TradeQuotes, qid)
        if quote is None:
            raise KeyError("quote 不存在")

        routes = quote.routes or []
        selected = quote.selected_route or {}
        side = quote.side
        actual: dict[str, Any] | None = None
        if quote.status == "executed":
            trade = (
                await self.session.execute(select(Trades).where(Trades.quote_id == quote.id))
            ).scalar_one_or_none()
            if trade is not None:
                actual = {
                    "status": trade.status,
                    "filled": trade.filled,
                    "paper": trade.paper,
                    "executed_at": trade.executed_at.isoformat(),
                }

        # 反事实：如果选了另一条路线会怎样
        counterfactual: list[dict[str, Any]] = []
        if selected:
            sel_recv = Decimal(str(selected.get("estimated_receive") or 0))
            sel_cost = Decimal(str(selected.get("total_cost_usd") or 0))
            for i, r in enumerate(routes):
                if r.get("venue") == selected.get("venue"):
                    continue
                r_recv = Decimal(str(r.get("estimated_receive") or 0))
                r_cost = Decimal(str(r.get("total_cost_usd") or 0))
                if side == "sell":
                    diff_pct = (
                        round(float((r_recv - sel_recv) / sel_recv * 100), 4) if sel_recv else 0.0
                    )
                    better = r_recv > sel_recv
                else:
                    diff_pct = (
                        round(float((sel_cost - r_cost) / sel_cost * 100), 4) if sel_cost else 0.0
                    )
                    better = r_cost < sel_cost
                counterfactual.append(
                    {
                        "venue": r.get("venue"),
                        "route_index": i,
                        "estimated_receive": str(r_recv),
                        "total_cost_usd": str(r_cost),
                        "diff_pct": diff_pct,
                        "would_be_better": better,
                    }
                )

        return {
            "quote_id": str(quote.id),
            "side": side,
            "asset": quote.asset_symbol,
            "fiat_amount": str(quote.fiat_amount),
            "fiat_currency": quote.fiat_currency,
            "status": quote.status,
            "created_at": quote.ts.isoformat(),
            "executed_at": actual["executed_at"] if actual else None,
            "snapshot_routes": routes,
            "selected_venue": selected.get("venue"),
            "selected_route": selected,
            "recommendation_reason": (
                f"已选 {selected.get('venue')}（当时报价快照如下）" if selected else "未选择路由"
            ),
            "actual": actual,
            "counterfactual": counterfactual,
        }

    async def _replay_response(self, quote: TradeQuotes) -> dict[str, Any]:
        if quote.status != "executed":
            raise ValueError(f"quote 状态为 {quote.status}，不可确认")
        trade = (
            await self.session.execute(select(Trades).where(Trades.quote_id == quote.id))
        ).scalar_one_or_none()
        if trade is None:
            raise ValueError("quote 已执行但缺少成交记录，数据不一致")
        route = quote.selected_route or {}
        return {
            "quote_id": str(quote.id),
            "status": trade.status,
            "filled": trade.filled,
            "paper": trade.paper,
            "selected_route": {
                "venue": route.get("venue"),
                "price": route.get("price"),
                "total_cost_usd": route.get("total_cost_usd"),
            },
            "execution_stages": self._execution_stages(route.get("kind", "cex")),
            "executed_at": trade.executed_at.isoformat(),
            "idempotent_replay": True,
        }

    async def _mark_expired(self, qid: uuid.UUID) -> None:
        await self.session.execute(
            update(TradeQuotes)
            .where(TradeQuotes.id == qid, TradeQuotes.status == "pending")
            .values(status="expired")
        )
        await self.session.commit()

    async def cancel(self, quote_id: str) -> dict[str, Any]:
        quote = await self.session.get(TradeQuotes, uuid.UUID(quote_id))
        if quote is None:
            raise KeyError("quote 不存在")
        if quote.status != "pending":
            raise ValueError(f"quote 状态为 {quote.status}，不可取消")
        quote.status = "cancelled"
        await self.session.commit()
        return {"quote_id": str(quote.id), "status": quote.status}
