"""
main.py - the web server the React screens talk to.

HOW TO RUN IT (from the project folder)
    .venv/bin/uvicorn api.main:app --reload --port 8000
    Then start the screens in web/ (see web/README.md).

HOW IT WORKS
    Every address takes the visitor's portfolio in the request and hands
    back plain JSON. The server never saves anyone's portfolio: the browser
    keeps it. That's the same rule the Streamlit app followed, because a
    hosted app's file would be shared by every visitor.

    The only thing the server remembers is MyOptimizer's results, for an
    hour, so MyEdit can replay an edit over exactly the same days.

HOW PROBLEMS ARE REPORTED
    A plain-English ValueError from core/ comes back as status 400 with
    {"detail": "the message"}, so the screen can show it as it is.
    Soft warnings (like "No price data for ZZZZ") come back in a
    "notes" list next to the answer.
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

import io
import json
import math
import threading
import time
import uuid
import warnings
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core import analysts as an
from core import dcf
from core import financials as fin
from core import my_optimizer as mo
from core import my_risks as mr
from core import my_stocks as ms
from core import portfolio as pf
from core import rivals as rv
from core import technicals as ta
from core import verdict as vd
from core import warnings_sidebar as ws


# ===========================================================================
# SETTINGS
# ===========================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_FILE = PROJECT_ROOT / "practice" / "OpenPosition_10_24_2026.csv"

# The columns a broker positions file must have.
# The Streamlit template's columns. Older broker files say "Symbol" instead of "Ticker"; both work.
BROKER_COLUMNS = ["Ticker", "Quantity", "Currency", "PricePaid"]

# These warnings need real buy dates. After a broker import every date is
# "today", so they would be false alarms, and they're left out.
DATE_DEPENDENT = {"Overtrading", "Holding a loser", "Quick flip"}

MAX_CHART_POINTS = 260        # charts get at most this many points (about a year of days)
OPTIMIZER_MEMORY = 50         # optimizer results kept for MyEdit
OPTIMIZER_SECONDS = 60 * 60   # ...for one hour

# A public app shares one Anthropic key, so each visitor (by internet
# address) gets this many coach notes a day.
COACH_NOTES_PER_DAY = 10

# core/ keeps its data memory in a plain dictionary, and Python's warning
# catcher is shared by the whole program. Neither is safe with two requests
# at once, so core/ is called by one request at a time.
CORE_LOCK = threading.Lock()

app = FastAPI(title="MyPortfolio API")


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def plain(value):
    """Turn core/'s answers (tables, numpy numbers, dates) into plain JSON.

    Blank numbers (NaN) and infinity become null, which JSON understands.
    """
    if isinstance(value, pd.DataFrame):
        return [plain(row) for row in value.to_dict("records")]
    if isinstance(value, pd.Series):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [plain(v) for v in value]
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.date().isoformat() if isinstance(value, (pd.Timestamp, datetime)) else value.isoformat()
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    return value


def table(frame: pd.DataFrame, index_name: str) -> list:
    """A table as a list of rows, with its row labels kept as `index_name`."""
    return plain(frame.rename_axis(index_name).reset_index())


def thin(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep at most MAX_CHART_POINTS rows, evenly spaced, always keeping the last."""
    if len(frame) <= MAX_CHART_POINTS:
        return frame
    step = math.ceil(len(frame) / MAX_CHART_POINTS)
    keep = list(range(0, len(frame), step))
    if keep[-1] != len(frame) - 1:
        keep.append(len(frame) - 1)
    return frame.iloc[keep]


def grid(frame: pd.DataFrame, index_name: str) -> dict:
    """A table with its columns kept in order: {"columns": [...], "rows": [[...], ...]}.

    For tables whose columns vary (one per business year, one per growth
    rate), so the screen can show them as they come.
    """
    frame = frame.rename_axis(index_name).reset_index()
    return {"columns": [str(c) for c in frame.columns], "rows": plain(frame.values.tolist())}


def series_chart(frame: pd.DataFrame) -> dict:
    """A table of lines (one column per line) as {"dates": [...], "lines": {name: [...]}}."""
    frame = thin(frame)
    return {"dates": [d.date().isoformat() for d in frame.index],
            "lines": {str(c): plain(list(frame[c])) for c in frame.columns}}


def charts(report: dict, makers: dict) -> dict:
    """core/'s own Plotly charts as JSON, the same ones the Streamlit app showed.

    makers  {name: chart function}. A chart that can't be drawn is left out,
            so one bad chart never sinks the rest of the answer.
    """
    drawn = {}
    for name, make in makers.items():
        try:
            drawn[name] = json.loads(make(report).to_json())
        except Exception:
            pass
    return drawn


def run(fn, *args, **kwargs):
    """Call one core/ function, one request at a time. Returns (answer, soft warnings)."""
    with CORE_LOCK, warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        answer = fn(*args, **kwargs)
    # yfinance and pandas also warn about their own internals: keep only core's.
    notes = sorted({str(w.message) for w in caught if w.category is UserWarning})
    return answer, notes


def skip_date_warnings(found: list, dates_known: bool) -> list:
    """Leave out the warnings that need real buy dates, when there are none."""
    return found if dates_known else [w for w in found if w["trap"] not in DATE_DEPENDENT]


def to_yahoo(symbol: str, currency: str) -> str:
    """Broker symbol -> Yahoo ticker: "QBR.B" + CAD -> "QBR-B.TO", "NVDA" + USD -> "NVDA"."""
    symbol = str(symbol).strip().upper()
    if str(currency).strip().upper() != "CAD" or symbol.endswith(ms.CANADIAN_ENDINGS):
        return symbol
    return symbol.replace(".", "-") + ".TO"


def read_broker_file(source) -> dict:
    """A broker positions file -> {"portfolio", "problems"}. Rows that can't be read are listed, not hidden."""
    try:
        # utf-8-sig: Excel's "CSV UTF-8" files start with an invisible mark that would spoil the first column name.
        broker = pd.read_csv(source, thousands=",", encoding="utf-8-sig")
    except Exception:
        raise ValueError("That file couldn't be read. Upload the positions file as a .csv.") from None
    broker.columns = [str(c).strip() for c in broker.columns]
    if "Ticker" not in broker.columns and "Symbol" in broker.columns:
        broker = broker.rename(columns={"Symbol": "Ticker"})
    missing = [c for c in BROKER_COLUMNS if c not in broker.columns]
    if missing:
        raise ValueError("This doesn't look like a supported file. Missing columns: " + ", ".join(missing)
                         + ". Use the template: Ticker, Quantity, Currency, PricePaid.")

    portfolio, problems = pf.empty_portfolio(), []
    for i, row in broker.iterrows():
        ticker = "" if pd.isna(row["Ticker"]) else str(row["Ticker"]).strip()
        try:
            if not ticker:
                raise ValueError("Ticker is empty")
            pf.add_holding(portfolio, to_yahoo(ticker, row["Currency"]), float(row["Quantity"]), float(row["PricePaid"]))
        except (ValueError, TypeError) as error:
            problems.append(f"Row {i + 2} ({ticker or '?'}): {error}")
    if not portfolio["holdings"]:
        raise ValueError("No holdings could be read from that file.")
    return {"portfolio": portfolio, "problems": problems}


# ===========================================================================
# HOW PROBLEMS COME BACK
# ===========================================================================

@app.exception_handler(ValueError)
def plain_english_problem(request: Request, error: ValueError):
    # core/'s own friendly messages, shown on screen as they are.
    return JSONResponse(status_code=400, content={"detail": str(error)})


@app.exception_handler(Exception)
def unexpected_problem(request: Request, error: Exception):
    return JSONResponse(status_code=502, content={
        "detail": "Couldn't load this right now. Market data providers sometimes rate-limit or time out. "
                  "Try again in a minute.",
        "technical": f"{type(error).__name__}: {error}",
    })


# ===========================================================================
# WHAT THE SCREENS SEND
# ===========================================================================

class WithPortfolio(BaseModel):
    portfolio: dict


class NewHolding(WithPortfolio):
    ticker: str
    shares: float
    price: float
    buy_date: str | None = None       # "2024-01-15", or leave out for today
    market: str = "US"                # "CA" adds .TO to Canadian tickers


class HistoryAsk(WithPortfolio):
    currency: str


class OptimizeAsk(WithPortfolio):
    add: list[str] = []
    goal: str = mo.GOAL
    max_drawdown_pct: float = mo.MAX_DRAWDOWN_PCT
    min_return_pct: float = mo.MIN_RETURN_PCT
    max_weight_pct: float = mo.MAX_WEIGHT_PCT
    min_weight_pct: float = mo.MIN_WEIGHT_PCT


class EditAsk(BaseModel):
    result_id: str
    changes: dict[str, float]         # {ticker: % of your money}


class StandingAsk(WithPortfolio):
    dates_known: bool = True


class TradeAsk(WithPortfolio):
    action: str
    ticker: str
    shares: float
    price: float
    reason: str = ""
    dates_known: bool = True
    coach: bool = True                # also ask the AI coach for a note


# ===========================================================================
# THE PORTFOLIO
# ===========================================================================

@app.get("/api/portfolio/sample")
def sample_portfolio():
    """The test portfolio from the broker file in practice/."""
    return read_broker_file(SAMPLE_FILE)


@app.post("/api/portfolio/import")
async def import_portfolio(file: UploadFile = File(...)):
    """A broker positions file uploaded from the screen."""
    return read_broker_file(io.BytesIO(await file.read()))


@app.post("/api/portfolio/add")
def add_holding(ask: NewHolding):
    ticker = to_yahoo(ask.ticker, "CAD" if ask.market.upper() == "CA" else "USD")
    portfolio = pf.add_holding(ask.portfolio, ticker, ask.shares, ask.price, ask.buy_date or None)
    return {"portfolio": portfolio}


# ===========================================================================
# MYSTOCKS
# ===========================================================================

@app.post("/api/overview")
def overview(ask: WithPortfolio):
    """One row per stock, plus the headline numbers per currency group."""
    positions, notes = run(ms.positions_table, ask.portfolio)
    summary, more = run(ms.portfolio_summary, ask.portfolio)
    return {"positions": plain(positions), "summary": plain(summary), "notes": sorted(set(notes + more))}


@app.post("/api/history")
def history(ask: HistoryAsk):
    """You vs your S&P 500 twin, day by day, for one currency group."""
    frame, notes = run(ms.value_history, ask.portfolio, ask.currency)
    return {"currency": ask.currency.upper(), **series_chart(frame), "notes": notes}


# ===========================================================================
# MYRISKS
# ===========================================================================

@app.post("/api/risks")
def risks(ask: WithPortfolio):
    report, notes = run(mr.portfolio_risks, ask.portfolio)
    correlation = report["correlation"]
    return {
        **plain({k: report[k] for k in ("score", "level", "top_risks", "left_out", "value", "home_currency",
                                        "period", "weights", "sectors", "currencies", "beta", "stress",
                                        "stock_drops", "bad_day")}),
        "areas": table(report["areas"], "area"),
        "risk_shares": table(report["risk_shares"], "ticker"),
        "correlation": {"tickers": list(correlation.columns), "values": plain(correlation.values.tolist())},
        "underwater": series_chart(report["underwater"].to_frame("below_high_pct")),
        # The worst fall, from every day (the chart above is thinned, so it can miss the bottom).
        "worst_fall_pct": abs(float(report["underwater"].min())) if len(report["underwater"]) else None,
        "charts": charts(report, {"sectors": mr.sector_chart, "correlation": mr.correlation_chart,
                                  "risk_share": mr.risk_share_chart, "drawdown": mr.drawdown_chart}),
        "notes": notes,
    }


# ===========================================================================
# MYOPTIMIZER AND MYEDIT
# ===========================================================================

# {result id: (time saved, the full result)}. Oldest first.
_optimizer_results: OrderedDict = OrderedDict()


def _remember_result(result: dict) -> str:
    now = time.time()
    for key in [k for k, (saved, _) in _optimizer_results.items() if now - saved > OPTIMIZER_SECONDS]:
        del _optimizer_results[key]
    while len(_optimizer_results) >= OPTIMIZER_MEMORY:
        _optimizer_results.popitem(last=False)
    result_id = uuid.uuid4().hex
    _optimizer_results[result_id] = (now, result)
    return result_id


def _optimizer_answer(result: dict, result_id: str, notes: list) -> dict:
    return {
        "result_id": result_id,
        **plain({k: result.get(k) for k in ("status", "message", "tickers", "goal", "rules", "period",
                                            "risk_free_pct", "best_weights", "current_weights", "limits")}),
        "edit_weights": plain(result.get("edit_weights")),
        "breaks": result.get("breaks", []),
        "comparison": table(result["comparison"], "mix"),
        "weights": table(result["weights"], "ticker"),
        "growth": series_chart(result["growth"]),
        "charts": charts(result, {"weights": mo.weights_chart, "growth": mo.growth_chart, "cloud": mo.cloud_chart}),
        "notes": notes,
    }


@app.post("/api/optimize")
def optimize(ask: OptimizeAsk):
    rules = {"goal": ask.goal, "max_drawdown_pct": ask.max_drawdown_pct, "min_return_pct": ask.min_return_pct,
             "max_weight_pct": ask.max_weight_pct, "min_weight_pct": ask.min_weight_pct}
    result, notes = run(mo.optimize_portfolio, ask.portfolio, add=ask.add or None, **rules)
    return _optimizer_answer(result, _remember_result(result), notes)


@app.post("/api/edit")
def edit(ask: EditAsk):
    """MyEdit, always starting from the optimizer's own result, so the screen sends every stock it set."""
    saved = _optimizer_results.get(ask.result_id)
    if saved is None:
        raise ValueError("That optimizer result has expired. Run the optimizer again, then edit.")
    result, notes = run(mo.my_edit, saved[1], ask.changes)
    return _optimizer_answer(result, ask.result_id, notes)


# ===========================================================================
# MYANALYSIS
# ===========================================================================

@app.get("/api/verdict/{ticker}")
def verdict(ticker: str, rivals: bool = False):
    """The final verdict on one stock. rivals=true adds the slow rivals part (15 to 30 seconds)."""
    result, notes = run(vd.stock_verdict, ticker, include_rivals=rivals)
    return {
        **plain({k: result[k] for k in ("company", "name", "score", "verdict", "momentum", "strengths", "concerns")}),
        "parts": table(result["parts"], "part"),
        "health_checks": table(result["health_checks"], "check"),
        "notes": [n for n in notes if result["company"] in n],
    }


# --- The five tabs under a stock's verdict (the Streamlit app's detail tabs) ---
# Each one runs only when its tab is opened. A ValueError (no statements for a
# fund, negative cash for a DCF) comes back as the usual plain-English 400.

def _for_this_stock(notes: list, ticker: str) -> list:
    return [n for n in notes if ticker.upper() in n.upper()]


@app.get("/api/stock/{ticker}/technicals")
def stock_technicals(ticker: str):
    s, notes = run(ta.technical_summary, ticker)
    return {
        **plain({k: s[k] for k in ("company", "price", "as_of", "score", "verdict", "setup")}),
        "signals": grid(s["signals"], "signal"),
        "charts": charts(s, {"chart": ta.technical_chart}),
        "notes": _for_this_stock(notes, ticker),
    }


@app.get("/api/stock/{ticker}/analysts")
def stock_analysts(ticker: str):
    s, notes = run(an.analyst_summary, ticker)
    return {
        **plain({k: s[k] for k in ("company", "verdict", "score", "momentum_score", "target_currency_note", "targets")}),
        "signals": grid(s["signals"], "signal"),
        "charts": charts(s, {"targets": an.targets_chart}),
        "notes": _for_this_stock(notes, ticker),
    }


@app.get("/api/stock/{ticker}/dcf")
def stock_dcf(ticker: str):
    r, notes = run(dcf.dcf_valuation, ticker)
    return {
        **plain({k: r[k] for k in ("company", "method", "currency", "price", "value_per_share", "upside_pct",
                                   "verdict", "score", "notes")}),
        "assumptions": grid(r["assumptions"], "assumption"),
        "sensitivity": grid(r["sensitivity"], "discount rate"),
        "charts": charts(r, {"bridge": dcf.bridge_chart}),
        "notes_soft": _for_this_stock(notes, ticker),
    }


@app.get("/api/stock/{ticker}/ratios")
def stock_ratios(ticker: str):
    ratios, notes = run(fin.ratios_table, ticker)
    # Readable text like "26.9%" and "34.1x", one row per ratio, as the Streamlit app showed it.
    shown = fin.format_ratios(ratios) if len(ratios) else pd.DataFrame()
    return {"ratios": grid(shown, "ratio") if len(shown) else None, "notes": _for_this_stock(notes, ticker)}


@app.get("/api/stock/{ticker}/rivals")
def stock_rivals(ticker: str):
    r, notes = run(rv.compare_to_rivals, ticker)
    return {
        "company": r["company"],
        "rivals": r["rivals"],
        "scores": grid(r["scores"], "quality"),
        "charts": charts(r, {"scores": lambda result: rv.scores_chart(result["scores"], result["company"])}),
        "notes": _for_this_stock(notes, ticker),
    }


# ===========================================================================
# THE WARNINGS SIDEBAR AND THE AI COACH
# ===========================================================================

_coach_notes_used: dict = {}       # {internet address: (day, notes used)}


def _coach_allowed(address: str) -> bool:
    today = date.today().isoformat()
    day, used = _coach_notes_used.get(address, (today, 0))
    if day != today:
        used = 0
    if used >= COACH_NOTES_PER_DAY:
        return False
    _coach_notes_used[address] = (today, used + 1)
    return True


@app.post("/api/warnings/standing")
def standing(ask: StandingAsk):
    found, notes = run(ws.standing_warnings, ask.portfolio)
    return {"warnings": skip_date_warnings(found, ask.dates_known), "notes": notes}


@app.post("/api/trade/check")
def check_trade(ask: TradeAsk, request: Request):
    """The rule warnings for one trade, plus the AI coach's note. Nothing is recorded."""
    found, notes = run(ws.check_trade, ask.portfolio, ask.action, ask.ticker, ask.shares, ask.price)
    found = skip_date_warnings(found, ask.dates_known)

    tip = None
    if ask.coach:
        address = request.client.host if request.client else "unknown"
        if not _coach_allowed(address):
            tip = {"status": "off", "note": None, "biases": [], "disclaimer": "",
                   "why": f"You've used all {COACH_NOTES_PER_DAY} coach notes for today."}
        else:
            from core import coach     # here, so a missing "anthropic" package can't stop the server
            # Imported holdings are all dated today, so the coach would be told
            # "you made 15 trades this month". It gets no diary for those.
            facts_portfolio = ask.portfolio if ask.dates_known else {**ask.portfolio, "trades": []}
            tip, _ = run(coach.coach_note, facts_portfolio, ask.action, ask.ticker, ask.shares, ask.price,
                         reason=ask.reason, found=found)
    return {"warnings": found, "tip": plain(tip), "notes": notes}


@app.post("/api/trade/record")
def record_trade(ask: TradeAsk):
    """Record the trade. The warnings never stop it; real mistakes (selling more than you own) still do."""
    (portfolio, _found), _notes = run(ws.trade, ask.portfolio, ask.action, ask.ticker, ask.shares, ask.price)
    return {"portfolio": portfolio}
