"""
Live edge-case run: every MyPortfolio section against awkward real-life cases.

Run it from the project folder (it needs the internet, and takes about 3 minutes):

    python tests/edge_cases.py

It prints one line per check:
    OK        the section gave a sensible answer
    FRIENDLY  it stopped with a clear, plain-English message (a ValueError)
    CRASH     anything else: a bug to fix

The cases: no portfolio, one stock, sold everything, a typo mixed in, only
typos, only funds, everything bought today, awkward single tickers, and bad
inputs to MyOptimizer and MyEdit.
"""
import sys, traceback, warnings
from datetime import date, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # find core/
warnings.simplefilter("ignore")
import pandas as pd
from core import (portfolio as pf, my_stocks as ms, my_risks as mr, my_optimizer as mo,
                  verdict as vd, warnings_sidebar as ws, financials as fin, rivals as rv,
                  economy as eco, technicals as ta, analysts as an, dcf)

results = []


def run(case, section, work):
    """Run one check. Records OK (with a short description), FRIENDLY (a clear ValueError), or CRASH."""
    try:
        out = work()
        results.append((case, section, "OK", describe(out)))
    except ValueError as e:
        results.append((case, section, "FRIENDLY", str(e)[:150]))
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)[-1]
        results.append((case, section, "CRASH", f"{type(e).__name__}: {str(e)[:110]} @ {tb.filename.split(chr(92))[-1]}:{tb.lineno}"))


def describe(out):
    if isinstance(out, pd.DataFrame):
        return f"table {out.shape[0]} rows x {out.shape[1]} cols"
    if isinstance(out, list):
        return f"{len(out)} warning(s)" + (f": {out[0]['trap']}" if out and isinstance(out[0], dict) and 'trap' in out[0] else "")
    if isinstance(out, dict):
        bits = []
        for key in ("score", "verdict", "level", "status", "message"):
            if key in out:
                value = out[key]
                bits.append(f"{key}={value:.0f}" if isinstance(value, float) else f"{key}={str(value)[:70]}")
        if "groups" in out:
            bits.append(f"groups={list(out['groups'])}, combined={out['combined']['value']:.0f}")
        if "table" in out:
            bits.append(f"table {len(out['table'])} rows")
        return ", ".join(bits) or f"dict with {list(out)[:5]}"
    if hasattr(out, "data") and hasattr(out, "layout"):
        return f"chart with {len(out.data)} trace(s)"
    return str(out)[:80]


def days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


def every_section(case, p):
    """Run every portfolio-level function on portfolio p."""
    run(case, "holdings_table", lambda: pf.holdings_table(p))
    run(case, "positions_table", lambda: ms.positions_table(p))
    run(case, "portfolio_summary", lambda: ms.portfolio_summary(p))
    run(case, "value_history USD", lambda: ms.value_history(p, "USD"))
    run(case, "allocation_chart", lambda: ms.allocation_chart(ms.positions_table(p)))
    run(case, "value_chart", lambda: ms.value_chart(ms.value_history(p, "USD"), "USD"))
    run(case, "portfolio_risks", lambda: mr.portfolio_risks(p))
    run(case, "optimize_portfolio", lambda: mo.optimize_portfolio(p))
    run(case, "optimize_portfolio + add", lambda: mo.optimize_portfolio(p, add=["KO", "MSFT"]))
    run(case, "portfolio_review", lambda: vd.portfolio_review(p, include_rivals=False))
    run(case, "standing_warnings", lambda: ws.standing_warnings(p))
    run(case, "check_trade buy KO", lambda: ws.check_trade(p, "buy", "KO", 5, 93))
    run(case, "check_trade sell AAPL", lambda: ws.check_trade(p, "sell", "AAPL", 1, 340))


# 1. No portfolio at all ---------------------------------------------------------
empty = pf.empty_portfolio()
every_section("1 empty portfolio", empty)
run("1 empty portfolio", "load_portfolio (no file)", lambda: pf.load_portfolio("data/does_not_exist.json"))
run("1 empty portfolio", "sell_holding", lambda: pf.sell_holding(pf.empty_portfolio(), "AAPL", 1, 100))
run("1 empty portfolio", "remove_holding row 0", lambda: pf.remove_holding(pf.empty_portfolio(), 0))
run("1 empty portfolio", "trade sell AAPL", lambda: ws.trade(pf.empty_portfolio(), "sell", "AAPL", 1, 340))

# 2. One stock only --------------------------------------------------------------
one = pf.empty_portfolio(); pf.add_holding(one, "AAPL", 10, 150, "2024-01-15")
every_section("2 one stock", one)

# 3. Sold everything (trade diary but no holdings) --------------------------------
sold = pf.empty_portfolio(); pf.add_holding(sold, "AAPL", 10, 150, "2024-01-15"); pf.sell_holding(sold, "AAPL", 10, 300, days_ago(5))
every_section("3 sold everything", sold)

# 4. A mistyped ticker mixed in ----------------------------------------------------
typo = pf.empty_portfolio(); pf.add_holding(typo, "AAPL", 10, 150, "2024-01-15"); pf.add_holding(typo, "ZZZZFAKE", 5, 50, "2025-01-15")
every_section("4 typo ticker mixed in", typo)

# 5. Only mistyped tickers ----------------------------------------------------------
allbad = pf.empty_portfolio(); pf.add_holding(allbad, "ZZZZFAKE", 5, 50, "2025-01-15"); pf.add_holding(allbad, "QQQQNOPE", 2, 10, "2025-02-01")
every_section("5 only typo tickers", allbad)

# 6. Only funds -------------------------------------------------------------------------
funds = pf.empty_portfolio(); pf.add_holding(funds, "SPY", 5, 500, "2024-03-01"); pf.add_holding(funds, "ZLB.TO", 100, 50, "2024-03-01")
every_section("6 only funds", funds)

# 7. Bought today (no history yet) ---------------------------------------------------------
today = pf.empty_portfolio(); pf.add_holding(today, "AAPL", 10, 340); pf.add_holding(today, "RY.TO", 10, 280)
every_section("7 everything bought today", today)

# 8. Single-stock analysis on awkward tickers ------------------------------------------------
for t in ["ZZZZFAKE", "SPY", "BRK-B", "RIVN", "SKHY", "aapl ", ""]:
    case = f"8 ticker {t!r}"
    run(case, "ratios_table", lambda: fin.ratios_table(t))
    run(case, "compare_to_rivals", lambda: rv.compare_to_rivals(t))
    run(case, "economy_effects", lambda: eco.economy_effects(t))
    run(case, "technical_summary", lambda: ta.technical_summary(t))
    run(case, "analyst_summary", lambda: an.analyst_summary(t))
    run(case, "dcf_valuation", lambda: dcf.dcf_valuation(t))
    run(case, "stock_verdict", lambda: vd.stock_verdict(t, include_rivals=False))
    run(case, "mix_risks", lambda: mr.mix_risks({t: 50, "KO": 50}))

# 9. Bad inputs to the optimizer and MyEdit ---------------------------------------------------------
base = mo.optimize(["AAPL", "KO", "RY.TO"], max_weight_pct=50)
run("9 optimizer inputs", "my_edit on a good result", lambda: mo.my_edit(base, {"KO": 20}))
run("9 optimizer inputs", "optimize with duplicates", lambda: mo.optimize(["aapl", "AAPL", "KO", "ko"], max_weight_pct=60))
run("9 optimizer inputs", "optimize 2 stocks, 30% cap", lambda: mo.optimize(["AAPL", "KO"]))
run("9 optimizer inputs", "optimize with a typo", lambda: mo.optimize(["AAPL", "KO", "ZZZZFAKE"], max_weight_pct=60))
run("9 optimizer inputs", "my_edit weights as text", lambda: mo.my_edit(base, {"KO": "twenty"}))

# 10. New checks for the fixes ------------------------------------------------------------------
run("10 fixes", "mix_risks all typos", lambda: mr.mix_risks({"ZZZZFAKE": 100}))
run("10 fixes", "mix_risks ko typed twice", lambda: mr.mix_risks({"ko": 50, "KO ": 50}))
run("10 fixes", "mix_risks weight as text", lambda: mr.mix_risks({"KO": "forty", "AAPL": 60}))
run("10 fixes", "mix_risks empty mix", lambda: mr.mix_risks({}))
run("10 fixes", "my_edit weight None", lambda: mo.my_edit(base, {"KO": None}))
run("10 fixes", "check_trade shares as text", lambda: ws.check_trade(one, "buy", "KO", "ten", 93))
run("10 fixes", "check_trade buy a typo", lambda: ws.check_trade(one, "buy", "ZZZZFAKE", 5, 10))
run("10 fixes", "empty + add, 60% cap", lambda: mo.optimize_portfolio(empty, add=["KO", "MSFT"], max_weight_pct=60))
run("10 fixes", "summary typo mixed in", lambda: {k: round(v, 1) for k, v in ms.portfolio_summary(typo)["groups"]["USD"].items()})
run("10 fixes", "summary only typos", lambda: {k: round(v, 1) for k, v in ms.portfolio_summary(allbad)["groups"]["USD"].items()})
run("10 fixes", "sidebar only typos", lambda: [w["message"] for w in ws.standing_warnings(allbad)])

pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 150); pd.set_option("display.max_rows", 500)
table = pd.DataFrame(results, columns=["case", "section", "outcome", "detail"])
print(table.to_string(index=False))
print()
print(table["outcome"].value_counts().to_string())
