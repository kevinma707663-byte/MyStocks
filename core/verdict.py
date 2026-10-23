"""
verdict.py - MyAnalysis Part 3G: "So what should I do?"

WHAT THIS FILE DOES
    Runs every MyAnalysis part (3A to 3F) on one stock, turns each into a
    score from 0 to 100, and blends them into ONE overall score and a
    plain-English suggestion, with the reasons behind it. It can also
    review every stock you own and flag the ones worth a closer look.

THE SIX PART SCORES, AND THEIR STARTING WEIGHTS
    Business health  20%   3A: how many basic health checks it passes
    Versus rivals    15%   3B: the average of its four quality scores
    Value            15%   3F: how far the DCF value is from today's price
    Economy          10%   3C: headwinds and tailwinds
    Price chart      20%   3D: the technical score
    Analysts         20%   3E: the analyst score, including analyst momentum

    You can change any weight. If a part can't run (a fund has no DCF,
    a small company has no analysts), it's skipped and the other weights
    grow to fill the gap.

THE SUGGESTION
    65 or more   "looks strong"
    50 to 65     "hold"
    35 to 50     "look closer"
    below 35     "consider trimming"

MOMENTUM
    Shown on its own line: price momentum from 3D (returns vs the
    S&P 500) next to analyst momentum from 3E (forecasts and ratings
    moving up or down), averaged together.

STRENGTHS AND CONCERNS
    Strengths come from the highest-scoring parts, concerns from the
    lowest-scoring ones, so the reasons point at what drove the verdict.

THIS IS A RULE OF THUMB, NOT FINANCIAL ADVICE
    It blends simple measures of past data. Use it to decide what to look
    into, not what to buy or sell.

THE FUNCTIONS OTHER FILES USE
    stock_verdict(ticker)             -> the overall score, suggestion, reasons, every part
    portfolio_review(portfolio)       -> one row per stock you own, flagged if worth a look
    verdict_chart(result)             -> bar chart of the six part scores
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# warnings: we hide the parts' own warnings here, because each part
# already shows them in its own section.
import warnings

# numpy: math helpers. np.nan means "blank / not a number".
import numpy as np

# pandas: the library for tables of numbers.
import pandas as pd

# plotly.express: quick, interactive charts.
import plotly.express as px

# Our own files. The dot means "from this same core/ folder".
from . import data
from . import financials as fin
from . import rivals as rv
from . import economy as eco
from . import technicals as ta
from . import analysts as an
from . import dcf
from . import portfolio as pf


# ===========================================================================
# SETTINGS
# ===========================================================================

# Starting weights, in %. They don't have to add up to 100: they're
# scaled so the parts that actually ran add up to 100.
WEIGHTS = {
    "Business health": 20,
    "Versus rivals": 15,
    "Value": 15,
    "Economy": 10,
    "Price chart": 20,
    "Analysts": 20,
}

# The suggestion for each overall score.
STRONG = 65
HOLD = 50
LOOK_CLOSER = 35

# At least this many parts must run for an overall score to mean anything.
MIN_PARTS = 2

# Health check thresholds (Part 3A numbers).
MIN_ROIC_PCT = 10             # return on invested capital, most companies
MIN_BANK_ROE_PCT = 10         # return on equity, banks and insurers
MIN_BANK_ROA_PCT = 0.8        # return on assets, banks and insurers
MAX_DEBT_TO_EQUITY = 1.5
MIN_CURRENT_RATIO = 1.0
MIN_INTEREST_COVER = 3.0
MIN_CASH_CONVERSION = 0.8


# ===========================================================================
# PART 3A AS A SCORE: THE HEALTH CHECKS
# ===========================================================================

def health_checks(ratios: pd.DataFrame, financial: bool) -> pd.DataFrame:
    """Basic yes/no health checks from a ratios_table(...).

    Returns a table with one row per check: result ("pass", "fail" or
    "skip" when the number isn't available) and the number behind it.
    Banks and insurers get checks that make sense for them.
    """
    def latest(key):
        return fin.latest(ratios, key)

    def check(name, value, passed, detail):
        if pd.isna(value):
            return {"check": name, "result": "skip", "detail": "no data"}
        return {"check": name, "result": "pass" if passed else "fail", "detail": detail}

    margin = latest("net_margin_pct")
    growth = latest("revenue_growth_pct")
    margin_trend = ratios.loc["net_margin_pct", "trend"]

    rows = [
        check("Profitable", margin, margin > 0, f"net margin {margin:.1f}%"),
        check("Sales growing", growth, growth > 0, f"revenue growth {growth:+.1f}%"),
        {"check": "Margins not shrinking",
         "result": "skip" if margin_trend == "n/a" else ("fail" if margin_trend == "worsening" else "pass"),
         "detail": f"net margin trend: {margin_trend}"},
    ]

    if financial:
        roe, roa, eps_growth = latest("roe_pct"), latest("roa_pct"), latest("eps_growth_pct")
        rows += [
            check("Strong return on equity", roe, roe >= MIN_BANK_ROE_PCT, f"{roe:.1f}% (bank benchmark {MIN_BANK_ROE_PCT}%)"),
            check("Strong return on assets", roa, roa >= MIN_BANK_ROA_PCT, f"{roa:.2f}% (bank benchmark {MIN_BANK_ROA_PCT}%)"),
            check("Earnings per share growing", eps_growth, eps_growth > 0, f"EPS growth {eps_growth:+.1f}%"),
        ]
    else:
        roic, debt = latest("roic_pct"), latest("debt_to_equity")
        current, cover = latest("current_ratio"), latest("interest_coverage")
        fcf, conversion = latest("free_cash_flow"), latest("cash_conversion")
        rows += [
            check("Strong return on invested capital", roic, roic >= MIN_ROIC_PCT, f"{roic:.1f}% (benchmark {MIN_ROIC_PCT}%)"),
            check("Manageable debt", debt, debt <= MAX_DEBT_TO_EQUITY, f"debt / equity {debt:.2f} (limit {MAX_DEBT_TO_EQUITY})"),
            check("Can pay this year's bills", current, current >= MIN_CURRENT_RATIO, f"current ratio {current:.2f}"),
            check("Profit covers interest", cover, cover >= MIN_INTEREST_COVER, f"interest coverage {cover:.1f}x"),
            check("Makes real cash", fcf, fcf > 0, f"free cash flow {fin.format_money(fcf)}"),
            check("Profit turns into cash", conversion, conversion >= MIN_CASH_CONVERSION, f"cash conversion {conversion:.2f}"),
        ]

    return pd.DataFrame(rows).set_index("check")


def _health_score(checks: pd.DataFrame) -> float:
    """Share of checks passed, in %, leaving out the skipped ones."""
    counted = checks[checks["result"] != "skip"]
    if counted.empty:
        return np.nan
    return float((counted["result"] == "pass").mean() * 100)


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _suggestion(score: float) -> str:
    """Turn the overall score into a suggestion."""
    if pd.isna(score):
        return "not enough data"
    if score >= STRONG:
        return "looks strong"
    if score >= HOLD:
        return "hold"
    if score >= LOOK_CLOSER:
        return "look closer"
    return "consider trimming"


def _price_momentum_pct(momentum: pd.DataFrame) -> float:
    """Price momentum from Part 3D as 0 to 100: the share of checks passed."""
    known = momentum.dropna(subset=["stock_pct"])
    if known.empty:
        return np.nan
    passed = (known["stock_pct"] > 0).sum() + (known["difference"] > 0).sum()
    return float(passed / (2 * len(known)) * 100)


def _run(part_name: str, work):
    """Run one part, hiding its warnings. Returns (result, problem)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return work(), ""
    except Exception as error:
        return None, f"{part_name} couldn't run: {error}"


# ===========================================================================
# THE MAIN FUNCTION
# ===========================================================================

def stock_verdict(ticker: str, weights: dict = None, include_rivals: bool = True) -> dict:
    """The final verdict on one stock.

    ticker          like "NVDA" or "RY.TO"
    weights         optional, like {"Value": 30, "Economy": 0}. Any part
                    you leave out keeps its starting weight. 0 turns a part off.
    include_rivals  False skips the rivals part, which is the slow one
                    (15 to 30 seconds the first time). Handy for big portfolios.

    Returns a dictionary:
        {
          "company", "name",
          "score":       the overall score, 0 to 100
          "verdict":     "looks strong", "hold", "look closer",
                         "consider trimming" or "not enough data"
          "momentum":    price momentum, analyst momentum, the two averaged,
                         and a one-word reading
          "parts":       table with one row per part: score, weight used,
                         a short summary, and why it was skipped if it was
          "strengths":   up to 3 plain-English strengths
          "concerns":    up to 3 plain-English concerns
          "health_checks": the Part 3A checks behind the business health score
          "details":     each part's full result, so a screen can show more
                         without running it again
        }
    """
    ticker = data.clean_tickers(ticker)[0]
    info = data.get_info(ticker)
    financial = (info["industry"] or "").startswith(fin.FINANCIAL_INDUSTRIES)
    weights = {**WEIGHTS, **(weights or {})}
    if not include_rivals:
        weights["Versus rivals"] = 0

    scores, summaries, problems = {}, {}, {}
    strengths, concerns = {}, {}     # part name -> list of reasons
    details = {}

    # --- 3A: business health ---------------------------------------------------
    ratios, problem = _run("Business health", lambda: fin.ratios_table(ticker))
    checks = pd.DataFrame(columns=["result", "detail"])
    if ratios is not None and not ratios.empty:
        checks = health_checks(ratios, financial)
        scores["Business health"] = _health_score(checks)
        passed = (checks["result"] == "pass").sum()
        counted = (checks["result"] != "skip").sum()
        summaries["Business health"] = f"passes {passed} of {counted} health checks"
        strengths["Business health"] = [f"{name}: {row['detail']}." for name, row in checks.iterrows() if row["result"] == "pass"]
        concerns["Business health"] = [f"{name} check failed: {row['detail']}." for name, row in checks.iterrows() if row["result"] == "fail"]
        details["ratios"] = ratios
    else:
        problems["Business health"] = problem or "no financial statements (funds and ETFs don't have them)"

    # --- 3B: versus rivals -------------------------------------------------------
    if weights["Versus rivals"] > 0:
        result, problem = _run("Versus rivals", lambda: rv.compare_to_rivals(ticker))
        if result is not None:
            quality = result["scores"]["score"].dropna()
            if len(quality):
                scores["Versus rivals"] = float(quality.mean())
                summaries["Versus rivals"] = f"average of {len(quality)} quality scores vs {len(result['rivals'])} rivals"
                strengths["Versus rivals"] = [f"{q} is strong against rivals ({s:.0f}/100)." for q, s in quality.items() if s >= 67]
                concerns["Versus rivals"] = [f"{q} is weak against rivals ({s:.0f}/100)." for q, s in quality.items() if s < 34]
            details["rivals"] = result
        else:
            problems["Versus rivals"] = problem
    else:
        problems["Versus rivals"] = "turned off"

    # --- 3F: value -----------------------------------------------------------------
    result, problem = _run("Value", lambda: dcf.dcf_valuation(ticker))
    if result is not None:
        scores["Value"] = result["score"]
        summaries["Value"] = f"{result['verdict']}: DCF value {result['value_per_share']:.2f} vs price {result['price']:.2f}"
        gap = f"DCF value {result['value_per_share']:.2f} is {abs(result['upside_pct']):.0f}% {'above' if result['upside_pct'] > 0 else 'below'} today's price."
        if result["verdict"] == "undervalued":
            strengths["Value"] = [f"Looks undervalued: {gap}"]
        elif result["verdict"] == "overvalued":
            concerns["Value"] = [f"Looks overvalued: {gap}"]
        details["dcf"] = result
    else:
        problems["Value"] = problem

    # --- 3C: economy -------------------------------------------------------------
    result, problem = _run("Economy", lambda: eco.economy_effects(ticker))
    if result is not None:
        scores["Economy"] = result["score"]
        summaries["Economy"] = f"economy is {result['verdict']} for this stock"
        effects = result["effects"]
        strengths["Economy"] = [f"Economy tailwind from {t.lower()}: {row['why']}" for t, row in effects.iterrows() if row["verdict"] == "tailwind"]
        concerns["Economy"] = [f"Economy headwind from {t.lower()}: {row['why']}" for t, row in effects.iterrows() if row["verdict"] == "headwind"]
        details["economy"] = result
    else:
        problems["Economy"] = problem

    # --- 3D: price chart -----------------------------------------------------------
    tech, problem = _run("Price chart", lambda: ta.technical_summary(ticker))
    if tech is not None:
        scores["Price chart"] = tech["score"]
        summaries["Price chart"] = f"technical signals are {tech['verdict']}"
        signals = tech["signals"]
        strengths["Price chart"] = [f"{s} (price chart): {row['reading']}." for s, row in signals.iterrows() if row["points"] > 0]
        concerns["Price chart"] = [f"{s} (price chart): {row['reading']}." for s, row in signals.iterrows() if row["points"] < 0]
        details["technicals"] = tech
    else:
        problems["Price chart"] = problem

    # --- 3E: analysts ----------------------------------------------------------------
    experts, problem = _run("Analysts", lambda: an.analyst_summary(ticker))
    if experts is not None and pd.notna(experts["score"]):
        scores["Analysts"] = experts["score"]
        summaries["Analysts"] = f"analyst views are {experts['verdict']}"
        signals = experts["signals"]
        strengths["Analysts"] = [f"{s} (analysts): {row['reading']}." for s, row in signals.iterrows() if row["points"] > 0]
        concerns["Analysts"] = [f"{s} (analysts): {row['reading']}." for s, row in signals.iterrows() if row["points"] < 0]
        details["analysts"] = experts
    else:
        problems["Analysts"] = problem or "no analysts cover this stock"

    # --- Blend the scores using the weights ------------------------------------------
    used = {part: s for part, s in scores.items() if pd.notna(s) and weights.get(part, 0) > 0}
    total_weight = sum(weights[part] for part in used)
    if len(used) >= MIN_PARTS and total_weight > 0:
        overall = sum(used[part] * weights[part] for part in used) / total_weight
    else:
        overall = np.nan

    rows = []
    for part in WEIGHTS:
        rows.append({
            "part": part,
            "score": scores.get(part, np.nan),
            "weight_pct": weights[part] / total_weight * 100 if part in used else 0.0,
            "summary": summaries.get(part, ""),
            "skipped_because": problems.get(part, "") if part not in used else "",
        })
    parts = pd.DataFrame(rows).set_index("part")

    # --- Momentum on its own line ------------------------------------------------------
    price_momentum = _price_momentum_pct(tech["momentum"]) if tech is not None else np.nan
    analyst_momentum = experts["momentum_score"] if experts is not None else np.nan
    both = [m for m in (price_momentum, analyst_momentum) if pd.notna(m)]
    combined = float(np.mean(both)) if both else np.nan
    reading = "n/a" if pd.isna(combined) else "strong" if combined >= 65 else "weak" if combined <= 35 else "mixed"

    # --- Reasons: strengths from the best parts, concerns from the worst ---------------
    by_score = sorted(used, key=lambda part: used[part], reverse=True)
    top_strengths = _pick(strengths, by_score)
    top_concerns = _pick(concerns, list(reversed(by_score)))

    return {
        "company": ticker,
        "name": info["name"],
        "score": overall,
        "verdict": _suggestion(overall),
        "momentum": {"price_pct": price_momentum, "analyst_pct": analyst_momentum,
                     "combined_pct": combined, "reading": reading},
        "parts": parts,
        "strengths": top_strengths,
        "concerns": top_concerns,
        "health_checks": checks,
        "details": details,
    }


def _pick(reasons: dict, part_order: list, how_many: int = 3) -> list:
    """Take reasons one part at a time, in the given order, until we have enough.

    Taking one per part first keeps the list varied, instead of three
    reasons all from the same part.
    """
    picked = []
    queues = {part: list(reasons.get(part, [])) for part in part_order}
    while len(picked) < how_many and any(queues.values()):
        for part in part_order:
            if queues[part] and len(picked) < how_many:
                picked.append(queues[part].pop(0))
    return picked


# ===========================================================================
# THE PORTFOLIO REVIEW
# ===========================================================================

def portfolio_review(portfolio: dict, weights: dict = None, include_rivals: bool = True) -> dict:
    """Run the verdict on every stock you own and flag the ones worth a look.

    portfolio       a portfolio from portfolio.py (load_portfolio, or the
                    Streamlit app's st.session_state.portfolio)
    weights         optional, the same as for stock_verdict
    include_rivals  False makes it much faster for big portfolios

    Returns a dictionary:
        {
          "table":   one row per stock, most worrying first: name, score,
                     verdict, momentum, the top concern, and a flag
          "results": every stock's full stock_verdict(...) result
        }

    A stock is flagged when its verdict is "look closer" or "consider trimming".
    The first run takes about half a minute per stock; repeats are fast.
    """
    tickers = list(dict.fromkeys(pf.holdings_table(portfolio)["ticker"]))   # unique, in order
    results, rows = {}, []
    for ticker in tickers:
        result = stock_verdict(ticker, weights=weights, include_rivals=include_rivals)
        results[ticker] = result
        rows.append({
            "ticker": ticker,
            "name": result["name"],
            "score": result["score"],
            "verdict": result["verdict"],
            "momentum": result["momentum"]["reading"],
            "top concern": result["concerns"][0] if result["concerns"] else "",
            "flag": result["verdict"] in ("look closer", "consider trimming"),
        })

    columns = ["name", "score", "verdict", "momentum", "top concern", "flag"]
    table = pd.DataFrame(rows, columns=["ticker"] + columns).set_index("ticker")
    table = table.sort_values("score", na_position="first")        # most worrying first
    return {"table": table, "results": results}


# ===========================================================================
# CHART
# ===========================================================================

def verdict_chart(result: dict):
    """Horizontal bars of the six part scores, with the overall score marked.

    Green bars are good (60 or more), red are concerns (40 or less), grey
    are in between. Skipped parts show as empty rows.
    """
    parts = result["parts"].reset_index()
    parts["label"] = [
        f"{row.part} ({row.weight_pct:.0f}%)" if row.weight_pct > 0 else f"{row.part} (skipped)"
        for row in parts.itertuples()
    ]
    parts["colour"] = ["good" if s >= 60 else "concern" if s <= 40 else "neutral" if pd.notna(s) else "skipped"
                       for s in parts["score"]]

    fig = px.bar(
        parts, x="score", y="label", orientation="h", color="colour",
        color_discrete_map={"good": "#16a34a", "neutral": "#9ca3af", "concern": "#dc2626", "skipped": "#e5e7eb"},
        range_x=[0, 100], text=parts["score"].round(0),
        title=f"{result['company']}: {result['verdict']} (overall {result['score']:.0f} / 100)",
        labels={"score": "Score (0 to 100)", "label": "", "colour": ""},
    )
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(parts["label"])))
    if pd.notna(result["score"]):
        fig.add_vline(x=result["score"], line_dash="dash", annotation_text="overall", annotation_position="top")
    fig.update_layout(showlegend=False, height=380)
    return fig
