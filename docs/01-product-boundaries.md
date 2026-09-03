# 01 · Product Boundaries

## 定位

**w3ex** 不是托管型交易所，而是纯行情 + 交易终端：

> Binance/CoinGecko 行情聚合 + 多通道路由报价 + Paper 执行

核心循环：**Observe Markets → Compare Routes → Decide → Execute (Paper)**

## MVP 范围内 (IN)

| 模块 | 说明 |
|---|---|
| Market Overview | 市场体制(Risk-On/Off)、三大币(BTC/ETH/SOL)、全局统计(市值/BTC占比)、涨跌榜/量能榜、资金费率、清算 |
| All Tickers | 全量行情表（过滤 + 排序） |
| Asset Detail | 单资产页：价格 / K线(5m-1d) / 统计(市值/排名/流通量) / 订单簿深度 / Funding / Trade CTA |
| Trading Execution | 意图 → 路由(Binance CEX / Jupiter DEX / Hyperliquid Perp) → 报价对比(价格/滑点/费用) → 用户确认 → paper 执行 |
| Watchlist | 自选资产跟踪 |
| Provider 抽象 | 数据源与业务逻辑完全解耦，mock 自动回退，响应携带 `sources` |

## MVP 范围外 (OUT) — 明确不实现

- 托管型钱包基础设施 / 私钥托管
- 内部撮合引擎 (matching engine)
- 用户资金托管 / 清算基础设施 / 专有交易所账本
- **研究类模块**：AI Research Agent、叙事检测、钱包画像、链上信号、新闻聚合（已从 MVP 移除，相关表保留在 schema 中但不在 API 层暴露）
- 全链多链覆盖
- 不透明 ML 评分

## 执行边界（安全）

- **系统永不自主交易**。所有执行需用户显式确认（`POST /trade/confirm`）。
- MVP 执行层为 **paper/simulated fill**（`paper: true`），不移动真实资金。
- 报价对比透明展示：价格 / 滑点 / 费用 / 总成本，用户自选路由。

## 资产范围

- BTC, ETH, SOL 及 Binance USDT 交易对全量（数百万流动性长尾自动覆盖）
- 稳定币报价经 CoinGecko / mock 回退链处理

## 设计原则

1. **真实数据优先**：默认 `rich` provider（Binance 镜像 + CoinGecko），网络不可达自动降级 mock 并标注。
2. **Provider 解耦**：核心业务逻辑不依赖任何单一 Provider。
3. **数据诚实**：每个响应带 `sources`，模拟数据明确标注。
4. **执行需确认**：报价 → 对比 → 确认 → 执行，无隐藏步骤。
