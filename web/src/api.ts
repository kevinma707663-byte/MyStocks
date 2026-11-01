// Talks to the Python server (api/main.py). Every number on screen comes
// from core/ through here: nothing in the app is made up.

export type Portfolio = { holdings: Record<string, unknown>[]; trades: Record<string, unknown>[] }

export type Position = {
  ticker: string; name: string | null; currency: string; sector: string | null
  shares: number; avg_cost: number; cost: number; price: number | null; value: number | null
  gain: number | null; gain_pct: number | null; day_change: number | null; day_change_pct: number | null
  weight_pct: number | null; pe_ratio: number | null; dividend_yield_pct: number | null
}

export type Group = {
  stocks: number; value: number; cost: number; gain: number; gain_pct: number | null
  day_change: number; day_change_pct: number | null; realized_gain: number
  sp500_twin_gain_pct: number | null; beat_sp500_by_pct: number | null; left_out: string[]
}

export type Overview = {
  positions: Position[]
  summary: { groups: Record<string, Group>; combined: { currency: string; value: number; fx_rates: Record<string, number> } }
  notes: string[]
}

export type Chart = { dates: string[]; lines: Record<string, (number | null)[]> }

/** A Plotly chart from core/, as JSON: what fig.to_json() gives in Python. */
export type Figure = { data: unknown[]; layout: Record<string, unknown> }

/** A table whose columns vary (business years, growth rates): kept in order. */
export type Grid = { columns: string[]; rows: (string | number | null)[][] }

// The five tabs under a stock's verdict.
export type TechnicalsTab = { company: string; price: number; as_of: string; score: number; verdict: string; signals: Grid; charts: { chart?: Figure }; notes: string[] }
export type AnalystsTab = { company: string; verdict: string; score: number | null; target_currency_note: string; signals: Grid; charts: { targets?: Figure }; notes: string[] }
export type DcfTab = {
  company: string; method: string; currency: string; price: number; value_per_share: number; upside_pct: number
  verdict: string; notes: string[]; assumptions: Grid; sensitivity: Grid; charts: { bridge?: Figure }; notes_soft: string[]
}
export type RatiosTab = { ratios: Grid | null; notes: string[] }
export type RivalsTab = { company: string; rivals: string[]; scores: Grid; charts: { scores?: Figure }; notes: string[] }
export type StockTab = 'technicals' | 'analysts' | 'dcf' | 'ratios' | 'rivals'

export type Level = 'low' | 'medium' | 'high' | 'n/a'

export type Risks = {
  score: number; level: Level; top_risks: string[]; left_out: string[]; value: number; home_currency: string
  period: { start: string; end: string; years: number }
  areas: { area: string; level: Level; reading: string }[]
  beta: number
  stress: { market_fall_pct: number; expected_fall_pct: number; expected_loss: number }
  bad_day: { loss_pct: number; loss: number; average_bad_day_pct: number; average_bad_day_loss: number }
  risk_shares: { ticker: string; 'money %': number; 'risk %': number }[]
  underwater: Chart
  correlation: { tickers: string[]; values: (number | null)[][] }
  charts: { sectors?: Figure; correlation?: Figure; risk_share?: Figure; drawdown?: Figure }
  notes: string[]
}

export type MixRow = {
  mix: string; 'yearly return %': number; 'yearly swings %': number; 'Sharpe ratio': number | null
  'worst drop %': number; '$10,000 became': number
}

export type Optimized = {
  result_id: string; status: 'ok' | 'no mix found'; message: string; tickers: string[]; goal: string
  rules: Record<string, string>; period: { start: string; end: string; years: number }
  best_weights: Record<string, number>; current_weights: Record<string, number>
  edit_weights: Record<string, number> | null; breaks: string[]
  limits: { max_drawdown_pct: number; min_return_pct: number; max_weight_pct: number; min_weight_pct: number }
  comparison: MixRow[]; growth: Chart; notes: string[]
  charts: { weights?: Figure; growth?: Figure; cloud?: Figure }
}

export type Verdict = {
  company: string; name: string | null; score: number | null; verdict: string
  momentum: { price_pct: number | null; analyst_pct: number | null; combined_pct: number | null; reading: string }
  strengths: string[]; concerns: string[]
  parts: { part: string; score: number | null; weight_pct: number; summary: string; skipped_because: string }[]
  health_checks: { check: string; result: 'pass' | 'fail' | 'skip'; detail: string }[]
  notes: string[]
}

export type Warning = { trap: string; level: 'caution' | 'heads-up'; message: string; tip: string }

export type CoachTip = {
  status: 'ok' | 'off' | 'unavailable'; note: string | null; why: string; disclaimer: string
  biases: { bias: string; quote: string; meaning: string }[]
}

export type Trade = { action: 'buy' | 'sell'; ticker: string; shares: number; price: number }

/** A problem the server explained in plain English (core/'s own message). */
export class ApiError extends Error {
  technical?: string
  constructor(message: string, technical?: string) {
    super(message)
    this.technical = technical
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, init)
  } catch {
    throw new ApiError("Can't reach the MyPortfolio server. Is it running? (see web/README.md)")
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(body?.detail ?? `The server answered ${response.status}.`, body?.technical)
  }
  return body as T
}

function post<T>(path: string, body: unknown): Promise<T> {
  return call<T>(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
}

export const api = {
  sample: () => call<{ portfolio: Portfolio; problems: string[] }>('/portfolio/sample'),
  importFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return call<{ portfolio: Portfolio; problems: string[] }>('/portfolio/import', { method: 'POST', body: form })
  },
  add: (portfolio: Portfolio, holding: { ticker: string; shares: number; price: number; market: string; buy_date?: string }) =>
    post<{ portfolio: Portfolio }>('/portfolio/add', { portfolio, ...holding }),
  overview: (portfolio: Portfolio) => post<Overview>('/overview', { portfolio }),
  history: (portfolio: Portfolio, currency: string) => post<Chart & { currency: string }>('/history', { portfolio, currency }),
  risks: (portfolio: Portfolio) => post<Risks>('/risks', { portfolio }),
  optimize: (portfolio: Portfolio, rules: Record<string, unknown>) => post<Optimized>('/optimize', { portfolio, ...rules }),
  edit: (resultId: string, changes: Record<string, number>) => post<Optimized>('/edit', { result_id: resultId, changes }),
  verdict: (ticker: string, rivals: boolean) =>
    call<Verdict>(`/verdict/${encodeURIComponent(ticker)}?rivals=${rivals}`),
  stockTab: <T>(ticker: string, tab: StockTab) => call<T>(`/stock/${encodeURIComponent(ticker)}/${tab}`),
  standing: (portfolio: Portfolio, datesKnown: boolean) =>
    post<{ warnings: Warning[] }>('/warnings/standing', { portfolio, dates_known: datesKnown }),
  checkTrade: (portfolio: Portfolio, trade: Trade, reason: string, datesKnown: boolean) =>
    post<{ warnings: Warning[]; tip: CoachTip | null }>('/trade/check', { portfolio, ...trade, reason, dates_known: datesKnown }),
  recordTrade: (portfolio: Portfolio, trade: Trade) => post<{ portfolio: Portfolio }>('/trade/record', { portfolio, ...trade }),
}
