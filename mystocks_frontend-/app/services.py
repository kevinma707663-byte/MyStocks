"""Thin, safe wrappers around the teammate's `core/` backend.
Rules: never edit core, never invent numbers. Every function returns real backend output
or raises the backend's own friendly ValueError, plus any soft warnings the backend raised."""
import json
import threading
import warnings

import streamlit as st

from core import (analysts as an, dcf, economy as eco, financials as fin, my_optimizer as mo,
                  my_risks as mr, my_stocks as ms, portfolio as pf, rivals as rv,
                  technicals as ta, verdict as vd, warnings_sidebar as ws)

TTL = 3600  # same as the backend's own 1-hour data memory


def _run(fn, *args, about=None, **kwargs):
    """Run a backend call, return (result, [soft warnings]).
    about=TICKER keeps only warnings that mention that ticker: Python's warning capture is global,
    so the background scoring thread's warnings about OTHER stocks can leak into this call."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = fn(*args, **kwargs)
    msgs = sorted({str(w.message) for w in caught})
    if about:
        msgs = [m for m in msgs if about.upper() in m.upper()]
    return out, msgs


def key(portfolio) -> str:
    return json.dumps(portfolio, sort_keys=True, default=str)


# Cached per portfolio content, so tab switches and reruns cost nothing.
@st.cache_data(ttl=TTL, show_spinner=False)
def positions(p):   return _run(ms.positions_table, p)
@st.cache_data(ttl=TTL, show_spinner=False)
def summary(p):     return _run(ms.portfolio_summary, p)
@st.cache_data(ttl=TTL, show_spinner=False)
def history(p, cur): return _run(ms.value_history, p, cur)
@st.cache_data(ttl=TTL, show_spinner=False)
def risks(p):       return _run(mr.portfolio_risks, p)
@st.cache_data(ttl=TTL, show_spinner=False)
def optimize(p, add, rules): return _run(mo.optimize_portfolio, p, add=list(add) or None, **dict(rules))
@st.cache_data(ttl=TTL, show_spinner=False)
def standing(p):    return _run(ws.standing_warnings, p)
@st.cache_data(ttl=TTL, show_spinner=False)
def technicals(t):  return _run(ta.technical_summary, t, about=t)
@st.cache_data(ttl=TTL, show_spinner=False)
def analysts(t):    return _run(an.analyst_summary, t, about=t)
@st.cache_data(ttl=TTL, show_spinner=False)
def dcf_for(t):     return _run(dcf.dcf_valuation, t, about=t)
@st.cache_data(ttl=TTL, show_spinner=False)
def rivals(t):      return _run(rv.compare_to_rivals, t, about=t)
@st.cache_data(ttl=TTL, show_spinner=False)
def ratios(t):      return _run(fin.ratios_table, t, about=t)
@st.cache_data(ttl=TTL, show_spinner=False)
def economy_for(t): return _run(eco.economy_effects, t, about=t)
@st.cache_data(ttl=TTL, show_spinner=False)
def verdict_one(t, with_rivals=False): return _run(vd.stock_verdict, t, include_rivals=with_rivals, about=t)


def check_trade(p, action, ticker, shares, price):
    return _run(ws.check_trade, p, action, ticker, shares, price)


# ---------------------------------------------------------------------------
# AI coach (backend: core/coach.py). It reads ANTHROPIC_API_KEY from the environment only,
# so on Streamlit Cloud we copy the key from st.secrets into the environment. Never hard-code it.
# ---------------------------------------------------------------------------
def ensure_api_key():
    import os
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        k = st.secrets["ANTHROPIC_API_KEY"]
    except Exception:            # no secrets file / no such key: the coach simply stays off
        return
    if k:
        os.environ["ANTHROPIC_API_KEY"] = str(k)


def coach_note(p, action, ticker, shares, price, reason, found, dates_known=True):
    """Ask the backend coach for a note. Never raises for coach problems (returns a status dict).
    A bad input (ValueError) still propagates so the form can show the backend's own message."""
    try:
        from core import coach            # imported here so a missing `anthropic` package can't crash the app
    except ImportError:
        return {"status": "unavailable", "note": None, "biases": [], "disclaimer": "",
                "why": "The AI coach isn't installed on this server (the 'anthropic' package is missing)."}
    ensure_api_key()
    facts_p = p
    if not dates_known:
        # Imported holdings carry today's date, so the coach would be told "you made N trades this month".
        # Not true, so for imported portfolios it gets the portfolio without that diary.
        facts_p = {**p, "trades": []}
    try:
        return coach.coach_note(facts_p, action, ticker, shares, price, reason=reason, found=found)
    except ValueError:
        raise
    except Exception as e:               # anything unexpected: the coach is optional, never block
        return {"status": "unavailable", "note": None, "biases": [], "disclaimer": "",
                "why": f"The AI coach hit a problem ({type(e).__name__}). The rule warnings above still apply."}


# ---------------------------------------------------------------------------
# Background verdicts: ONE worker thread (the backend's cache has no locks and
# warnings.catch_warnings is not thread-safe, so we don't run several at once).
# The thread only writes into a plain dict. It never touches Streamlit.
# ---------------------------------------------------------------------------
def start_verdicts(store: dict, tickers: list):
    """tickers should already be sorted biggest-first."""
    if store.get("running"):
        return
    store.update(running=True, done={}, errors={}, total=len(tickers))

    def work():
        for t in tickers:
            try:
                res = vd.stock_verdict(t, include_rivals=False)
                store["done"][t] = res
            except Exception as e:  # show a friendly line per stock, keep going
                store["errors"][t] = str(e)
        store["running"] = False

    threading.Thread(target=work, daemon=True).start()
