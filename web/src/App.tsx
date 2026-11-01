import { useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from 'react'
import {
  api, ApiError,
  type Chart, type CoachTip, type Group, type Level, type Optimized, type Overview, type Portfolio,
  type Position, type Risks, type Trade, type Verdict, type Warning,
  type AnalystsTab, type DcfTab, type Grid, type RatiosTab, type RivalsTab, type StockTab, type TechnicalsTab,
} from './api'
import { AREA_HELP, DISCLAIMER, GLOSSARY, PAGES, RULE_HELP, STOCK_TABS, TRADE_HELP } from './content'
import { ChartGroup } from './Chart'

type IconName =
  | 'grid'
  | 'chart'
  | 'spark'
  | 'shield'
  | 'bell'
  | 'search'
  | 'plus'
  | 'chevron'
  | 'arrowUp'
  | 'more'
  | 'briefcase'
  | 'close'

const paths: Record<IconName, ReactNode> = {
  grid: <><rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/></>,
  chart: <><path d="M4 19V9"/><path d="M10 19V5"/><path d="M16 19v-7"/><path d="M22 19H2"/></>,
  spark: <><path d="m3 17 5-5 4 4 8-10"/><path d="M14 6h6v6"/></>,
  shield: <><path d="M12 22s8-3.5 8-10V5l-8-3-8 3v7c0 6.5 8 10 8 10Z"/><path d="m9 12 2 2 4-4"/></>,
  bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M10 21h4"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
  plus: <><path d="M12 5v14M5 12h14"/></>,
  chevron: <path d="m9 18 6-6-6-6"/>,
  arrowUp: <><path d="m18 15-6-6-6 6"/></>,
  more: <><circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/></>,
  briefcase: <><rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18"/></>,
  close: <><path d="m6 6 12 12M18 6 6 18"/></>,
}

function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {paths[name]}
    </svg>
  )
}

// ===========================================================================
// SETTINGS AND SMALL HELPERS
// ===========================================================================

const workflow = [
  { label: 'Set Up', module: 'Set Up Portfolio', icon: 'briefcase', ask: 'Build your portfolio' },
  { label: 'MyStocks', module: 'MyStocks', icon: 'grid', ask: 'Where am I now?' },
  { label: 'MyAnalysis', module: 'MyAnalysis', icon: 'chart', ask: 'Are these good investments?' },
  { label: 'MyRisks', module: 'MyRisks', icon: 'shield', ask: 'What could go wrong?' },
  { label: 'MyOptimizer', module: 'MyOptimizer', icon: 'spark', ask: 'Is there a better allocation?' },
  { label: 'MyEdit', module: 'MyEdit', icon: 'chart', ask: 'What if I change it?' },
  { label: 'Decision', module: 'Decision / Action', icon: 'chevron', ask: 'Choose what to do' },
  { label: 'Warnings', module: 'Warning Check', icon: 'bell', ask: 'Check before updating' },
] as const

const NAV: [string, IconName][] = [
  ['Dashboard', 'grid'], ['MyStocks', 'briefcase'], ['MyAnalysis', 'chart'], ['MyRisks', 'shield'],
  ['MyOptimizer', 'spark'], ['MyEdit', 'chart'], ['Decision / Action', 'chevron'], ['Warning Check', 'bell'],
]

const SLICE_COLOURS = ['#2778e6', '#76b900', '#e31837', '#f7b500', '#174c8f', '#8b5cf6', '#c7a33b']
const LEVEL_COLOUR: Record<string, string> = { low: '#17875d', medium: '#e6a432', high: '#cf5255', 'n/a': '#9aa4b3' }
const VERDICT_COLOUR: Record<string, string> = {
  'looks strong': '#17875d', hold: '#2475df', 'look closer': '#e6a432', 'consider trimming': '#cf5255', 'not enough data': '#9aa4b3',
}
const VERDICT_PLAIN: Record<string, string> = {
  'looks strong': 'Most checks look good.',
  hold: 'Mixed signals. Nothing urgent.',
  'look closer': 'Some warning signs. Worth a closer look.',
  'consider trimming': 'Several warning signs. Worth asking if you still want this much of it.',
  'not enough data': 'Not enough data to score this one.',
}
const PART_TAG: Record<string, string> = {
  'Business health': '3A', 'Versus rivals': '3B', Economy: '3C', 'Price chart': '3D', Analysts: '3E', Value: '3F',
}
const GOALS: [string, string][] = [['sharpe', 'Highest Sharpe Ratio'], ['low_risk', 'Lowest Risk'], ['high_return', 'Highest Return']]

const STORAGE_KEY = 'mystocks.portfolio.v1'

// The visitor's portfolio lives in their own browser, never on the server.
type Saved = { portfolio: Portfolio; datesKnown: boolean }

function loadSaved(): Saved | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const saved = raw ? JSON.parse(raw) as Saved : null
    return saved?.portfolio?.holdings?.length ? saved : null
  } catch {
    return null
  }
}

function storeSaved(saved: Saved | null) {
  try {
    if (saved) localStorage.setItem(STORAGE_KEY, JSON.stringify(saved))
    else localStorage.removeItem(STORAGE_KEY)
  } catch { /* private window: the portfolio just won't be remembered */ }
}

function digits(x: number) { return Math.abs(x) >= 1000 ? 0 : 2 }
function num(x: number | null | undefined, d = 2) {
  return x == null ? 'n/a' : x.toLocaleString('en-CA', { minimumFractionDigits: d, maximumFractionDigits: d })
}
function money(x: number | null | undefined, currency = '') {
  return x == null ? 'n/a' : `$${num(x, digits(x))}${currency ? ` ${currency}` : ''}`
}
function signedMoney(x: number | null | undefined, currency = '') {
  return x == null ? 'n/a' : `${x >= 0 ? '+' : '-'}$${num(Math.abs(x), digits(x))}${currency ? ` ${currency}` : ''}`
}
function signedPct(x: number | null | undefined, d = 1) {
  return x == null ? 'n/a' : `${x >= 0 ? '+' : ''}${x.toFixed(d)}%`
}
function short(x: number) {
  const a = Math.abs(x)
  return a >= 1e6 ? `${(x / 1e6).toFixed(1)}M` : a >= 1e3 ? `${(x / 1e3).toFixed(1)}K` : x.toFixed(0)
}
function upDown(x: number | null | undefined) { return (x ?? 0) >= 0 ? 'positive-cell' : 'negative-cell' }
function ring(score: number | null | undefined, colour: string) {
  const s = Math.max(0, Math.min(100, score ?? 0))
  return { background: `conic-gradient(${colour} 0 ${s}%, #e5eaf1 ${s}%)` }
}

/** Load something from the server whenever `key` changes. */
function useLoad<T>(load: () => Promise<T>, key: string, enabled = true) {
  const [state, setState] = useState<{ data?: T; error?: ApiError; loading: boolean }>({ loading: enabled })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    if (!enabled) { setState({ loading: false }); return }
    let live = true
    setState({ loading: true })
    load().then(
      (data) => live && setState({ data, loading: false }),
      (error) => live && setState({ error: error instanceof ApiError ? error : new ApiError(String(error)), loading: false }),
    )
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt, enabled])
  return { ...state, retry: () => setAttempt((n) => n + 1) }
}

function Loading({ text }: { text: string }) {
  return <div className="state-box"><span className="spinner" />{text}</div>
}

function Problem({ error, onRetry }: { error: ApiError; onRetry?: () => void }) {
  return (
    <div className="state-box problem">
      <strong>{error.message}</strong>
      {error.technical && <details><summary>Technical details</summary><code>{error.technical}</code></details>}
      {onRetry && <button onClick={onRetry}>Try again</button>}
    </div>
  )
}

/** Text with **double stars** around the words to make bold (the style content.ts is written in). */
function Rich({ text }: { text: string }) {
  return <>{text.split('**').map((part, i) => i % 2 ? <b key={i}>{part}</b> : part)}</>
}

/** A page's one-line "what this means" tip. */
function Tip({ page }: { page: string }) {
  const tip = PAGES[page]?.tip
  return tip ? <div className="tip-banner"><span aria-hidden="true">💡</span><p><Rich text={tip} /></p></div> : null
}

/** The bottom of every page: the words it uses, explained, and the disclaimer. */
function PageEnd({ page }: { page: string }) {
  const terms = PAGES[page]?.terms ?? []
  return <>
    {terms.length > 0 && (
      <details className="glossary">
        <summary>📖 Words explained</summary>
        <dl>{terms.map((term) => <div key={term}><dt>{term}</dt><dd>{GLOSSARY[term]}</dd></div>)}</dl>
      </details>
    )}
    <p className="page-disclaimer">{DISCLAIMER}</p>
  </>
}

function Notes({ notes }: { notes?: string[] }) {
  if (!notes?.length) return null
  return <div className="notice-list">{notes.map((n) => <p key={n}>⚠️ {n}</p>)}</div>
}

// ===========================================================================
// THE APP
// ===========================================================================

function App() {
  const [saved, setSaved] = useState<Saved | null>(loadSaved)
  const [settingUp, setSettingUp] = useState(false)

  function update(next: Saved | null) {
    storeSaved(next)
    setSaved(next)
  }

  if (!saved || settingUp) {
    return <PortfolioSetup
      onCancel={saved ? () => setSettingUp(false) : undefined}
      onComplete={(portfolio, datesKnown) => { update({ portfolio, datesKnown }); setSettingUp(false) }}
    />
  }
  return <Workspace saved={saved} onChange={update} onSetUp={() => setSettingUp(true)} />
}

function Workspace({ saved, onChange, onSetUp }: { saved: Saved; onChange: (next: Saved | null) => void; onSetUp: () => void }) {
  const { portfolio, datesKnown } = saved
  const key = useMemo(() => JSON.stringify(portfolio), [portfolio])

  const [activeNav, setActiveNav] = useState('Dashboard')
  const [isModalOpen, setModalOpen] = useState(false)
  const [notice, setNotice] = useState('')

  // Loaded once per portfolio, and shared by every page.
  const overview = useLoad(() => api.overview(portfolio), key)
  const risks = useLoad(() => api.risks(portfolio), key)
  const standing = useLoad(() => api.standing(portfolio, datesKnown), `${key}|${datesKnown}`)

  // Kept while moving between pages. A new portfolio starts them over.
  const [optimized, setOptimized] = useState<Optimized | null>(null)
  const [edited, setEdited] = useState<Optimized | null>(null)
  const [edits, setEdits] = useState<Record<string, number>>({})
  const [decision, setDecision] = useState<'current' | 'best' | 'edit'>('current')
  const [verdicts, setVerdicts] = useState<Record<string, Verdict>>({})
  const [stockTabs, setStockTabs] = useState<Record<string, unknown>>({})
  useEffect(() => { setOptimized(null); setEdited(null); setEdits({}); setDecision('current') }, [key])

  function say(text: string) {
    setNotice(text)
    window.setTimeout(() => setNotice(''), 3500)
  }

  function changePortfolio(next: Portfolio, nextDatesKnown = datesKnown) {
    onChange({ portfolio: next, datesKnown: nextDatesKnown })
  }

  const tickers = overview.data?.positions.map((p) => p.ticker) ?? []
  const warningCount = standing.data?.warnings.length ?? 0

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Icon name="spark" size={19} /></div>
          <span>MyPortfolio</span>
        </div>
        <nav className="main-nav" aria-label="Main navigation">
          {NAV.map(([label, icon]) => (
            <button className={`nav-item ${activeNav === label ? 'active' : ''}`} onClick={() => setActiveNav(label)} key={label}>
              <Icon name={icon} />
              <span>{label}</span>
              {label === 'Warning Check' && warningCount > 0 && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="disclaimer"><Icon name="shield" size={16} /><span>Rules of thumb based on past data.<br />Not financial advice.</span></div>
          <button className="profile" onClick={() => {
            if (window.confirm('Start over? This forgets the portfolio saved in this browser.')) onChange(null)
          }}>
            <span className="avatar"><Icon name="briefcase" size={15} /></span>
            <span className="profile-copy"><strong>{tickers.length || portfolio.holdings.length} holdings</strong><small>Saved in this browser · start over</small></span>
            <Icon name="more" size={17} />
          </button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">MY PORTFOLIO</p>
            <h1>{activeNav}</h1>
          </div>
          <div className="header-actions">
            <button className="icon-button" aria-label="Warnings" onClick={() => setActiveNav('Warning Check')}><Icon name="bell" />{warningCount > 0 && <span className="notification-dot" />}</button>
            <button className="primary-button" onClick={() => setModalOpen(true)}><Icon name="plus" size={17} /> Add holding</button>
          </div>
        </header>

        {notice && <div className="toast">{notice}</div>}
        {activeNav === 'Dashboard' ? (
          <Dashboard
            portfolio={portfolio} datesKnown={datesKnown} portfolioKey={key}
            overview={overview} risks={risks} onNavigate={setActiveNav} onSetUp={onSetUp}
          />
        ) : (
          <ModulePage module={activeNav} onBack={() => setActiveNav('Dashboard')} onNext={setActiveNav}>
            {activeNav === 'MyStocks' ? <MyStocksPage overview={overview} datesKnown={datesKnown} />
              : activeNav === 'MyAnalysis' ? <AnalysisPage tickers={tickers} verdicts={verdicts} onVerdict={(k, v) => setVerdicts((all) => ({ ...all, [k]: v }))}
                  tabCache={stockTabs} onTabCache={(k, v) => setStockTabs((all) => ({ ...all, [k]: v }))} />
              : activeNav === 'MyRisks' ? <RiskPage risks={risks} />
              : activeNav === 'MyOptimizer' ? <OptimizerPage portfolio={portfolio} result={optimized} onResult={(r) => { setOptimized(r); setEdited(null); setEdits({}) }} onEdit={() => setActiveNav('MyEdit')} />
              : activeNav === 'MyEdit' ? <EditPage optimized={optimized} edited={edited} edits={edits} onEdited={(r, e) => { setEdited(r); setEdits(e) }} onOptimize={() => setActiveNav('MyOptimizer')} />
              : activeNav === 'Decision / Action' ? <DecisionPanel optimized={optimized} edited={edited} choice={decision} onChoice={setDecision} onContinue={() => setActiveNav('Warning Check')} />
              : <WarningCheck
                  portfolio={portfolio} datesKnown={datesKnown} standing={standing}
                  onRecorded={(next, text) => { changePortfolio(next); say(text) }}
                />}
          </ModulePage>
        )}
      </main>

      {isModalOpen && (
        <AddHoldingModal
          portfolio={portfolio}
          onClose={() => setModalOpen(false)}
          onAdded={(next, ticker, dated) => {
            // Mixing dated and undated purchases: stay on the cautious side.
            changePortfolio(next, datesKnown && dated)
            setModalOpen(false)
            say(`${ticker} was added to your portfolio.`)
          }}
        />
      )}
    </div>
  )
}

// ===========================================================================
// SETTING UP AND ADDING HOLDINGS
// ===========================================================================

type Row = { ticker: string; shares: string; price: string; market: string; date: string }
const emptyRow = (): Row => ({ ticker: '', shares: '', price: '', market: 'US', date: '' })
const today = () => new Date().toISOString().slice(0, 10)

function PortfolioSetup({ onComplete, onCancel }: { onComplete: (p: Portfolio, datesKnown: boolean) => void; onCancel?: () => void }) {
  const [rows, setRows] = useState<Row[]>([emptyRow(), emptyRow()])
  const [busy, setBusy] = useState('')
  const [problems, setProblems] = useState<string[]>([])
  const [imported, setImported] = useState<{ portfolio: Portfolio; problems: string[] } | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  function updateRow(index: number, key: keyof Row, value: string) {
    setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, [key]: value } : row))
  }

  async function finishSetup(event: FormEvent) {
    event.preventDefault()
    const filled = rows.filter((row) => row.ticker.trim())
    if (!filled.length) { setProblems(['Enter at least one holding to continue.']); return }
    setBusy('Checking your holdings…')
    setProblems([])
    // core/ checks every row, with its usual plain-English messages.
    let portfolio: Portfolio = { holdings: [], trades: [] }
    const found: string[] = []
    for (const row of filled) {
      try {
        portfolio = (await api.add(portfolio, {
          ticker: row.ticker, shares: Number(row.shares), price: Number(row.price), market: row.market,
          buy_date: row.date || undefined,
        })).portfolio
      } catch (error) {
        found.push(`${row.ticker.toUpperCase()}: ${(error as Error).message}`)
      }
    }
    setBusy('')
    if (found.length) { setProblems(found); return }
    onComplete(portfolio, filled.every((row) => row.date))
  }

  async function bring(load: () => Promise<{ portfolio: Portfolio; problems: string[] }>) {
    setBusy('Reading the positions file…')
    setProblems([])
    try {
      setImported(await load())
    } catch (error) {
      setProblems([(error as Error).message])
    }
    setBusy('')
  }

  return (
    <main className="setup-page">
      <header className="setup-header">
        <div className="brand setup-brand"><div className="brand-mark"><Icon name="spark" size={19} /></div><span>MyPortfolio</span></div>
        {onCancel ? <button className="text-button" onClick={onCancel}>Back to my portfolio</button> : <span>Step 1 of 8</span>}
      </header>
      <div className="setup-layout">
        <section className="setup-intro">
          <p className="setup-kicker">LET’S GET STARTED</p>
          <h1>What do you own today?</h1>
          <p>Add the stocks in your portfolio, or bring in your broker’s positions file. We’ll organize them into a clear dashboard before showing any analysis or optimization.</p>
          <Tip page="Setup" />
          <div className="setup-benefits">
            <span><i><Icon name="grid" size={16} /></i><strong>See the big picture<small>Value, gains and allocation in one place</small></strong></span>
            <span><i><Icon name="chart" size={16} /></i><strong>Understand each holding<small>Start with a score, then explore the details</small></strong></span>
            <span><i><Icon name="shield" size={16} /></i><strong>Check your portfolio risk<small>Plain-English warnings, not technical jargon</small></strong></span>
          </div>
        </section>
        <section className="setup-card">
          <div className="setup-card-heading"><span className="modal-icon"><Icon name="briefcase" /></span><div><h2>Set up my portfolio</h2><p>Import a file, try the sample, or enter holdings by hand.</p></div></div>
          <div className="import-strip">
            <input ref={fileInput} type="file" accept=".csv" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) bring(() => api.importFile(f)); e.target.value = '' }} />
            <button type="button" onClick={() => fileInput.current?.click()}><Icon name="plus" size={14} /> Import broker file (.csv)</button>
            <button type="button" onClick={() => bring(api.sample)}>Try a sample portfolio</button>
          </div>
          {imported ? (
            <div className="imported">
              <strong>Read {imported.portfolio.holdings.length} holdings.</strong>
              <p>Broker files don’t include purchase dates, so value over time, the S&P 500 twin and a few date-based warnings are switched off.</p>
              {imported.problems.map((p) => <p className="problem-line" key={p}>{p}</p>)}
              <div className="setup-footer">
                <button type="button" className="secondary" onClick={() => setImported(null)}>Cancel</button>
                <button type="button" onClick={() => onComplete(imported.portfolio, false)}>Open my dashboard <Icon name="chevron" size={15} /></button>
              </div>
            </div>
          ) : (
            <form onSubmit={finishSetup}>
              <div className="setup-table-head"><span>Symbol</span><span>Shares</span><span>Avg. cost</span><span>Market</span><span>Bought (optional)</span><span /></div>
              {rows.map((row, index) => (
                <div className="setup-row" key={index}>
                  <input aria-label={`Stock symbol ${index + 1}`} value={row.ticker} onChange={(e) => updateRow(index, 'ticker', e.target.value.toUpperCase())} placeholder={index ? 'RY' : 'AAPL'} />
                  <input aria-label={`Shares ${index + 1}`} type="number" min="0" step="any" value={row.shares} onChange={(e) => updateRow(index, 'shares', e.target.value)} placeholder="0" />
                  <div className="money-input"><span>$</span><input aria-label={`Average cost ${index + 1}`} type="number" min="0" step="0.01" value={row.price} onChange={(e) => updateRow(index, 'price', e.target.value)} placeholder="0.00" /></div>
                  <select aria-label={`Market ${index + 1}`} value={row.market} onChange={(e) => updateRow(index, 'market', e.target.value)}><option value="US">USD</option><option value="CA">CAD</option></select>
                  <input aria-label={`Buy date ${index + 1}`} type="date" max={today()} value={row.date} onChange={(e) => updateRow(index, 'date', e.target.value)} />
                  <button type="button" aria-label={`Remove row ${index + 1}`} onClick={() => rows.length > 1 && setRows((current) => current.filter((_, rowIndex) => rowIndex !== index))}><Icon name="close" size={15} /></button>
                </div>
              ))}
              <button className="add-row-button" type="button" onClick={() => setRows((current) => [...current, emptyRow()])}><Icon name="plus" size={15} /> Add another holding</button>
              <div className="setup-footer"><span>CAD stocks get .TO added (RY → RY.TO). Buy dates turn on value over time and the S&P 500 twin.</span><button type="submit" disabled={!!busy}>Create my dashboard <Icon name="chevron" size={15} /></button></div>
            </form>
          )}
          {busy && <div className="setup-status"><Loading text={busy} /></div>}
          {problems.length > 0 && <div className="setup-status">{problems.map((p) => <p className="problem-line" key={p}>{p}</p>)}</div>}
        </section>
      </div>
    </main>
  )
}

function AddHoldingModal({ portfolio, onClose, onAdded }: { portfolio: Portfolio; onClose: () => void; onAdded: (p: Portfolio, ticker: string, dated: boolean) => void }) {
  const [problem, setProblem] = useState('')
  const [busy, setBusy] = useState(false)

  async function addHolding(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const data = new FormData(event.currentTarget)
    const date = String(data.get('date') || '')
    setBusy(true)
    setProblem('')
    try {
      const { portfolio: next } = await api.add(portfolio, {
        ticker: String(data.get('ticker') || ''), shares: Number(data.get('shares')), price: Number(data.get('price')),
        market: String(data.get('market')), buy_date: date || undefined,
      })
      const added = String(next.holdings[next.holdings.length - 1]?.ticker ?? data.get('ticker'))
      onAdded(next, added, !!date)
    } catch (error) {
      setProblem((error as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(event) => event.stopPropagation()}>
        <div className="modal-heading"><div className="modal-icon"><Icon name="briefcase" /></div><div><h2>Add a holding</h2><p>Record a purchase. CAD stocks get .TO added for you.</p></div><button onClick={onClose}><Icon name="close" /></button></div>
        <form onSubmit={addHolding}>
          <label>Stock symbol<input name="ticker" placeholder="e.g. AAPL or RY" required /></label>
          <div className="form-row"><label>Number of shares<input name="shares" type="number" min="0.0001" step="any" placeholder="0" required /></label><label>Price paid per share<input name="price" type="number" min="0.01" step="0.01" placeholder="0.00" required /></label></div>
          <div className="form-row">
            <label>Market<select name="market"><option value="US">United States (USD)</option><option value="CA">Canada (CAD)</option></select></label>
            <label>Buy date (optional)<input name="date" type="date" max={today()} /></label>
          </div>
          {problem && <p className="problem-line">{problem}</p>}
          <div className="modal-actions"><button type="button" onClick={onClose}>Cancel</button><button type="submit" disabled={busy}>{busy ? 'Adding…' : 'Add holding'}</button></div>
        </form>
      </div>
    </div>
  )
}

// ===========================================================================
// THE DASHBOARD
// ===========================================================================

type Loaded<T> = { data?: T; error?: ApiError; loading: boolean; retry: () => void }

/** Totals across both currency groups, in the home currency (the same math as the Streamlit overview). */
function totals(summary: Overview['summary']) {
  const { groups, combined } = summary
  const rate = (c: string) => combined.fx_rates[c] ?? 1
  const entries = Object.entries(groups)
  const day = entries.reduce((s, [c, g]) => s + g.day_change * rate(c), 0)
  const cost = entries.reduce((s, [c, g]) => s + g.cost * rate(c), 0)
  const gain = combined.value - cost
  // Each group's lead over its S&P 500 twin, weighted by how much money is in it.
  const twinGroups = entries.filter(([, g]) => g.beat_sp500_by_pct != null && g.value > 0)
  const twinWeight = twinGroups.reduce((s, [c, g]) => s + g.value * rate(c), 0)
  const beat = twinWeight ? twinGroups.reduce((s, [c, g]) => s + (g.beat_sp500_by_pct ?? 0) * g.value * rate(c), 0) / twinWeight : null
  return {
    value: combined.value, currency: combined.currency, day, cost, gain, beat, twinGroups,
    gainPct: cost ? gain / cost * 100 : null,
    dayPct: combined.value - day ? day / (combined.value - day) * 100 : null,
  }
}

function Dashboard({ portfolio, datesKnown, portfolioKey, overview, risks, onNavigate, onSetUp }: {
  portfolio: Portfolio; datesKnown: boolean; portfolioKey: string
  overview: Loaded<Overview>; risks: Loaded<Risks>; onNavigate: (m: string) => void; onSetUp: () => void
}) {
  if (overview.loading) return <div className="content"><Loading text="Getting the latest prices…" /></div>
  if (overview.error || !overview.data) return <div className="content"><Problem error={overview.error ?? new ApiError('No data.')} onRetry={overview.retry} /></div>

  const { positions, summary, notes } = overview.data
  const t = totals(summary)
  const topRisk = risks.data?.top_risks[0]

  return (
    <div className="content">
      <section className="journey-panel">
        <div className="journey-heading">
          <div><p className="label">YOUR INVESTING WORKFLOW</p><h2>From portfolio setup to a confident decision</h2></div>
          <span>8 guided steps</span>
        </div>
        <div className="journey-steps">
          {workflow.map((step, index) => (
            <button
              className={`journey-step ${index === 1 ? 'current' : ''}`}
              key={step.label}
              onClick={() => step.module === 'Set Up Portfolio' ? onSetUp() : onNavigate(step.module)}
            >
              <span className="step-number">{index + 1}</span>
              <span className="step-icon"><Icon name={step.icon as IconName} size={16} /></span>
              <span className="step-copy"><strong>{step.label}</strong><small>{step.ask}</small></span>
              {index < workflow.length - 1 && <span className="step-arrow"><Icon name="chevron" size={13} /></span>}
            </button>
          ))}
        </div>
      </section>
      <Tip page="Dashboard" />
      <Notes notes={notes} />
      <section className="hero-summary">
        <div>
          <p className="label">TOTAL PORTFOLIO VALUE</p>
          <div className="portfolio-value">{money(t.value)} <span>{t.currency}</span></div>
          <div className="gain-line"><span className={t.gain >= 0 ? 'positive' : 'negative'}>{signedMoney(t.gain)} ({signedPct(t.gainPct, 2)})</span><span>since you bought</span></div>
        </div>
        <div className="updated"><span className="live-dot" /> Latest prices from Yahoo Finance</div>
      </section>

      <section className="metric-grid">
        <article className="metric-card">
          <div className="metric-heading"><span>Today’s change</span><span className="mini-icon blue"><Icon name="spark" size={16} /></span></div>
          <strong className="metric-value">{signedMoney(t.day)}</strong>
          <span className={t.day >= 0 ? 'metric-positive' : 'metric-negative'}>{signedPct(t.dayPct, 2)} today</span>
        </article>
        <article className="metric-card">
          <div className="metric-heading"><span>Total gain</span><span className="mini-icon green"><Icon name="chart" size={16} /></span></div>
          <strong className="metric-value">{signedMoney(t.gain)}</strong>
          <span className={t.gain >= 0 ? 'metric-positive' : 'metric-negative'}>{signedPct(t.gainPct, 2)} on {money(t.cost)} paid</span>
        </article>
        <article className="metric-card">
          <div className="metric-heading"><span>S&P 500 twin</span><span className="mini-icon violet"><Icon name="spark" size={16} /></span></div>
          {datesKnown && t.beat != null ? <>
            <strong className="metric-value">{signedPct(t.beat)} pts</strong>
            <span className={t.beat >= 0 ? 'beat-market' : 'metric-negative'}>{t.beat >= 0 ? 'You’re ahead of the market' : 'Behind the market'} · {t.twinGroups.map(([c, g]) => `${c} ${signedPct(g.beat_sp500_by_pct)}`).join(' · ')}</span>
          </> : <>
            <strong className="metric-value">—</strong>
            <span className="muted-copy">Needs buy dates</span>
          </>}
        </article>
        <article className="metric-card">
          <div className="metric-heading"><span>Risk score</span><span className="mini-icon amber"><Icon name="shield" size={16} /></span></div>
          {risks.data ? <>
            <div className="risk-row"><strong className="metric-value">{risks.data.score.toFixed(0)}</strong><span>/ 100</span><span className={`level-pill ${risks.data.level}`}>{risks.data.level.toUpperCase()}</span></div>
            <span className="muted-copy">Higher means riskier</span>
          </> : risks.error ? <span className="muted-copy">{risks.error.message}</span> : <span className="muted-copy">Measuring…</span>}
        </article>
      </section>

      <section className="dashboard-grid">
        <PerformancePanel portfolio={portfolio} portfolioKey={portfolioKey} currencies={Object.keys(summary.groups)} datesKnown={datesKnown} />
        <AllocationPanel positions={positions} total={t.value} onDetails={() => onNavigate('MyStocks')} />
      </section>

      <HoldingsTable positions={positions} />

      {topRisk && (
        <section className="insight-strip">
          <span className="insight-icon"><Icon name="shield" /></span>
          <div><strong>What to watch</strong><p>{topRisk}</p></div>
          <button onClick={() => onNavigate('MyRisks')}>View risks <Icon name="chevron" size={15} /></button>
        </section>
      )}
      <PageEnd page="Dashboard" />
    </div>
  )
}

const RANGES: [string, number][] = [['1M', 22], ['3M', 66], ['1Y', 252], ['All', Infinity]]

function PerformancePanel({ portfolio, portfolioKey, currencies, datesKnown }: { portfolio: Portfolio; portfolioKey: string; currencies: string[]; datesKnown: boolean }) {
  const [currency, setCurrency] = useState(currencies[0] ?? 'CAD')
  const [range, setRange] = useState('All')
  const history = useLoad(() => api.history(portfolio, currency), `${portfolioKey}|${currency}`, datesKnown)

  const header = (
    <div className="panel-header">
      <div><h2>Performance</h2><p>You vs your S&P 500 twin{datesKnown ? `, in ${currency}` : ''}</p></div>
      {datesKnown && <div className="chart-switches">
        {currencies.length > 1 && <div className="range-picker">{currencies.map((c) => <button className={currency === c ? 'selected' : ''} onClick={() => setCurrency(c)} key={c}>{c}</button>)}</div>}
        <div className="range-picker">{RANGES.map(([r]) => <button className={range === r ? 'selected' : ''} onClick={() => setRange(r)} key={r}>{r}</button>)}</div>
      </div>}
    </div>
  )

  if (!datesKnown) {
    return <article className="panel performance-panel">{header}<p className="panel-empty">Value over time needs buy dates. Broker files don’t include them, so this chart is off. Add holdings with their buy dates to turn it on.</p></article>
  }
  if (history.loading) return <article className="panel performance-panel">{header}<Loading text="Drawing your history…" /></article>
  if (history.error || !history.data) return <article className="panel performance-panel">{header}<Problem error={history.error ?? new ApiError('No data.')} onRetry={history.retry} /></article>

  // The thinned history has about one point every few days; keep the share that fits the range.
  const all = history.data
  const days = RANGES.find(([r]) => r === range)?.[1] ?? Infinity
  const cut = Number.isFinite(days) ? Math.max(0, all.dates.length - Math.ceil(days * all.dates.length / Math.max(1, daysBetween(all.dates)))) : 0
  return <article className="panel performance-panel">{header}<LineChart chart={slice(all, cut)} currency={currency} /></article>
}

function daysBetween(dates: string[]) {
  // Trading days covered, roughly: calendar days x 252/365.
  if (dates.length < 2) return 1
  return (Date.parse(dates[dates.length - 1]) - Date.parse(dates[0])) / 86_400_000 * 252 / 365
}

function slice(chart: Chart, from: number): Chart {
  return { dates: chart.dates.slice(from), lines: Object.fromEntries(Object.entries(chart.lines).map(([k, v]) => [k, v.slice(from)])) }
}

function LineChart({ chart, currency }: { chart: Chart; currency: string }) {
  const you = chart.lines['You'] ?? []
  const twin = chart.lines['S&P 500 twin'] ?? []
  const values = [...you, ...twin].filter((v): v is number => v != null)
  if (values.length < 2) return <p className="panel-empty">Not enough history to draw yet.</p>
  const low = Math.min(...values), high = Math.max(...values)
  const span = high - low || 1
  const x = (i: number) => (i / Math.max(1, you.length - 1)) * 500
  const y = (v: number) => 112 - ((v - low) / span) * 104
  const line = (points: (number | null)[]) => points.map((v, i) => v == null ? '' : `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ')
  const ticks = [0, 1, 2, 3].map((i) => high - (span * i) / 3)
  const labels = [0, 1, 2, 3, 4].map((i) => chart.dates[Math.round((i / 4) * (chart.dates.length - 1))])
  const lastYou = you[you.length - 1] ?? 0, lastTwin = twin[twin.length - 1] ?? 0
  return <>
    <div className="chart-legend"><span><i className="legend-line blue-line" />You</span><span><i className="legend-line gray-line" />S&P 500 twin</span><strong>{money(lastYou, currency)} <em className={lastYou >= lastTwin ? '' : 'behind'}>{signedMoney(lastYou - lastTwin)} vs twin</em></strong></div>
    <div className="line-chart">
      <div className="axis-labels">{ticks.map((v) => <span key={v}>${short(v)}</span>)}</div>
      <svg viewBox="0 0 500 120" preserveAspectRatio="none" role="img" aria-label="Your value over time next to your S&P 500 twin">
        <defs><linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#277be9" stopOpacity=".2"/><stop offset="100%" stopColor="#277be9" stopOpacity="0"/></linearGradient></defs>
        <path d={`${line(you)} L500 120 L0 120 Z`} fill="url(#area)" />
        <path d={line(twin)} className="market-path" />
        <path d={line(you)} className="portfolio-path" />
      </svg>
      <div className="date-labels">{labels.map((d, i) => <span key={i}>{new Date(d).toLocaleDateString('en-CA', { month: 'short', year: '2-digit' })}</span>)}</div>
    </div>
  </>
}

function AllocationPanel({ positions, total, onDetails }: { positions: Position[]; total: number; onDetails: () => void }) {
  const sorted = [...positions].filter((p) => p.weight_pct != null).sort((a, b) => (b.weight_pct ?? 0) - (a.weight_pct ?? 0))
  const top = sorted.slice(0, 5)
  const other = sorted.slice(5).reduce((s, p) => s + (p.weight_pct ?? 0), 0)
  let at = 0
  const stops = top.map((p, i) => { const from = at; at += p.weight_pct ?? 0; return `${SLICE_COLOURS[i]} ${from}% ${at}%` })
  stops.push(`#dce2ea ${at}% 100%`)
  return (
    <article className="panel allocation-panel">
      <div className="panel-header"><div><h2>Allocation</h2><p>By holding, compared in CAD</p></div><button className="text-button" onClick={onDetails}>View details <Icon name="chevron" size={14} /></button></div>
      <div className="allocation-content">
        <div className="donut" style={{ background: `conic-gradient(${stops.join(', ')})` }}><div><strong>${short(total)}</strong><span>Total</span></div></div>
        <div className="allocation-list">
          {top.map((item, i) => (
            <div className="allocation-item" key={item.ticker}><span className="color-dot" style={{ background: SLICE_COLOURS[i] }} /><span>{item.ticker}</span><strong>{item.weight_pct?.toFixed(1)}%</strong></div>
          ))}
          {other > 0 && <div className="allocation-item"><span className="color-dot other" /><span>Other ({sorted.length - 5})</span><strong>{other.toFixed(1)}%</strong></div>}
        </div>
      </div>
    </article>
  )
}

function HoldingsTable({ positions, limit = 8 }: { positions: Position[]; limit?: number }) {
  const [search, setSearch] = useState('')
  const [market, setMarket] = useState<'All' | 'CAD' | 'USD'>('All')
  const [showAll, setShowAll] = useState(false)
  const filtered = positions.filter((item) =>
    (market === 'All' || item.currency === market)
    && `${item.ticker} ${item.name ?? ''}`.toLowerCase().includes(search.toLowerCase()))
  const shown = showAll ? filtered : filtered.slice(0, limit)
  const currencies = [...new Set(positions.map((p) => p.currency))]
  return (
    <section className="panel holdings-panel">
      <div className="holdings-header">
        <div><h2>My holdings</h2><p>{positions.length} positions across {currencies.join(' and ')}. Amounts are in each stock’s own currency.</p></div>
        <div className="table-tools">
          <label className="search-box"><Icon name="search" size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search holdings" /></label>
          <button className="filter-button" onClick={() => setMarket(market === 'All' ? 'CAD' : market === 'CAD' ? 'USD' : 'All')}>{market === 'All' ? 'All markets' : market} <span>⌄</span></button>
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead><tr><th>Holding</th><th>Shares</th><th>Avg. cost</th><th>Price</th><th>Market value</th><th>Total gain</th><th>Today</th><th>Allocation</th></tr></thead>
          <tbody>
            {shown.map((item) => (
              <tr key={item.ticker}>
                <td><div className="holding-name"><span className="stock-logo">{item.ticker.slice(0, 1)}</span><span><strong>{item.ticker}</strong><small>{(item.name ?? 'Unknown')} · {item.currency}</small></span></div></td>
                <td>{num(item.shares, item.shares % 1 ? 2 : 0)}</td>
                <td>{money(item.avg_cost)}</td>
                <td>{item.price == null ? <span className="negative-cell">no price</span> : money(item.price)}</td>
                <td><strong>{money(item.value)}</strong></td>
                <td className={upDown(item.gain)}><strong>{signedMoney(item.gain)}</strong><small>{signedPct(item.gain_pct)}</small></td>
                <td className={upDown(item.day_change_pct)}>{signedPct(item.day_change_pct, 2)}</td>
                <td><div className="allocation-bar"><span>{item.weight_pct == null ? 'n/a' : `${item.weight_pct.toFixed(1)}%`}</span><i><b style={{ width: `${Math.min((item.weight_pct ?? 0) * 3.2, 100)}%` }} /></i></div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {filtered.length > limit && <button className="show-all" onClick={() => setShowAll(!showAll)}>{showAll ? 'Show fewer' : `Show all ${filtered.length} holdings`} <Icon name="chevron" size={14} /></button>}
    </section>
  )
}

// ===========================================================================
// THE GUIDED STEPS
// ===========================================================================

const MODULES: Record<string, { kicker: string; title: string; text: string }> = {
  MyStocks: { kicker: 'STEP 2 · CURRENT POSITION', title: 'Where am I now?', text: 'Review what you own, what it is worth today and whether your portfolio is beating its S&P 500 twin.' },
  MyAnalysis: { kicker: 'STEP 3 · 7-PART STOCK REVIEW', title: 'Are these good investments?', text: 'Business health, rivals, economy, price action, analysts and fair value, combined into one clear verdict. A rule of thumb for what to look into, not what to buy or sell.' },
  MyRisks: { kicker: 'STEP 4 · 8-AREA RISK REVIEW', title: 'What could go wrong?', text: 'Concentration, sectors, currencies, correlation, market exposure, drawdown and bad days, in plain English. Based on the past few years: a guide, not a promise.' },
  MyOptimizer: { kicker: 'STEP 5 · PORTFOLIO OPTIMIZER', title: 'Is there a better allocation?', text: 'Thousands of mixes of the stocks you own, tested on their past prices against your rules. The best mix for the past is rarely the best for the future: use it as a starting point.' },
  MyEdit: { kicker: 'STEP 6 · SCENARIO EDITOR', title: 'What if I change it?', text: 'Adjust individual stock weights and see the effect on return, swings, worst drop and your rules.' },
  'Decision / Action': { kicker: 'STEP 7 · DECISION', title: 'Turn the analysis into an action.', text: 'Pick the mix you want to move toward. Nothing is bought or sold here.' },
  'Warning Check': { kicker: 'STEP 8 · BEHAVIOUR CHECK', title: 'Pause before you update.', text: 'Check each planned trade for chasing, panic selling, concentration, loss aversion and other common investing traps. It never blocks a trade: it’s your call.' },
}

function ModulePage({ module, onBack, onNext, children }: { module: string; onBack: () => void; onNext: (module: string) => void; children: ReactNode }) {
  const data = MODULES[module]
  const currentIndex = workflow.findIndex((step) => step.module === module)
  const nextModule = workflow[currentIndex + 1]?.module
  return (
    <div className="module-page">
      <div className="module-progress">
        {workflow.map((step, index) => <span className={index <= currentIndex ? 'complete' : ''} key={step.label}><i />{step.label}</span>)}
      </div>
      <section className="module-hero"><p>{data.kicker}</p><h2>{data.title}</h2><span>{data.text}</span><div className="module-actions"><button onClick={onBack}>Back to Dashboard</button>{nextModule ? <button onClick={() => onNext(nextModule)}>Continue to {workflow[currentIndex + 1].label} <Icon name="chevron" size={15} /></button> : <button onClick={onBack}>Return to Dashboard <Icon name="chevron" size={15} /></button>}</div></section>
      <Tip page={module} />
      {children}
      <PageEnd page={module} />
    </div>
  )
}

function Stats({ items }: { items: [string, string][] }) {
  return <section className="module-stats">{items.map(([value, label]) => <article key={label}><strong>{value}</strong><span>{label}</span><i /></article>)}</section>
}

// --- Step 2: MyStocks --------------------------------------------------------

function MyStocksPage({ overview, datesKnown }: { overview: Loaded<Overview>; datesKnown: boolean }) {
  if (overview.loading) return <Loading text="Getting the latest prices…" />
  if (overview.error || !overview.data) return <Problem error={overview.error ?? new ApiError('No data.')} onRetry={overview.retry} />
  const { positions, summary, notes } = overview.data
  const t = totals(summary)
  return <>
    <Stats items={[
      [money(t.value), `Portfolio value (${t.currency})`],
      [signedPct(t.gainPct), 'Total return'],
      [datesKnown && t.beat != null ? `${signedPct(t.beat)} pts` : '—', datesKnown ? 'Vs the S&P 500 twin' : 'Twin needs buy dates'],
      [String(positions.length), 'Current holdings'],
    ]} />
    <Notes notes={notes} />
    <section className="metric-grid group-grid">
      {Object.entries(summary.groups).map(([currency, g]) => <GroupCard key={currency} currency={currency} group={g} datesKnown={datesKnown} />)}
    </section>
    <HoldingsTable positions={positions} limit={50} />
  </>
}

function GroupCard({ currency, group: g, datesKnown }: { currency: string; group: Group; datesKnown: boolean }) {
  return (
    <article className="metric-card">
      <div className="metric-heading"><span>{currency} holdings · {g.stocks} stocks</span></div>
      <strong className="metric-value">{money(g.value, currency)}</strong>
      <span className={g.gain >= 0 ? 'metric-positive' : 'metric-negative'}>Gain {signedMoney(g.gain)} ({signedPct(g.gain_pct)}) · Today {signedPct(g.day_change_pct, 2)}</span>
      {g.realized_gain !== 0 && <span className="muted-copy">Locked in by sales: {signedMoney(g.realized_gain, currency)}</span>}
      {datesKnown && g.beat_sp500_by_pct != null && <span className="muted-copy">S&P 500 twin {signedPct(g.sp500_twin_gain_pct)}, you beat it by {signedPct(g.beat_sp500_by_pct)} pts</span>}
      {g.left_out.length > 0 && <span className="metric-negative">Not counted (no price today): {g.left_out.join(', ')}</span>}
    </article>
  )
}

// --- Step 3: MyAnalysis --------------------------------------------------------

function AnalysisPage({ tickers, verdicts, onVerdict, tabCache, onTabCache }: {
  tickers: string[]; verdicts: Record<string, Verdict>; onVerdict: (key: string, v: Verdict) => void
  tabCache: Record<string, unknown>; onTabCache: (key: string, v: unknown) => void
}) {
  const [ticker, setTicker] = useState(tickers[0] ?? '')
  const [typed, setTyped] = useState('')
  const [rivals, setRivals] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)
  const cacheKey = `${ticker}|${rivals}`
  const verdict = verdicts[cacheKey]

  useEffect(() => {
    if (!ticker || verdicts[cacheKey]) return
    let live = true
    setBusy(true)
    setError(null)
    api.verdict(ticker, rivals).then(
      (v) => { if (live) { onVerdict(cacheKey, v); setBusy(false) } },
      (e) => { if (live) { setError(e instanceof ApiError ? e : new ApiError(String(e))); setBusy(false) } },
    )
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cacheKey, attempt])

  const colour = VERDICT_COLOUR[verdict?.verdict ?? ''] ?? '#9aa4b3'
  return (
    <section className="detail-workspace">
      <div className="stock-picker">
        <div className="stock-logo">{ticker.slice(0, 1) || '?'}</div>
        <div><strong>{ticker || 'Pick a stock'}</strong><span>{verdict?.name ?? (busy ? 'Analysing…' : ' ')}</span></div>
        <select value={tickers.includes(ticker) ? ticker : ''} onChange={(e) => e.target.value && setTicker(e.target.value)} aria-label="Your stocks">
          <option value="">Your stocks…</option>
          {tickers.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <form className="ticker-form" onSubmit={(e) => { e.preventDefault(); if (typed.trim()) setTicker(typed.trim().toUpperCase()) }}>
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder="Any ticker, like MSFT" aria-label="Any ticker" />
        </form>
        <label className="toggle"><input type="checkbox" checked={rivals} onChange={(e) => setRivals(e.target.checked)} /> Include rivals (slower)</label>
      </div>
      {busy ? <Loading text={`Analysing ${ticker}… the first time takes ${rivals ? 'up to a minute' : 'about 15 seconds'}.`} />
        : error ? <Problem error={error} onRetry={() => setAttempt((n) => n + 1)} />
        : verdict ? (<>
          <div className="score-layout">
            <div className="overall-score">
              <p>OVERALL SCORE</p>
              <div className="score-ring" style={ring(verdict.score, colour)}><strong>{verdict.score == null ? '—' : verdict.score.toFixed(0)}</strong><span>/ 100</span></div>
              <b style={{ color: colour, background: `${colour}18` }}>{verdict.verdict.toUpperCase()}</b>
              <small>{VERDICT_PLAIN[verdict.verdict]} Momentum: {verdict.momentum.reading}.</small>
            </div>
            <div className="score-breakdown">
              <div className="score-title"><div><h3>What’s behind the score?</h3><p>Six parts, each 0 to 100. Skipped parts don’t count, and the others grow to fill the gap.</p></div><span>3G Final Verdict</span></div>
              {verdict.parts.map((p) => (
                <div className="score-row" key={p.part} title={p.skipped_because || p.summary}>
                  <span className="part-tag">{PART_TAG[p.part] ?? ''}</span>
                  <strong>{p.part}</strong>
                  <i><b style={{ width: `${p.score ?? 0}%` }} /></i>
                  <em className={p.score != null && p.score < 60 ? 'score-medium' : ''}>{p.score == null || p.weight_pct === 0 ? '—' : p.score.toFixed(0)}</em>
                  <small className="part-summary">{p.weight_pct > 0 ? `${p.weight_pct.toFixed(0)}% · ${p.summary}` : `Skipped: ${p.skipped_because}`}</small>
                </div>
              ))}
              <div className="reasons">
                {verdict.strengths.length > 0 && <div><h4>What looks good</h4>{verdict.strengths.map((s) => <p key={s}>✅ {s}</p>)}</div>}
                {verdict.concerns.length > 0 && <div><h4>What to look at</h4>{verdict.concerns.map((s) => <p key={s}>⚠️ {s}</p>)}</div>}
              </div>
              {verdict.health_checks.length > 0 && (
                <details className="health-checks"><summary>Health checks behind “Business health”</summary>
                  {verdict.health_checks.map((c) => <p key={c.check}><span className={`level-pill ${c.result === 'pass' ? 'low' : c.result === 'fail' ? 'high' : ''}`}>{c.result.toUpperCase()}</span> {c.check}: {c.detail}</p>)}
                </details>
              )}
            </div>
          </div>
          <StockTabs ticker={ticker} cache={tabCache} onCache={onTabCache} />
        </>) : <p className="panel-empty">Pick one of your stocks, or type any ticker.</p>}
    </section>
  )
}

// --- The five tabs under a stock's verdict (Emma's "Look closer" tabs) -------------

const TAB_COLOUR: Record<string, string> = {
  positive: '#17875d', undervalued: '#17875d', strong: '#17875d',
  mixed: '#e6a432', 'fairly valued': '#2475df', average: '#e6a432',
  negative: '#cf5255', overvalued: '#cf5255', weak: '#cf5255', 'no coverage': '#9aa4b3', 'n/a': '#9aa4b3',
}

function pill(word: string) {
  const colour = TAB_COLOUR[word] ?? '#596579'
  return <span className="tab-pill" style={{ color: colour, background: `${colour}18` }}>{word}</span>
}

/** One of core/'s tables as it comes. Numbers get 2 decimals; points read +1 / 0 / -1; verdict words get a colour. */
function DataTable({ grid, wide = false }: { grid: Grid; wide?: boolean }) {
  const cell = (column: string, value: string | number | null) => {
    if (value == null) return '—'
    if (column === 'points' && typeof value === 'number') return value > 0 ? '+1' : value < 0 ? '−1' : '0'
    if (column === 'verdict' && typeof value === 'string') return pill(value)
    if (typeof value === 'number') return num(value, 2)
    return value
  }
  return (
    <div className={`table-scroll data-table ${wide ? 'wide' : ''}`}>
      <table>
        <thead><tr>{grid.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{grid.rows.map((row, i) => <tr key={i}>{row.map((v, j) => <td key={j} className={grid.columns[j] === 'why' ? 'why' : ''}>{cell(grid.columns[j], v)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}

function StockTabs({ ticker, cache, onCache }: { ticker: string; cache: Record<string, unknown>; onCache: (key: string, v: unknown) => void }) {
  const [tab, setTab] = useState<StockTab>('technicals')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  const [attempt, setAttempt] = useState(0)
  const key = `${ticker}|${tab}`
  const data = cache[key]

  // A tab loads the first time it's opened (Emma's "Load" buttons, one click fewer).
  useEffect(() => {
    if (data) return
    let live = true
    setBusy(true)
    setError(null)
    api.stockTab(ticker, tab).then(
      (answer) => { if (live) { onCache(key, answer); setBusy(false) } },
      (e) => { if (live) { setError(e instanceof ApiError ? e : new ApiError(String(e))); setBusy(false) } },
    )
    return () => { live = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, attempt])

  const caption = STOCK_TABS.find(([k]) => k === tab)?.[2]
  return (
    <div className="stock-tabs">
      <div className="tab-bar" role="tablist">
        {STOCK_TABS.map(([k, label]) => <button role="tab" aria-selected={tab === k} className={tab === k ? 'selected' : ''} onClick={() => setTab(k as StockTab)} key={k}>{label}</button>)}
      </div>
      <p className="muted-copy tab-caption">{caption}</p>
      {busy ? <Loading text={tab === 'rivals' ? 'Downloading rivals… 15–30 s first time.' : `Loading ${ticker}…`} />
        : error ? <Problem error={error} onRetry={() => setAttempt((n) => n + 1)} />
        : data ? <StockTabBody tab={tab} data={data} /> : null}
    </div>
  )
}

function StockTabBody({ tab, data }: { tab: StockTab; data: unknown }) {
  if (tab === 'technicals') {
    const s = data as TechnicalsTab
    return <>
      <p className="tab-headline">Signal: {pill(s.verdict)} (score {s.score.toFixed(0)}) · price {num(s.price)} on {s.as_of}</p>
      <DataTable grid={s.signals} />
      <ChartGroup title="Price chart with technical levels" open figures={[[s.charts.chart, 520]]}>
        <p className="muted-copy">The entry and stop lines are suggested price levels, not trade orders.</p>
      </ChartGroup>
    </>
  }
  if (tab === 'analysts') {
    const s = data as AnalystsTab
    return <>
      <p className="tab-headline">Analysts: {pill(s.verdict)}{s.score != null && ` (score ${s.score.toFixed(0)})`}</p>
      <DataTable grid={s.signals} />
      <ChartGroup title="Where analysts think the price will be in a year" open figures={[[s.charts.targets, 300]]} />
      {s.target_currency_note && <p className="muted-copy">{s.target_currency_note}</p>}
    </>
  }
  if (tab === 'dcf') {
    const r = data as DcfTab
    return <>
      <div className="dcf-card">
        <span className="muted-copy">Value per share</span>
        <strong>{num(r.value_per_share)} {r.currency}</strong>
        <span className="muted-copy">Price {num(r.price)} · {pill(r.verdict)} ({signedPct(r.upside_pct, 0)})</span>
      </div>
      {r.notes.map((n) => <p className="muted-copy" key={n}>• {n}</p>)}
      <DataTable grid={r.assumptions} />
      <ChartGroup title="How the value of one share is built" open figures={[[r.charts.bridge, 320]]} />
      <details className="chart-group"><summary>Sensitivity: the value per share if the guesses are off</summary><DataTable grid={r.sensitivity} /></details>
    </>
  }
  if (tab === 'ratios') {
    const r = data as RatiosTab
    return r.ratios ? <DataTable grid={r.ratios} wide /> : <p className="panel-empty">No financial statements available (common for ETFs and funds).</p>
  }
  const r = data as RivalsTab
  return <>
    <p className="tab-headline">Rivals: {r.rivals.join(', ')}</p>
    <DataTable grid={r.scores} />
    <ChartGroup title={`${r.company} vs its rivals (0 to 100)`} open figures={[[r.charts.scores, 320]]} />
  </>
}

// --- Step 4: MyRisks --------------------------------------------------------------

function RiskPage({ risks }: { risks: Loaded<Risks> }) {
  const [open, setOpen] = useState<string | null>(null)
  if (risks.loading) return <Loading text="Measuring risk from past prices…" />
  if (risks.error || !risks.data) return <Problem error={risks.error ?? new ApiError('No data.')} onRetry={risks.retry} />
  const r = risks.data
  const colour = LEVEL_COLOUR[r.level]
  const worst = r.areas.find((a) => a.area === 'Worst drop')
  return <>
    <Stats items={[
      [`${r.score.toFixed(0)} / 100`, 'Risk score (higher = riskier)'],
      [r.beta.toFixed(2), 'Portfolio beta'],
      [`-${r.stress.expected_fall_pct.toFixed(0)}%`, `If the S&P 500 fell ${r.stress.market_fall_pct}%`],
      [`-${r.bad_day.loss_pct.toFixed(1)}%`, 'Bad day (1 in 20)'],
    ]} />
    <Notes notes={r.notes} />
    <section className="detail-workspace risk-workspace">
      <div className="risk-score-card">
        <p>PORTFOLIO RISK</p>
        <div className="score-ring risk-ring" style={ring(r.score, colour)}><strong>{r.score.toFixed(0)}</strong><span>/ 100</span></div>
        <b style={{ color: colour, background: `${colour}18` }}>{r.level.toUpperCase()}</b>
        <small>Based on {r.period.years} years of prices ({r.period.start} to {r.period.end}). A low score means no area crossed its warning line, not that nothing can fall.</small>
        {worst && <small>{worst.reading}</small>}
      </div>
      <div className="risk-list">
        <div className="score-title"><div><h3>What could go wrong?</h3><p>Eight areas. Tap one to see what we found.</p></div></div>
        {r.left_out.length > 0 && <p className="problem-line">Left out (no price history): {r.left_out.join(', ')}. Canadian stocks need .TO, like RY.TO.</p>}
        {r.areas.map((a) => (
          <div key={a.area}>
            <button className="risk-item" onClick={() => setOpen(open === a.area ? null : a.area)}>
              <span className={`risk-status ${a.level === 'n/a' ? '' : a.level}`}>{a.level === 'low' ? '✓' : a.level === 'n/a' ? '–' : '!'}</span>
              <strong>{a.area}</strong>
              <span className={`level-pill ${a.level === 'n/a' ? '' : a.level}`}>{a.level === 'n/a' ? 'N/A' : a.level.toUpperCase()}</span>
              <Icon name="chevron" size={15} />
            </button>
            {open === a.area && <div className="risk-reading">{AREA_HELP[a.area] && <small>{AREA_HELP[a.area]}</small>}<p>{a.reading}</p></div>}
          </div>
        ))}
        {r.top_risks.length > 0 && <div className="reasons"><div><h4>What to watch</h4>{r.top_risks.map((t) => <p key={t}>⚠️ {t}</p>)}</div></div>}
      </div>
    </section>
    <ChartGroup title="Charts: sectors, moving together, money vs risk, worst drops" figures={[
      // The grid gets taller with more stocks, so every square stays readable.
      [r.charts.sectors, 300], [r.charts.correlation, Math.max(360, r.correlation.tickers.length * 28 + 140)],
      [r.charts.risk_share, 320], [r.charts.drawdown, 300],
    ]} />
  </>
}

// --- Step 5: MyOptimizer ------------------------------------------------------------

function OptimizerPage({ portfolio, result, onResult, onEdit }: { portfolio: Portfolio; result: Optimized | null; onResult: (r: Optimized) => void; onEdit: () => void }) {
  const [goal, setGoal] = useState('sharpe')
  const [rules, setRules] = useState({ max_drawdown_pct: 25, min_return_pct: 8, max_weight_pct: 30, min_weight_pct: 0 })
  const [extra, setExtra] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const add = extra.split(',').map((t) => t.trim().toUpperCase()).filter(Boolean)
      onResult(await api.optimize(portfolio, { goal, add, ...rules }))
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(String(e)))
    }
    setBusy(false)
  }

  const rule = (key: keyof typeof rules, label: string, min: number, max: number) => (
    <label className="rule-input"><span>{label}<small className="rule-help">{RULE_HELP[key]}</small></span><strong><input type="number" min={min} max={max} value={rules[key]} onChange={(e) => setRules({ ...rules, [key]: Number(e.target.value) })} />%</strong></label>
  )
  const current = result?.comparison.find((m) => m.mix === 'Your current mix')
  const best = result?.comparison.find((m) => m.mix === 'Best mix')

  return (<>
    <section className="optimizer-workspace">
      <div className="optimizer-settings">
        <p className="setup-kicker">YOUR RULES</p><h3>Would you like to improve your portfolio allocation?</h3>
        <label>My goal</label>
        {GOALS.map(([key, label]) => <button className={`goal-option ${goal === key ? 'selected' : ''}`} onClick={() => setGoal(key)} key={key}><i />{label}</button>)}
        <small className="rule-help">{RULE_HELP.goal}</small>
        {rule('max_drawdown_pct', 'Biggest fall I’d accept', 5, 80)}
        {rule('min_return_pct', 'Least yearly return', 0, 40)}
        {rule('max_weight_pct', 'Most in any one stock', 5, 100)}
        {rule('min_weight_pct', 'Least in any one stock', 0, 50)}
        <label className="rule-input stacked"><span>Also consider (optional)</span><input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="MSFT, TD.TO" /></label>
        <button className="optimize-button" onClick={run} disabled={busy}><Icon name="spark" size={16} />{busy ? 'Trying thousands of mixes…' : 'Optimize My Portfolio'}</button>
      </div>
      <div className={`optimizer-results ${result ? 'visible' : ''}`}>
        {busy ? <Loading text="Trying 20,000 mixes on the past three years…" /> : error ? <Problem error={error} /> : <>
          <div className="score-title"><div><h3>{result ? 'Your mix now vs the best mix we found' : 'See a better allocation'}</h3><p>{result ? result.message : 'Set your rules and run the optimizer to compare.'}</p></div>{result?.status === 'ok' && <span>{GOALS.find(([k]) => k === result.goal)?.[1]}</span>}</div>
          <div className="comparison-head"><span /><strong>Current</strong><strong>Best</strong></div>
          {([['Yearly return', 'yearly return %', '%'], ['Yearly swings', 'yearly swings %', '%'], ['Sharpe ratio', 'Sharpe ratio', ''], ['Worst drop', 'worst drop %', '%'], ['$10,000 became', '$10,000 became', '$']] as const).map(([label, k, unit]) => (
            <div className="comparison-row" key={label}><strong>{label}</strong><span>{fmtMix(current?.[k], unit)}</span><span className={best ? 'suggested-value' : ''}>{fmtMix(best?.[k], unit)}</span></div>
          ))}
          {result && result.status === 'ok' && <>
            <div className="weights-compare">
              <div className="comparison-head"><span>Stock</span><strong>Now</strong><strong>Best</strong></div>
              {result.tickers.map((t) => <div className="comparison-row" key={t}><strong>{t}</strong><span>{(result.current_weights[t] ?? 0).toFixed(1)}%</span><span className="suggested-value">{(result.best_weights[t] ?? 0).toFixed(1)}%</span></div>)}
            </div>
            <button className="optimize-button" onClick={onEdit}>Tweak it in MyEdit <Icon name="chevron" size={15} /></button>
          </>}
          {result && <p className="muted-copy">Tested on {result.period.start} to {result.period.end} ({result.period.years} years). Based on the past: the best mix for the past is rarely the best for the future.</p>}
        </>}
      </div>
    </section>
    {result && !busy && <>
      <ChartGroup title="How much money goes in each stock" open figures={[[result.charts.weights, 340]]} />
      <ChartGroup title="Growth of $10,000" figures={[[result.charts.growth, 300]]} />
      <ChartGroup title="All mixes tried" figures={[[result.charts.cloud, 340]]}>
        <p className="muted-copy">Each dot is one mix. Up and to the left is good: more return for less bumpiness. Grey dots break your rules.</p>
      </ChartGroup>
    </>}
  </>)
}

function fmtMix(value: number | null | undefined, unit: string) {
  if (value == null) return '—'
  if (unit === '$') return money(value)
  return unit === '%' ? `${value.toFixed(1)}%` : value.toFixed(2)
}

// --- Step 6: MyEdit -------------------------------------------------------------------

function EditPage({ optimized, edited, edits, onEdited, onOptimize }: {
  optimized: Optimized | null; edited: Optimized | null; edits: Record<string, number>
  onEdited: (r: Optimized | null, edits: Record<string, number>) => void; onOptimize: () => void
}) {
  const [active, setActive] = useState(optimized?.tickers[0] ?? '')
  const [draft, setDraft] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const timer = useRef<number | undefined>(undefined)

  if (!optimized) {
    return <section className="module-placeholder"><span className="module-placeholder-icon"><Icon name="spark" size={28} /></span><h3>Run the optimizer first</h3><p>MyEdit starts from the best mix the optimizer found, so you can tweak it by hand.</p><button className="optimize-button narrow" onClick={onOptimize}>Go to MyOptimizer <Icon name="chevron" size={15} /></button></section>
  }

  const weights = edited?.edit_weights ?? (Object.keys(optimized.best_weights).length ? optimized.best_weights : optimized.current_weights)
  const shown = draft ?? weights[active] ?? 0
  const total = Object.values(weights).reduce((s, v) => s + v, 0)

  function setWeight(value: number) {
    setDraft(value)
    window.clearTimeout(timer.current)
    // Wait until the slider stops for a moment, then replay the edited mix on the server.
    timer.current = window.setTimeout(async () => {
      const next = { ...edits, [active]: value }
      setBusy(true)
      setError('')
      try {
        onEdited(await api.edit(optimized!.result_id, next), next)
      } catch (e) {
        setError((e as Error).message)
      }
      setDraft(null)
      setBusy(false)
    }, 350)
  }

  const best = (edited ?? optimized).comparison.find((m) => m.mix === 'Best mix')
  const mine = edited?.comparison.find((m) => m.mix === 'Your edit')
  const shownCharts = (edited ?? optimized).charts
  return (<>
    <section className="editor-workspace">
      <div className="allocation-editor">
        <div className="score-title"><div><h3>{Object.keys(optimized.best_weights).length ? 'Optimizer suggestion' : 'Your current mix'}</h3><p>A starting point, not an instruction. Set any stock and the others share what’s left in the same proportions.</p></div><span>{total.toFixed(0)}% allocated</span></div>
        <div className="weight-list">
          {optimized.tickers.map((ticker) => (
            <button className={`weight-row ${active === ticker ? 'active' : ''}`} onClick={() => { setActive(ticker); setDraft(null) }} key={ticker}>
              <span className="stock-logo">{ticker.slice(0, 1)}</span><strong>{ticker}{ticker in edits ? ' •' : ''}</strong><i><b style={{ width: `${Math.min(100, (weights[ticker] ?? 0) * 2.5)}%` }} /></i><em>{(weights[ticker] ?? 0).toFixed(1)}%</em>
            </button>
          ))}
        </div>
        <div className="slider-card">
          <div><span>I want {active}</span><strong>{shown.toFixed(1)}%</strong></div>
          <input type="range" min="0" max="100" step="1" value={Math.round(shown)} onChange={(event) => setWeight(Number(event.target.value))} />
          <div className="range-labels"><span>0%</span><span>Your limit: {optimized.limits.max_weight_pct}% in one stock</span><span>100%</span></div>
        </div>
        {Object.keys(edits).length > 0 && <button className="add-row-button" onClick={() => onEdited(null, {})}>Reset to the optimizer’s mix</button>}
      </div>
      <div className="edit-results">
        <p className="setup-kicker">{busy ? 'UPDATING…' : 'LIVE PREVIEW'}</p><h3>{mine ? 'Your edit' : 'Best mix'}</h3>
        <div className="edit-metrics">
          <div><span>Return</span><strong>{fmtMix((mine ?? best)?.['yearly return %'], '%')}</strong></div>
          <div><span>Swings</span><strong>{fmtMix((mine ?? best)?.['yearly swings %'], '%')}</strong></div>
          <div><span>Sharpe</span><strong>{fmtMix((mine ?? best)?.['Sharpe ratio'], '')}</strong></div>
        </div>
        {error ? <div className="rule-warning"><span>!</span><div><strong>That edit didn’t work</strong><p>{error}</p></div></div>
          : edited && edited.breaks.length ? <div className="rule-warning"><span>!</span><div><strong>{edited.message}</strong>{edited.breaks.map((b) => <p key={b}>{b}</p>)}</div></div>
          : edited ? <div className="rule-success"><Icon name="shield" size={17} /><div><strong>All portfolio rules passed</strong><p>{edited.message}</p></div></div>
          : <div className="rule-success"><Icon name="shield" size={17} /><div><strong>Move a slider to try a change</strong><p>We’ll replay it over the same days and say which of your rules it breaks.</p></div></div>}
        <div className="edit-note"><Icon name="spark" size={17} /><p>MyEdit changes are a scenario only. Nothing is bought or sold until you record a trade in the warning check.</p></div>
      </div>
    </section>
    <ChartGroup title="Your edit next to your current mix and the best mix" open figures={[[shownCharts.weights, 340]]} />
    <ChartGroup title="Growth of $10,000" figures={[[shownCharts.growth, 300]]} />
  </>)
}

// --- Step 7: Decision ------------------------------------------------------------------

function DecisionPanel({ optimized, edited, choice, onChoice, onContinue }: {
  optimized: Optimized | null; edited: Optimized | null; choice: 'current' | 'best' | 'edit'
  onChoice: (c: 'current' | 'best' | 'edit') => void; onContinue: () => void
}) {
  const hasBest = !!optimized && Object.keys(optimized.best_weights).length > 0
  const target = choice === 'edit' ? edited?.edit_weights : choice === 'best' ? optimized?.best_weights : null
  const options: ['current' | 'best' | 'edit', string, string, boolean][] = [
    ['current', 'Keep Current Portfolio', 'Make no allocation changes and keep your existing holdings.', true],
    ['best', 'Move Toward the Best Mix', 'Use the optimizer’s suggestion as the target for upcoming trades.', hasBest],
    ['edit', 'Apply MyEdit Allocation', 'Use your adjusted weights as the target for upcoming trades.', !!edited],
  ]
  const changes = target && optimized
    ? optimized.tickers.map((t) => [t, (target[t] ?? 0) - (optimized.current_weights[t] ?? 0)] as const).filter(([, d]) => Math.abs(d) >= 0.5).sort((a, b) => a[1] - b[1])
    : []
  return (
    <section className="decision-workspace">
      <div className="decision-heading"><p className="setup-kicker">YOUR DECISION</p><h3>Which portfolio do you want to move forward with?</h3><p>The optimizer offered a suggestion and MyEdit let you make it yours. Nothing is bought or sold here: record each real trade in the warning check.</p></div>
      <div className="decision-options three">
        {options.map(([key, title, text, possible]) => (
          <button className={choice === key ? 'selected' : ''} disabled={!possible} onClick={() => onChoice(key)} key={key}>
            <span className="decision-radio" /><div><strong>{title}</strong><p>{possible ? text : key === 'edit' ? 'Make an edit in MyEdit first.' : 'Run the optimizer first.'}</p></div>
          </button>
        ))}
      </div>
      {changes.length > 0 && (
        <div className="weights-compare">
          <div className="comparison-head"><span>Planned change</span><strong>Now</strong><strong>Target</strong></div>
          {changes.map(([t, d]) => <div className="comparison-row" key={t}><strong>{d > 0 ? 'Add to' : 'Trim'} {t}</strong><span>{(optimized!.current_weights[t] ?? 0).toFixed(1)}%</span><span className={d > 0 ? 'positive-cell' : 'negative-cell'}>{(target![t] ?? 0).toFixed(1)}% ({d > 0 ? '+' : ''}{d.toFixed(1)} pts)</span></div>)}
        </div>
      )}
      <div className="decision-summary"><div><span>Selected action</span><strong>{options.find(([k]) => k === choice)?.[1]}</strong></div><button onClick={onContinue}>{choice === 'current' ? 'Confirm and check my trades' : 'Check planned trades'} <Icon name="chevron" size={15} /></button></div>
    </section>
  )
}

// --- Step 8: Warning check -----------------------------------------------------------------

function WarningCards({ found, empty }: { found: Warning[]; empty: string }) {
  if (!found.length) return <p className="all-clear">✅ {empty}</p>
  return <>{found.map((w) => (
    <div className={`warning-card ${w.level === 'caution' ? 'caution' : ''}`} key={w.trap + w.message}>
      <div><strong>{w.trap}</strong><span className={`level-pill ${w.level === 'caution' ? 'high' : 'medium'}`}>{w.level.toUpperCase()}</span></div>
      <p>{w.message}</p><small>{w.tip}</small>
    </div>
  ))}</>
}

function CoachCard({ tip }: { tip: CoachTip | null }) {
  if (!tip) return null
  if (tip.status !== 'ok') return <p className="muted-copy">🤖 AI coach: {tip.why}</p>
  return (
    <div className="coach-card">
      <strong>🤖 AI coach</strong>
      <p>{tip.note}</p>
      {tip.biases.map((b) => <p key={b.bias}>🧠 <b>{b.bias}</b>: you wrote “{b.quote}”. <span className="muted-copy">({b.meaning})</span></p>)}
      <small>{tip.disclaimer}</small>
    </div>
  )
}

function WarningCheck({ portfolio, datesKnown, standing, onRecorded }: {
  portfolio: Portfolio; datesKnown: boolean; standing: Loaded<{ warnings: Warning[] }>
  onRecorded: (p: Portfolio, text: string) => void
}) {
  const [trade, setTrade] = useState<Trade>({ action: 'buy', ticker: '', shares: 0, price: 0 })
  const [reason, setReason] = useState('')
  const [checked, setChecked] = useState<{ trade: Trade; warnings: Warning[]; tip: CoachTip | null } | null>(null)
  const [busy, setBusy] = useState('')
  const [problem, setProblem] = useState('')

  async function check(event: FormEvent) {
    event.preventDefault()
    setBusy('Checking for traps, and asking your coach…')
    setProblem('')
    setChecked(null)
    try {
      const answer = await api.checkTrade(portfolio, trade, reason, datesKnown)
      setChecked({ trade, ...answer })
    } catch (e) {
      setProblem((e as Error).message)
    }
    setBusy('')
  }

  async function record() {
    if (!checked) return
    setBusy('Recording…')
    setProblem('')
    try {
      const { portfolio: next } = await api.recordTrade(portfolio, checked.trade)
      const t = checked.trade
      setChecked(null)
      onRecorded(next, `Recorded: ${t.action} ${t.shares} ${t.ticker.toUpperCase()} at ${t.price}.`)
    } catch (e) {
      setProblem((e as Error).message)
    }
    setBusy('')
  }

  return (
    <section className="warning-workspace">
      <div className="warning-sidebar">
        <p>HEADS-UP ON WHAT YOU OWN</p>
        {standing.loading ? <Loading text="Checking…" /> : standing.error ? <Problem error={standing.error} onRetry={standing.retry} />
          : <WarningCards found={standing.data?.warnings ?? []} empty="No traps spotted in what you own." />}
        {!datesKnown && <small className="muted-copy">Warnings that need purchase dates are hidden, because imported files don’t include them.</small>}
      </div>
      <div className="trade-check">
        <p className="setup-kicker">TRADE CHECK</p>
        <h3>Thinking of a trade? Check it first</h3>
        <p className="trade-help">{TRADE_HELP}</p>
        <form className="trade-form" onSubmit={check}>
          <div className="segmented">{(['buy', 'sell'] as const).map((a) => <button type="button" className={trade.action === a ? 'selected' : ''} onClick={() => setTrade({ ...trade, action: a })} key={a}>{a === 'buy' ? 'Buy' : 'Sell'}</button>)}</div>
          <div className="form-row three">
            <label>Ticker<input value={trade.ticker} onChange={(e) => setTrade({ ...trade, ticker: e.target.value.toUpperCase() })} placeholder="AAPL or RY.TO" required /></label>
            <label>Shares<input type="number" min="0" step="any" value={trade.shares || ''} onChange={(e) => setTrade({ ...trade, shares: Number(e.target.value) })} required /></label>
            <label>Price<input type="number" min="0" step="0.01" value={trade.price || ''} onChange={(e) => setTrade({ ...trade, price: Number(e.target.value) })} required /></label>
          </div>
          <label>Why are you making this trade? (optional)<textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. everyone’s talking about it" rows={2} /></label>
          <button className="optimize-button" type="submit" disabled={!!busy}>Check this trade</button>
        </form>
        {busy && <Loading text={busy} />}
        {problem && <p className="problem-line">{problem}</p>}
        {checked && (
          <div className="check-result">
            <h4>{checked.trade.action === 'buy' ? 'Buy' : 'Sell'} {checked.trade.shares} {checked.trade.ticker} at {checked.trade.price.toFixed(2)}</h4>
            <WarningCards found={checked.warnings} empty="No traps spotted for this trade." />
            <CoachCard tip={checked.tip} />
            <small className="muted-copy">These are reflection prompts, not blocks. You can record the trade after thinking it over.</small>
            <div className="warning-actions"><button onClick={() => setChecked(null)}>Discard</button><button onClick={record} disabled={!!busy}>{checked.warnings.length ? 'Record it anyway' : 'Record it'} <Icon name="chevron" size={15} /></button></div>
          </div>
        )}
      </div>
    </section>
  )
}

export default App
