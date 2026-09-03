from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from w3ex.core.schemas import (
    ExecutionQuoteResult,
    ExecutionResult,
    ExecutionRoute,
)
from w3ex.providers.base import ExecutionProvider
from w3ex.providers.mock.generator import MockDataset


class MockExecutionProvider(ExecutionProvider):
    """模拟三类执行通道：CEX 现货、DEX Aggregator、Perpetual DEX。全部 paper fill。"""

    name = "mock"

    def __init__(self, dataset: MockDataset | None = None) -> None:
        self.ds = dataset or MockDataset()

    async def get_quote(
        self,
        side: str,
        asset: str,
        fiat_amount: Decimal,
        fiat_currency: str = "USD",
        market_type: str = "spot",
        constraints: dict[str, int] | None = None,
    ) -> ExecutionQuoteResult:
        symbol = asset.upper()
        mid = float(self.ds.price(symbol).price)
        amount = float(fiat_amount)
        routes: list[ExecutionRoute] = []

        # 1) CEX 现货：低滑点，手续费较高
        cex_price = mid * (1.0004 if side == "buy" else 0.9996)
        cex_fee = amount * 0.001
        routes.append(
            ExecutionRoute(
                venue="binance_cex",
                kind="cex",
                price=Decimal(str(round(cex_price, 8))),
                slippage_pct=0.05,
                fees_usd=Decimal(str(round(cex_fee, 2))),
                gas_usd=Decimal("0"),
                total_cost_usd=Decimal(str(round(amount + cex_fee, 2))),
                estimated_receive=Decimal(str(round(amount / cex_price, 8))),
                confidence=0.99,
                notes=["CEX 现货深度最优，滑点最小", "无链上 Gas 成本"],
            )
        )

        # 2) DEX Aggregator：中等滑点，需要 Gas
        dex_price = mid * (1.0012 if side == "buy" else 0.9988)
        dex_gas = 8.0 if symbol in ("SOL", "JUP") else 3.5
        dex_fee = amount * 0.0004
        routes.append(
            ExecutionRoute(
                venue="jupiter_dex",
                kind="dex",
                price=Decimal(str(round(dex_price, 8))),
                slippage_pct=0.35,
                fees_usd=Decimal(str(round(dex_fee, 2))),
                gas_usd=Decimal(str(round(dex_gas, 2))),
                total_cost_usd=Decimal(str(round(amount + dex_fee + dex_gas, 2))),
                estimated_receive=Decimal(str(round(amount / dex_price, 8))),
                confidence=0.94,
                notes=[f"DEX 聚合报价，预估滑点 0.35%，Gas ~${dex_gas:.2f}"],
            )
        )

        # 3) Perp：杠杆/做空能力，资金费率
        perp_price = mid * (1.0010 if side == "buy" else 0.9990)
        perp_fee = amount * 0.00035
        routes.append(
            ExecutionRoute(
                venue="hyperliquid_perp",
                kind="perp",
                price=Decimal(str(round(perp_price, 8))),
                slippage_pct=0.10,
                fees_usd=Decimal(str(round(perp_fee, 2))),
                gas_usd=Decimal("0"),
                total_cost_usd=Decimal(str(round(amount + perp_fee, 2))),
                estimated_receive=Decimal(str(round(amount / perp_price, 8))),
                confidence=0.96,
                notes=["永续合约通道，支持做空与杠杆", "注意资金费率", "非现货，存在强平风险"],
            )
        )

        # 评审 P0-1/P0-2：标注产品语义；只返回同类通道；买入按全成本、卖出按净到手
        for r in routes:
            r.instrument_type = "perp" if r.kind == "perp" else "spot"
            if side == "sell" and r.instrument_type == "spot":
                r.net_proceeds_usd = r.estimated_receive
                r.comparison_basis = "net_proceeds_usd"
        wanted = "perp" if market_type == "perp" else "spot"
        routes = [r for r in routes if r.instrument_type == wanted]
        if side == "buy":
            best = min(range(len(routes)), key=lambda i: float(routes[i].total_cost_usd))
            reason = (
                f"全成本最低：${float(routes[best].total_cost_usd):,.2f}（含价格/滑点/费用/Gas）"
            )
        else:
            best = max(range(len(routes)), key=lambda i: float(routes[i].net_proceeds_usd or 0))
            reason = f"净到手最多：${float(routes[best].net_proceeds_usd or 0):,.2f}"
        return ExecutionQuoteResult(
            side=side,
            asset_symbol=symbol,
            fiat_amount=fiat_amount,
            fiat_currency=fiat_currency,
            routes=routes,
            best_route_index=best,
            expires_in_seconds=60,
            ts=datetime.utcnow(),
            market_type=wanted,
            recommendation_reason=reason,
        )

    async def execute(self, quote: ExecutionQuoteResult, route_index: int) -> ExecutionResult:
        route = quote.routes[route_index]
        return ExecutionResult(
            quote_id="pending",
            status="executed",
            paper=True,
            filled=dict(
                side=quote.side,
                asset_symbol=quote.asset_symbol,
                venue=route.venue,
                price=str(route.price),
                receive=str(route.estimated_receive),
                fees_usd=str(route.fees_usd),
                total_cost_usd=str(route.total_cost_usd),
            ),
            executed_at=datetime.utcnow(),
        )
