import { getOrCreateUserKey } from "./user";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export const API_ROOT = API_BASE.replace(/\/api\/v1$/, "");

export class ApiError extends Error {
  code: string;
  status: number;
  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export interface ApiOptions extends RequestInit {
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT = 15000;
/** LLM 生成 10-120s（推理模型更长），行情 15s。 */
const LLM_TIMEOUT = 120000;

/** 评审 P0 数据可信度：最近一次响应的 provenance（来自 X-Data-Source / X-Data-Quality 头）。 */
export interface DataMeta {
  source: string;
  quality: string;
}
let lastDataMeta: DataMeta = { source: "", quality: "" };
export function getLastDataMeta(): DataMeta {
  return lastDataMeta;
}

export async function api<T>(path: string, options?: ApiOptions): Promise<T> {
  const { timeoutMs = DEFAULT_TIMEOUT, headers: extraHeaders, ...init } = options ?? {};
  // 需求⑥：模拟交易账户按浏览器用户隔离（后端 X-User-Key）
  const userKey =
    typeof window !== "undefined" ? getOrCreateUserKey() : "default";
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}${path}`, {
      ...init,
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "X-User-Key": userKey,
        ...(extraHeaders ?? {}),
      },
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (typeof window !== "undefined") {
      lastDataMeta = {
        source: resp.headers.get("x-data-source") ?? "",
        quality: resp.headers.get("x-data-quality") ?? "",
      };
    }
  } catch (e) {
    if (e instanceof DOMException && (e.name === "TimeoutError" || e.name === "AbortError")) {
      throw new ApiError(
        0,
        "timeout",
        timeoutMs > 60000
          ? "模型响应超时（120s），推理模型生成较慢，请重试或更换模型"
          : "请求超时（15s），行情数据源响应缓慢，请点击重试",
      );
    }
    throw new ApiError(0, "network_error", "无法连接后端 API（请确认 uvicorn 已启动）");
  }
  if (!resp.ok) {
    let code = "error";
    let message = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: { code?: string; message?: string } };
      if (body.detail) {
        code = body.detail.code ?? code;
        message = body.detail.message ?? message;
      }
    } catch {
      /* keep defaults */
    }
    throw new ApiError(resp.status, code, message);
  }
  return (await resp.json()) as T;
}

// ---------- Shared ----------

export interface Ticker {
  symbol: string;
  price: number | null;
  change_24h_pct: number;
  volume_24h_usd: number | string | null;
  high_24h: number | string | null;
  low_24h: number | string | null;
}

export interface Candle {
  ts: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface Regime {
  regime: "risk_on" | "risk_off" | "neutral";
  score: number;
  label: string;
  drivers: string[];
  btc_change_24h_pct: number;
  eth_change_24h_pct: number;
  sol_change_24h_pct: number;
}

export interface FundingEntry {
  symbol: string;
  rate: number;
  mark_price: string;
  ts: string;
}

export interface LiquidationEvent {
  symbol: string;
  side: string;
  amount_usd: string;
  price: string;
  ts: string;
}

export interface GlobalStats {
  total_market_cap_usd: number;
  total_volume_24h_usd: number;
  btc_dominance_pct: number;
  eth_dominance_pct: number;
  mcap_change_24h_pct: number;
  active_cryptocurrencies: number;
  source: string;
  ts: string;
}

// ---------- Market Overview ----------

export interface MarketOverview {
  as_of: string;
  global_stats: GlobalStats | null;
  regime: Regime;
  indices: Record<string, number>;
  gainers: Ticker[];
  losers: Ticker[];
  volume_leaders: Ticker[];
  funding: FundingEntry[];
  liquidations: LiquidationEvent[];
  sources: { market: string; liquidations: string };
}

// ---------- Asset Detail ----------

export interface DepthSnapshot {
  bids: [number, number][];
  asks: [number, number][];
  ts: string;
  source: string;
}

export interface AssetDetail {
  symbol: string;
  name: string;
  price: number | null;
  change_24h_pct: number;
  change_1h_pct: number | null;
  interval: string;
  candles: Candle[];
  stats: {
    market_cap: number | string | null;
    market_cap_rank: number | null;
    volume_24h_usd: number | string | null;
    circulating_supply: number | string | null;
    high_24h: number | string | null;
    low_24h: number | string | null;
  };
  funding_rate: number | null;
  depth: DepthSnapshot | null;
  sources: { market: string; meta: string };
}

// ---------- Trade ----------

export interface Route {
  venue: string;
  kind: "cex" | "dex" | "perp";
  price: string;
  slippage_pct: number;
  fees_usd: string;
  gas_usd: string;
  total_cost_usd: string;
  estimated_receive: string;
  confidence: number;
  notes: string[];
  instrument_type: "spot" | "perp";
  net_proceeds_usd: string | null;
  comparison_basis: string;
  data_age_ms: number;
  worst_receive: string | null;
  funding_rate: number | null;
  margin_required_usd: string | null;
  liquidation_distance_pct: number | null;
}

export interface FilteredRoute {
  route: Route;
  reason: string;
}

export interface Quote {
  quote_id: string | null;
  side: string;
  asset: string;
  fiat_amount: string;
  fiat_currency: string;
  market_type: string;
  routes: Route[];
  best_route_index: number;
  recommendation_reason: string;
  constraints: { max_slippage_bps: number; max_data_age_ms: number } | null;
  filtered_routes: FilteredRoute[];
  expires_at: string | null;
  status: string;
}

export interface ExecStage {
  stage: string;
  label: string;
  status: string;
  ts: string;
  simulated: boolean;
}

export interface ExecResult {
  quote_id: string;
  status: string;
  filled: Record<string, unknown>;
  paper: boolean;
  leverage?: number;
  selected_route: { venue: string | null; price: string | null; total_cost_usd: string | null };
  execution_stages: ExecStage[];
  executed_at: string;
  idempotent_replay?: boolean;
}

export interface ReplayResult {
  quote_id: string;
  side: string;
  asset: string;
  fiat_amount: string;
  fiat_currency: string;
  status: string;
  created_at: string;
  executed_at: string | null;
  snapshot_routes: Route[];
  selected_venue: string | null;
  selected_route: Route | Record<string, never>;
  recommendation_reason: string;
  actual: { status: string; filled: Record<string, unknown>; paper: boolean; executed_at: string } | null;
  counterfactual: {
    venue: string;
    route_index: number;
    estimated_receive: string;
    total_cost_usd: string;
    diff_pct: number;
    would_be_better: boolean;
  }[];
}

// ---------- Fetchers ----------

export const getOverview = () => api<MarketOverview>("/market/overview");
export const getTickers = (assets?: string) =>
  api<Ticker[]>(`/market/tickers${assets ? `?assets=${assets}` : ""}`);
export const getAsset = (symbol: string, interval?: string) =>
  api<AssetDetail>(`/assets/${symbol}${interval ? `?interval=${interval}` : ""}`);
export interface QuoteParams {
  side: string;
  asset: string;
  amount: string;
  market_type?: string;
  max_slippage_bps?: number;
  max_data_age_ms?: number;
  leverage?: number;
}

export const getQuote = (p: QuoteParams) => {
  const q = new URLSearchParams({
    side: p.side,
    asset: p.asset,
    amount: p.amount,
    market_type: p.market_type ?? "spot",
    max_slippage_bps: String(p.max_slippage_bps ?? 0),
    max_data_age_ms: String(p.max_data_age_ms ?? 0),
    leverage: String(p.leverage ?? 1),
  });
  return api<Quote>(`/trade/quote?${q}`);
};
export const postConfirm = (quote_id: string, route_index: number, idemKey?: string) =>
  api<ExecResult>("/trade/confirm", {
    method: "POST",
    body: JSON.stringify({ quote_id, route_index }),
    headers: idemKey ? { "Idempotency-Key": idemKey } : undefined,
  });
export const postCancel = (quote_id: string) =>
  api<{ quote_id: string; status: string }>("/trade/cancel", {
    method: "POST",
    body: JSON.stringify({ quote_id }),
  });
export const getReplay = (quote_id: string) => api<ReplayResult>(`/trade/replay/${quote_id}`);
export const getWatchlist = () => api<string[]>("/watchlist");
export const putWatchlist = (symbols: string[]) =>
  api<string[]>("/watchlist", { method: "PUT", body: JSON.stringify({ symbols }) });

// ---------- Paper Orders ----------

export interface PaperOrder {
  order_id: string;
  side: "buy" | "sell";
  asset: string;
  market_type: "spot" | "perp";
  order_type: "market" | "limit" | "tp" | "sl";
  quantity: string;
  limit_price: string | null;
  tp_price: string | null;
  sl_price: string | null;
  leverage: number;
  linked_position_id: string | null;
  reduce_only: boolean;
  status: "pending" | "filled" | "cancelled";
  entry_price: string | null;
  fill_price: string | null;
  filled_at: string | null;
  fee_rate: string;
  paper: boolean;
  ts: string;
  current_price?: string;
  unrealized_pnl_usd?: string;
}

export const createOrder = (body: {
  side: string;
  asset: string;
  order_type: string;
  amount_usd: string;
  market_type: string;
  limit_price?: string | null;
  leverage?: number;
  linked_position_id?: string | null;
}) => api<PaperOrder>("/trade/order", { method: "POST", body: JSON.stringify(body) });
export const listOrders = (status = "all") => api<PaperOrder[]>(`/trade/orders?status=${status}`);
export const cancelOrder = (orderId: string) =>
  api<PaperOrder>(`/trade/orders/${orderId}`, { method: "DELETE" });

// ---------- Paper Positions（评审 P0-3） ----------

export interface PaperPosition {
  position_id: string;
  venue: string;
  asset: string;
  side: "long" | "short";
  quantity: string;
  entry_price: string;
  leverage: number;
  margin_usd: string;
  notional_usd: string;
  status: "open" | "closed";
  realized_pnl: string;
  closed_price: string | null;
  closed_at: string | null;
  ts: string;
  paper: boolean;
  current_price?: string;
  unrealized_pnl_usd?: string;
  liquidation_estimate?: string;
  liquidation_estimated?: boolean;
}

export const listPositions = (status = "open") =>
  api<PaperPosition[]>(`/trade/positions?status=${status}`);

// ---------- Paper Account（需求⑥ 模拟账户） ----------

export interface AccountSummary {
  user_key: string;
  initial_balance_usd: string;
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  equity_usd: string;
  total_pnl_usd: string;
  margin_used_usd: string;
  available_usd: string;
  open_positions: number;
  orders_count: number;
  reset_count: number;
  paper: boolean;
  ts: string;
}

export const getAccount = () => api<AccountSummary>("/trade/account");

export const resetAccount = () =>
  api<{ user_key: string; reset_count: number; history_retained: boolean }>(
    "/trade/account/reset",
    { method: "POST" },
  );

// ---------- Macro（股指 / 大宗商品 / 世界银行宏观） ----------

export interface GroupQuote {
  symbol: string;
  yahoo_symbol: string;
  name: string;
  price: number;
  change_pct: number;
  ts: string;
}

export interface MacroMetric {
  value: number;
  year: number;
}

export interface MacroCountry {
  iso3: string;
  name: string;
  metrics: Record<string, MacroMetric | null>;
}

export interface MacroOverview {
  indices: GroupQuote[];
  commodities: GroupQuote[];
  macro: { countries: MacroCountry[]; source: string; note: string } | null;
  sources: { indices: string; commodities: string; macro: string };
  ts: string;
}

export const getMacro = () => api<MacroOverview>("/macro/overview");

export interface MacroHistory {
  symbol: string;
  yahoo_symbol: string;
  range: string;
  interval: string;
  candles: Candle[];
}

// 后端查询参数名是 rng（不是 range——写错会静默走默认 5y）
export const getMacroHistory = (symbol: string, range: string, interval: string) =>
  api<MacroHistory>(
    `/macro/history/${symbol}?rng=${encodeURIComponent(range)}&interval=${interval}`,
  );

export interface MacroIndicatorSeries {
  iso3: string;
  name: string;
  indicator: string;
  indicator_name: string;
  series: { year: number; value: number }[];
  source: string;
}

export const getMacroIndicator = (iso3: string, indicator: string) =>
  api<MacroIndicatorSeries>(`/macro/indicator/${iso3}/${indicator}`);

// ---------- AI（模型绑定 / Regime 简报 / 标的对话） ----------

export interface AiStatus {
  bound: boolean;
  provider?: string;
  label?: string;
  base_url?: string;
  api_key_masked?: string;
  model?: string | null;
  status?: string;
  last_checked_at?: string | null;
}

export interface AiBindResult {
  bound: boolean;
  provider: string;
  model: string | null;
  models: string[];
  status: string;
  api_key_masked: string;
}

export const getAiStatus = () => api<AiStatus>("/ai/status");

export const bindAi = (body: {
  provider: string;
  base_url: string;
  api_key: string;
  model?: string | null;
  label?: string;
}) =>
  api<AiBindResult>("/ai/bind", {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: LLM_TIMEOUT,
  });

export const unbindAi = () => api<{ bound: boolean }>("/ai/bind", { method: "DELETE" });

export const getAiModels = () =>
  api<{ provider: string; models: string[] }>("/ai/models", { timeoutMs: LLM_TIMEOUT });

export interface AiBrief {
  source: "rule" | "llm";
  model: string | null;
  summary: string[];
  detail: string;
  uncertainty: string;
  disclaimer: string;
  error?: string | null;
}

export const postRegimeBrief = () =>
  api<AiBrief>("/ai/regime-brief", { method: "POST", timeoutMs: LLM_TIMEOUT });

export interface AiChatReply {
  source: "rule" | "llm";
  model: string | null;
  reply: string;
  disclaimer: string;
  error?: string | null;
}

export const postAssetChat = (
  symbol: string,
  body: { message: string; interval: string; range?: string; history: { role: string; content: string }[] },
) =>
  api<AiChatReply>(`/ai/asset-chat/${symbol}`, {
    method: "POST",
    body: JSON.stringify(body),
    timeoutMs: LLM_TIMEOUT,
  });

export interface ChatStreamEvent {
  type: "step" | "delta" | "done" | "error";
  stage?: string;
  message?: string;
  text?: string;
  source?: "rule" | "llm";
  model?: string | null;
}

/** AI 流式对话：fetch reader 解析 SSE（data: 行），事件逐块回调。 */
export async function postAssetChatStream(
  symbol: string,
  body: { message: string; interval: string; range?: string; history: { role: string; content: string }[] },
  onEvent: (ev: ChatStreamEvent) => void,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/ai/asset-chat/${symbol}/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(LLM_TIMEOUT),
  });
  if (!resp.ok || !resp.body) {
    let message = `HTTP ${resp.status}`;
    try {
      const j = (await resp.json()) as { detail?: { message?: string } };
      message = j.detail?.message ?? message;
    } catch {
      /* keep default */
    }
    throw new ApiError(resp.status, "stream_failed", message);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const s = line.trim();
      if (!s.startsWith("data:")) continue;
      try {
        onEvent(JSON.parse(s.slice(5).trim()) as ChatStreamEvent);
      } catch {
        /* 忽略无法解析的行 */
      }
    }
  }
}

// ---------- AI Agents（PDF 6.2 四类教练） ----------
export interface AgentMeta {
  kind: string;
  name: string;
  name_en: string;
  style: string;
}

export interface AgentToolStep {
  tool: string;
  args: Record<string, unknown>;
  ok: boolean;
  summary: string;
}

export interface AgentReply {
  kind: string;
  agent_name?: string;
  reply: string;
  context?: string;
  source: string;
  disclaimer?: string;
  tool_trace?: AgentToolStep[];
  ts?: string;
}

export async function getAgents(): Promise<AgentMeta[]> {
  // 后端返回 {agents: [...]} 包装结构
  const data = await api<{ agents: AgentMeta[] }>("/agent");
  return data.agents;
}

export async function postAgentChat(
  kind: string,
  body: { message: string; history?: { role: string; content: string }[]; lang?: string }
): Promise<AgentReply> {
  return api<AgentReply>(`/agent/${kind}`, { method: "POST", body: JSON.stringify(body), timeoutMs: LLM_TIMEOUT });
}
