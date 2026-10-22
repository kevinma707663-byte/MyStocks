"""
rivals.py - MyAnalysis Part 3B: "Is it better than its rivals?"

WHAT THIS FILE DOES
    Finds a company's main competitors ("rivals"), lines up their ratios
    side by side, and scores four qualities from 0 to 100:

        Management quality      Does management grow returns, buy back
                                shares, and keep debt in check?
        Competitive advantage   Does it earn more than rivals, year after year?
        Brand strength          Can it charge more than rivals? (pricing power)
        Industry trends         Is the whole industry growing and doing well?

HOW THE 0 TO 100 SCORES WORK
    For the first three qualities, each measurement asks "what share of the
    rivals does this company beat?" A score of 80 means it beats 80% of them.
    A quality's score is the average of its measurements.

    Industry trends is different, because it's about the whole group, not
    one company. Its score is the share of the industry that's growing
    sales, improving margins, and beating the S&P 500, averaged together.

    67 or more is "strong", 34 to 66 is "average", below 34 is "weak".

THESE ARE STAND-INS
    Management quality and brand strength are partly opinion. Nobody can
    measure them exactly from numbers, so we use number-based stand-ins.
    For example, brand strength is measured as pricing power: can the
    company keep a higher, steadier gross margin than its rivals?

HOW RIVALS ARE PICKED
    Yahoo lists the biggest companies in each industry. We skip tiny ones
    (under 0.5% of the industry's value) and skip the company itself, even
    when it's listed in another country (RY.TO and RY are the same bank).
    If that leaves fewer than 3, we top up with the biggest companies in
    the broader sector. You can always pass your own list instead.

STAND-INS CAN MISREAD SOME BUSINESSES
    Costco keeps its markup low on purpose and earns money from
    memberships, so "pricing power" scores it as weak on brand strength.
    Always read the "why" next to each score.

BANKS AND INSURERS
    They don't report gross margin, operating margin, or return on invested
    capital. So for them we use net margin and return on equity instead,
    and brand strength shows "n/a".

THE FUNCTIONS OTHER FILES USE
    find_rivals(ticker)                   -> a list of rival tickers
    compare_to_rivals(ticker)             -> side-by-side table, scores, details
    rivals_chart(side_by_side, column)    -> bar chart of one measure across companies
    scores_chart(scores)                  -> bar chart of the four 0 to 100 scores
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# warnings: a polite way to say "something looks off" without crashing.
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


# ===========================================================================
# SETTINGS
# ===========================================================================

# How many rivals to compare against.
HOW_MANY_RIVALS = 6

# Skip companies smaller than this share of their industry (0.005 = 0.5%).
MIN_MARKET_WEIGHT = 0.005

# Only top up from the broader sector if the industry has fewer rivals than
# this. Otherwise unrelated companies sneak in (Coca-Cola as a Costco rival).
MIN_INDUSTRY_RIVALS = 3

# The S&P 500 fund, used to judge whether the industry beat the market.
BENCHMARK = "SPY"

# The four qualities, in the order they're shown.
QUALITIES = ["Management quality", "Competitive advantage", "Brand strength", "Industry trends"]

# The measurements behind each quality, for most companies.
# Format:  key: (quality, friendly label, higher_is_better, tie_within)
#
# tie_within: differences this small count as a tie, not a win or loss.
# For example, 0.03% vs 0.26% insider ownership is meaningless noise.
# "Worst year" asks: even in its worst year, how good was it? A company
# that stays strong in its worst year has an advantage that lasts.
MEASURES = {
    "roic_trend": ("Management quality", "Change in return on invested capital (points)", True, 0),
    "share_change_pct": ("Management quality", "Change in share count % (below 0 = buybacks)", False, 1.0),
    "debt_change": ("Management quality", "Change in debt / equity", False, 0),
    "insider_pct": ("Management quality", "Insider ownership %", True, 1.0),
    "operating_margin_now": ("Competitive advantage", "Operating margin % now", True, 0),
    "operating_margin_worst": ("Competitive advantage", "Operating margin % in its worst year", True, 0),
    "roic_now": ("Competitive advantage", "Return on invested capital % now", True, 0),
    "gross_margin_now": ("Brand strength", "Gross margin % now", True, 0),
    "gross_margin_worst": ("Brand strength", "Gross margin % in its worst year", True, 0),
    "gross_margin_trend": ("Brand strength", "Change in gross margin (points)", True, 0),
}

# The same idea for banks and insurers, using ratios they actually report.
# There's no brand strength measure, because they have no gross margin.
BANK_MEASURES = {
    "roe_trend": ("Management quality", "Change in return on equity (points)", True, 0),
    "share_change_pct": ("Management quality", "Change in share count % (below 0 = buybacks)", False, 1.0),
    "debt_change": ("Management quality", "Change in debt / equity", False, 0),
    "insider_pct": ("Management quality", "Insider ownership %", True, 1.0),
    "net_margin_now": ("Competitive advantage", "Net profit margin % now", True, 0),
    "net_margin_worst": ("Competitive advantage", "Net profit margin % in its worst year", True, 0),
    "roe_now": ("Competitive advantage", "Return on equity % now", True, 0),
}

# The columns of the side-by-side table.
# Format:  ratio key from financials.py: column title
SIDE_BY_SIDE = {
    "pe_ratio": "P/E",
    "gross_margin_pct": "Gross margin %",
    "operating_margin_pct": "Operating margin %",
    "net_margin_pct": "Net margin %",
    "roe_pct": "Return on equity %",
    "roic_pct": "Return on invested capital %",
    "debt_to_equity": "Debt / equity",
    "revenue_growth_pct": "Revenue growth %",
}
RETURN_COLUMN = "1-year stock return %"
MEDIAN_ROW = "Rivals' median"


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _is_financial(ticker: str) -> bool:
    """True for banks and insurers, which need different measurements."""
    industry = data.get_info(ticker)["industry"] or ""
    return industry.startswith(fin.FINANCIAL_INDUSTRIES)


def _same_company(ticker_a, name_a, ticker_b, name_b) -> bool:
    """Spot the same company under two tickers.

    RY.TO and RY are Royal Bank listed in Toronto and New York, so we
    compare the part before the dot. GOOG and GOOGL are two kinds of
    Alphabet shares, so we also compare company names.
    """
    same_base = ticker_a.split(".")[0] == ticker_b.split(".")[0]
    same_name = bool(name_a) and bool(name_b) and name_a.lower() == name_b.lower()
    return same_base or same_name


def _years(ratios: pd.DataFrame, key: str) -> pd.Series:
    """A ratio's value for each business year, newest first (no TTM)."""
    year_columns = [c for c in ratios.columns if str(c).startswith("FY")]
    return ratios.loc[key, year_columns].astype(float)


def _change(values: pd.Series) -> float:
    """Newest year minus oldest year. Blank if the newest year is missing."""
    if len(values) == 0 or pd.isna(values.iloc[0]):
        return np.nan
    values = values.dropna()
    if len(values) < 2:
        return np.nan
    return float(values.iloc[0] - values.iloc[-1])


def _worst_year(values: pd.Series) -> float:
    """The lowest value across the business years. Needs at least 2 years."""
    values = values.dropna()
    if len(values) < 2:
        return np.nan
    return float(values.min())


def _share_change_pct(ticker: str) -> float:
    """How much the number of shares changed, newest year vs oldest, in %.

    Below 0 means the company bought back its own shares, which gives each
    remaining share a bigger slice. Above 0 means it issued new shares,
    which shrinks everyone's slice.
    """
    income = data.get_financial_statements(ticker)["income"]
    if "Diluted Average Shares" not in income.index:
        return np.nan
    shares = income.loc["Diluted Average Shares"].dropna()
    if len(shares) < 2:
        return np.nan
    return float((shares.iloc[0] / shares.iloc[-1] - 1) * 100)


def _beats_pct(values: pd.Series, company: str, higher_is_better: bool, tie_within: float = 0) -> float:
    """What share of the rivals does the company beat on this measurement, in %?

    Rivals within `tie_within` of the company count as a tie, and a tie
    counts as half a win. Blank if the company or all rivals are blank.
    """
    mine = values.get(company)
    others = values.drop(company).dropna()
    if pd.isna(mine) or others.empty:
        return np.nan

    # Close enough to call it a tie.
    ties = (others - mine).abs() <= tie_within
    if higher_is_better:
        wins = (others < mine) & ~ties          # ~ means "not"
    else:
        wins = (others > mine) & ~ties
    return float((wins.sum() + 0.5 * ties.sum()) / len(others) * 100)


def _verdict(score: float) -> str:
    """Turn a 0 to 100 score into a word."""
    if pd.isna(score):
        return "n/a"
    if score >= 67:
        return "strong"
    if score >= 34:
        return "average"
    return "weak"


def _one_year_returns(tickers: list) -> pd.Series:
    """Each stock's return over the past year, in %, plus the S&P 500's.

    Uses dividend-adjusted prices, so dividends count as part of the return.
    A stock that started trading partway through the year gets a blank,
    because a few months of returns isn't a fair one-year comparison.
    """
    prices = data.get_prices(list(tickers) + [BENCHMARK], period="1y").ffill()

    # Each stock's first day with a price.
    first_day = prices.apply(lambda column: column.first_valid_index())
    # Allow two weeks of slack for holidays and different exchanges.
    full_year = first_day <= prices.index[0] + pd.Timedelta(days=14)

    # .bfill() fills any blanks on the first day with the next price.
    first = prices.bfill().iloc[0]
    last = prices.iloc[-1]
    return ((last / first - 1) * 100).where(full_year)


# ===========================================================================
# FINDING RIVALS
# ===========================================================================

def find_rivals(ticker: str, how_many: int = HOW_MANY_RIVALS) -> list:
    """The company's biggest rivals, as a list of tickers.

    Starts with the biggest companies in the same industry, skips tiny ones
    and the company itself, then tops up from the same sector if needed.
    """
    ticker = data.clean_tickers(ticker)[0]
    info = data.get_info(ticker)

    if not info["industry_key"] and not info["sector_key"]:
        warnings.warn(f"Yahoo doesn't say which industry {ticker} is in. Pass your own rivals list.")
        return []

    chosen = []
    seen = [(ticker, info["name"])]

    def add_from(candidates: pd.DataFrame):
        """Add candidates in order, skipping the company itself and duplicates."""
        for symbol, row in candidates.iterrows():
            if len(chosen) == how_many:
                return
            if any(_same_company(symbol, row["name"], t, n) for t, n in seen):
                continue
            chosen.append(symbol)
            seen.append((symbol, row["name"]))

    # --- Step 1: big companies in the same industry --------------------------
    if info["industry_key"]:
        industry = data.get_group_companies("industry", info["industry_key"])
        add_from(industry[industry["market_weight"] >= MIN_MARKET_WEIGHT])

    # --- Step 2: too few? Top up from the broader sector ---------------------
    if len(chosen) < MIN_INDUSTRY_RIVALS and info["sector_key"]:
        add_from(data.get_group_companies("sector", info["sector_key"]))

    if not chosen:
        warnings.warn(f"Couldn't find rivals for {ticker}. Pass your own rivals list.")
    return chosen


# ===========================================================================
# MEASURING ONE COMPANY
# ===========================================================================

def _measure(ticker: str):
    """Every measurement for one company, plus its side-by-side numbers.

    Returns (measurements, side_by_side_row), or None if the company has
    no financial statements.
    """
    # Each company's own warnings (like "this is a bank") were already shown
    # in Part 3A. Repeating them for every rival would just be noise.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ratios = fin.ratios_table(ticker)
        insiders = data.get_info(ticker)["insider_ownership"]
    if ratios.empty:
        return None

    measurements = {
        # Management quality
        "roic_trend": _change(_years(ratios, "roic_pct")),
        "roe_trend": _change(_years(ratios, "roe_pct")),
        "share_change_pct": _share_change_pct(ticker),
        "debt_change": _change(_years(ratios, "debt_to_equity")),
        "insider_pct": insiders * 100 if insiders is not None else np.nan,
        # Competitive advantage
        "operating_margin_now": fin.latest(ratios, "operating_margin_pct"),
        "operating_margin_worst": _worst_year(_years(ratios, "operating_margin_pct")),
        "roic_now": fin.latest(ratios, "roic_pct"),
        "net_margin_now": fin.latest(ratios, "net_margin_pct"),
        "net_margin_worst": _worst_year(_years(ratios, "net_margin_pct")),
        "roe_now": fin.latest(ratios, "roe_pct"),
        # Brand strength
        "gross_margin_now": fin.latest(ratios, "gross_margin_pct"),
        "gross_margin_worst": _worst_year(_years(ratios, "gross_margin_pct")),
        "gross_margin_trend": _change(_years(ratios, "gross_margin_pct")),
        # Industry trends
        "revenue_growth_now": fin.latest(ratios, "revenue_growth_pct"),
        "operating_margin_trend": _change(_years(ratios, "operating_margin_pct")),
        "net_margin_trend": _change(_years(ratios, "net_margin_pct")),
    }
    side_by_side_row = {title: fin.latest(ratios, key) for key, title in SIDE_BY_SIDE.items()}
    return measurements, side_by_side_row


# ===========================================================================
# INDUSTRY TRENDS
# ===========================================================================

def _industry_trends(measures: pd.DataFrame, returns: pd.Series, financial: bool) -> dict:
    """How the whole group is doing: growth, margins, and stock performance.

    measures  one row per company (the company and its rivals)
    returns   1-year stock returns, including the S&P 500
    """
    companies = measures.index
    sp500_return = returns.get(BENCHMARK, np.nan)

    # Banks don't report operating margin, so use net margin for them.
    margin_trend = measures["net_margin_trend" if financial else "operating_margin_trend"]

    # For each test, count how many companies pass, out of those with data.
    def share_passing(values: pd.Series) -> tuple:
        known = values.dropna()
        passing = int(known.sum())
        return passing, len(known)

    growing, growing_total = share_passing(measures["revenue_growth_now"].dropna() > 0)
    improving, improving_total = share_passing(margin_trend.dropna() > 0)
    company_returns = returns.reindex(companies).dropna()
    beating, beating_total = share_passing(company_returns > sp500_return)

    # The score is the average share passing across the three tests.
    shares = [p / t * 100 for p, t in [(growing, growing_total), (improving, improving_total), (beating, beating_total)] if t]
    score = float(np.mean(shares)) if shares else np.nan

    why = (
        f"{growing} of {growing_total} companies grew sales, "
        f"{improving} of {improving_total} improved margins, "
        f"{beating} of {beating_total} beat the S&P 500 over the past year."
    )
    return {
        "score": score,
        "why": why,
        "median_revenue_growth_pct": float(measures["revenue_growth_now"].median()),
        "median_1y_return_pct": float(company_returns.median()) if len(company_returns) else np.nan,
        "sp500_1y_return_pct": float(sp500_return),
    }


# ===========================================================================
# THE MAIN FUNCTION
# ===========================================================================

def compare_to_rivals(ticker: str, rivals=None, how_many: int = HOW_MANY_RIVALS) -> dict:
    """Compare a company with its rivals and score four qualities.

    ticker    the company, like "NVDA"
    rivals    optional list of your own rivals, like ["AMD", "INTC"].
              Leave it out to pick them automatically with find_rivals().
    how_many  how many rivals to pick automatically

    Returns a dictionary:
        {
          "company":      "NVDA",
          "rivals":       ["AVGO", "MU", ...],
          "side_by_side": table with one row per company, plus "Rivals' median"
          "scores":       table with one row per quality: score, verdict, why
          "details":      table with one row per measurement: the company's
                          number, the rivals' median, and the share it beats
          "industry":     facts about the whole group
        }

    The first run downloads data for every rival, so it can take
    15 to 30 seconds. After that, the one-hour memory makes it fast.
    """
    ticker = data.clean_tickers(ticker)[0]
    rivals = data.clean_tickers(rivals) if rivals else find_rivals(ticker, how_many)
    rivals = [r for r in rivals if r != ticker]

    # --- Measure every company -----------------------------------------------
    measured, side_rows = {}, {}
    for company in [ticker] + rivals:
        result = _measure(company)
        if result is None:
            if company == ticker:
                raise ValueError(f"{ticker} has no financial statements, so it can't be compared. Funds and ETFs don't have them.")
            warnings.warn(f"Skipped rival {company}: it has no financial statements.")
            continue
        measured[company], side_rows[company] = result

    rivals = [r for r in rivals if r in measured]
    if not rivals:
        raise ValueError(f"No usable rivals found for {ticker}. Try passing your own list, like rivals=['AMD', 'INTC'].")

    # One row per company, one column per measurement.
    measures = pd.DataFrame(measured).T
    financial = _is_financial(ticker)
    returns = _one_year_returns(list(measured))

    # --- Side-by-side table --------------------------------------------------
    side = pd.DataFrame(side_rows).T
    side[RETURN_COLUMN] = returns.reindex(side.index)
    side.insert(0, "name", [data.get_info(c)["name"] for c in side.index])
    median = side.loc[rivals].median(numeric_only=True)
    median["name"] = ""
    side.loc[MEDIAN_ROW] = median

    # --- Score each measurement ----------------------------------------------
    measure_set = BANK_MEASURES if financial else MEASURES
    detail_rows = []
    for key, (quality, label, higher_is_better, tie_within) in measure_set.items():
        values = measures[key].astype(float)
        detail_rows.append(
            {
                "quality": quality,
                "measure": label,
                "company": values[ticker],
                "rivals_median": values[rivals].median(),
                "beats_pct": _beats_pct(values, ticker, higher_is_better, tie_within),
            }
        )
    details = pd.DataFrame(detail_rows)

    # --- Average the measurements into quality scores ------------------------
    score_rows = []
    for quality in QUALITIES[:3]:
        part = details[(details["quality"] == quality) & details["beats_pct"].notna()]
        if part.empty:
            why = "Can't be measured for banks and insurers." if financial and quality == "Brand strength" else "Not enough data."
            score_rows.append({"quality": quality, "score": np.nan, "verdict": "n/a", "why": why})
            continue

        score = float(part["beats_pct"].mean())
        best = part.loc[part["beats_pct"].idxmax()]
        worst = part.loc[part["beats_pct"].idxmin()]
        if best["beats_pct"] == worst["beats_pct"]:
            # Every measurement scored the same, so there's no best or worst.
            why = f"Every measure beats {best['beats_pct']:.0f}% of rivals."
        else:
            why = (
                f"Best: {best['measure']} (beats {best['beats_pct']:.0f}% of rivals). "
                f"Weakest: {worst['measure']} (beats {worst['beats_pct']:.0f}%)."
            )
        score_rows.append({"quality": quality, "score": score, "verdict": _verdict(score), "why": why})

    # Industry trends has its own recipe.
    industry = _industry_trends(measures, returns, financial)
    score_rows.append(
        {
            "quality": "Industry trends",
            "score": industry["score"],
            "verdict": _verdict(industry["score"]),
            "why": industry["why"],
        }
    )
    scores = pd.DataFrame(score_rows).set_index("quality")

    return {
        "company": ticker,
        "rivals": rivals,
        "side_by_side": side,
        "scores": scores,
        "details": details,
        "industry": industry,
    }


# ===========================================================================
# CHARTS
# ===========================================================================

def rivals_chart(side_by_side: pd.DataFrame, column: str):
    """Bar chart of one column across the company and its rivals.

    Pass in compare_to_rivals(...)["side_by_side"] and a column title,
    like "Gross margin %". The company is the first bar, in blue.
    A dashed line marks the rivals' median.
    """
    company = side_by_side.index[0]
    rows = side_by_side.drop(index=MEDIAN_ROW, errors="ignore")

    chart_data = pd.DataFrame(
        {
            "ticker": rows.index,
            "value": rows[column].astype(float),
            "who": ["This company" if t == company else "Rival" for t in rows.index],
        }
    )
    fig = px.bar(
        chart_data, x="ticker", y="value", color="who",
        color_discrete_map={"This company": "#2563eb", "Rival": "#9ca3af"},
        title=f"{column}: {company} vs rivals",
        labels={"ticker": "", "value": column, "who": ""},
    )

    # A dashed line at the rivals' median, if we have one.
    if MEDIAN_ROW in side_by_side.index and pd.notna(side_by_side.loc[MEDIAN_ROW, column]):
        fig.add_hline(
            y=float(side_by_side.loc[MEDIAN_ROW, column]),
            line_dash="dash",
            annotation_text="Rivals' median",
        )
    return fig


def scores_chart(scores: pd.DataFrame, company: str = ""):
    """Horizontal bars for the four 0 to 100 scores. Pass in compare_to_rivals(...)["scores"]."""
    chart_data = scores.reset_index()
    fig = px.bar(
        chart_data, x="score", y="quality", orientation="h",
        text=chart_data["verdict"],                 # write the verdict on each bar
        range_x=[0, 100],
        title=f"{company} vs its rivals (0 to 100)".strip(),
        labels={"score": "Score", "quality": ""},
    )
    # Put Management quality at the top.
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(QUALITIES)))
    return fig
