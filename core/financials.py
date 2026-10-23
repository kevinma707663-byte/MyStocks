"""
financials.py - MyAnalysis Part 3A: "Is the business healthy?"

WHAT THIS FILE DOES
    Shows a company's three financial statements and calculates the
    standard ratios from them, for every year plus the last 12 months.

THE THREE STATEMENTS
    income statement     the yearly report card: money in, money out, profit
    balance sheet        a snapshot of what it owns (assets) and owes (liabilities)
    cash flow statement  where real cash came from and where it went

PERIODS (the columns)
    "TTM"     trailing twelve months: the latest four quarters added up.
              Its price-based ratios use TODAY's share price.
    "FY2025"  the company's business ("fiscal") year that ended in 2025.
              Its price-based ratios use the share price on the last day
              of that year. Fiscal years don't always end in December.
              Apple's ends in September.

PERCENTS
    Every ratio ending in _pct is a percent number: 5.0 means 5%.

BANKS, INSURERS AND FUNDS
    Banks don't report things like gross profit or current assets, so some
    ratios come back blank (NaN) for them. That's expected, not a bug.
    For banks and insurers we also blank the cash flow ratios, because their
    cash flow mixes in customer deposits and loans, which makes "free cash
    flow" meaningless. Funds like SPY have no financial statements at all.

THE FUNCTIONS OTHER FILES USE
    statements(ticker)            -> the three statements, key lines only
    ratios_table(ticker)          -> every ratio, every period, plus a trend
    latest(ratios, key)           -> one ratio's most recent value
    ratio_guide()                 -> what each ratio means and how it's calculated
    ratio_chart(ratios, keys)     -> line chart of chosen ratios over the years
    format_statement(table)       -> a statement with readable numbers (416.16B)
    format_ratios(ratios)         -> the ratios with readable numbers (26.9%, 34.1x)
    format_money(value)           -> one big number made readable (416161000000 -> 416.16B)
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

# Our own price fetcher. The dot means "from this same core/ folder".
from . import data


# ===========================================================================
# THE RATIO GUIDE
#
# Every ratio we calculate, with:
#   group             which family it belongs to
#   label             a friendly name for tables
#   unit              "x" means times, "%" is a percent number, "$" is money
#   formula           how it's calculated
#   meaning           what it tells you, in plain English
#   higher_is_better  True, False, or None when neither is clearly better
# ===========================================================================

RATIOS = {
    # --- Valuation: is the stock cheap or pricey for what you get? ----------
    "pe_ratio": {
        "group": "Valuation", "label": "Price / earnings (P/E)", "unit": "x",
        "formula": "share price / earnings per share",
        "meaning": "Dollars you pay for each $1 of yearly profit. Lower is cheaper. Blank when there's a loss.",
        "higher_is_better": False,
    },
    "price_to_book": {
        "group": "Valuation", "label": "Price / book", "unit": "x",
        "formula": "market value / shareholders' equity",
        "meaning": "Price compared with what the owners would keep if the company sold everything and paid its debts. Lower is cheaper.",
        "higher_is_better": False,
    },
    "price_to_sales": {
        "group": "Valuation", "label": "Price / sales", "unit": "x",
        "formula": "market value / revenue",
        "meaning": "Dollars you pay for each $1 of yearly sales. Handy when a company has no profit yet.",
        "higher_is_better": False,
    },
    "ev_to_ebitda": {
        "group": "Valuation", "label": "EV / EBITDA", "unit": "x",
        "formula": "(market value + debt - cash) / EBITDA",
        "meaning": "Price of buying the WHOLE business, debts included, compared with its profit before interest, taxes and accounting charges. Lower is cheaper.",
        "higher_is_better": False,
    },
    "fcf_yield_pct": {
        "group": "Valuation", "label": "Free cash flow yield %", "unit": "%",
        "formula": "free cash flow / market value",
        "meaning": "Spare cash the business makes in a year, as a percent of what the whole company costs. Higher is better.",
        "higher_is_better": True,
    },
    "dividend_yield_pct": {
        "group": "Valuation", "label": "Dividend yield %", "unit": "%",
        "formula": "dividends paid / market value",
        "meaning": "Cash paid to shareholders in a year, as a percent of the stock price. Higher isn't always better: a very high yield can mean the price crashed.",
        "higher_is_better": None,
    },

    # --- Profitability: how good is it at turning sales into profit? -------
    "gross_margin_pct": {
        "group": "Profitability", "label": "Gross margin %", "unit": "%",
        "formula": "gross profit / revenue",
        "meaning": "Cents left from each $1 of sales after paying to make the product. High margins often mean pricing power.",
        "higher_is_better": True,
    },
    "operating_margin_pct": {
        "group": "Profitability", "label": "Operating margin %", "unit": "%",
        "formula": "operating income / revenue",
        "meaning": "Cents left from each $1 of sales after running the whole business: staff, rent, research and so on.",
        "higher_is_better": True,
    },
    "net_margin_pct": {
        "group": "Profitability", "label": "Net profit margin %", "unit": "%",
        "formula": "net income / revenue",
        "meaning": "Cents of final profit from each $1 of sales, after everything including taxes. This is 'the' profit margin.",
        "higher_is_better": True,
    },
    "roe_pct": {
        "group": "Profitability", "label": "Return on equity %", "unit": "%",
        "formula": "net income / shareholders' equity",
        "meaning": "Profit made on the owners' money. 15% or more is usually strong. Very high numbers can come from heavy debt or big buybacks.",
        "higher_is_better": True,
    },
    "roa_pct": {
        "group": "Profitability", "label": "Return on assets %", "unit": "%",
        "formula": "net income / total assets",
        "meaning": "Profit made on everything the company owns. Banks usually sit around 1%.",
        "higher_is_better": True,
    },
    "roic_pct": {
        "group": "Profitability", "label": "Return on invested capital %", "unit": "%",
        "formula": "operating profit after tax / invested capital",
        "meaning": "Profit made on ALL the money put in by owners and lenders. A favourite test of management skill.",
        "higher_is_better": True,
    },
    "eps": {
        "group": "Profitability", "label": "Earnings per share", "unit": "$",
        "formula": "net income / diluted shares",
        "meaning": "The slice of the year's profit that belongs to one share.",
        "higher_is_better": True,
    },

    # --- Debt and safety: could it survive a bad year? ----------------------
    "debt_to_equity": {
        "group": "Debt and safety", "label": "Debt / equity", "unit": "x",
        "formula": "total debt / shareholders' equity",
        "meaning": "Borrowed money for every $1 of owners' money. Above 2 is heavy for most companies, but normal for banks.",
        "higher_is_better": False,
    },
    "current_ratio": {
        "group": "Debt and safety", "label": "Current ratio", "unit": "x",
        "formula": "current assets / current liabilities",
        "meaning": "Can it pay the bills due within a year? Above 1 means more short-term assets than short-term bills.",
        "higher_is_better": True,
    },
    "quick_ratio": {
        "group": "Debt and safety", "label": "Quick ratio", "unit": "x",
        "formula": "(current assets - inventory) / current liabilities",
        "meaning": "Like the current ratio, but leaves out inventory, which can be slow to sell.",
        "higher_is_better": True,
    },
    "interest_coverage": {
        "group": "Debt and safety", "label": "Interest coverage", "unit": "x",
        "formula": "EBIT / interest expense",
        "meaning": "How many times over profit could pay the interest bill. Below 3 can be a warning sign.",
        "higher_is_better": True,
    },

    # --- Growth: is the business getting bigger? ----------------------------
    "revenue_growth_pct": {
        "group": "Growth", "label": "Revenue growth %", "unit": "%",
        "formula": "revenue this year / revenue last year - 1",
        "meaning": "How fast sales grew compared with the year before.",
        "higher_is_better": True,
    },
    "eps_growth_pct": {
        "group": "Growth", "label": "EPS growth %", "unit": "%",
        "formula": "EPS this year / EPS last year - 1",
        "meaning": "How fast profit per share grew. Blank if last year was a loss.",
        "higher_is_better": True,
    },
    "fcf_growth_pct": {
        "group": "Growth", "label": "Free cash flow growth %", "unit": "%",
        "formula": "free cash flow this year / last year - 1",
        "meaning": "How fast spare cash grew. Blank if last year's was negative.",
        "higher_is_better": True,
    },

    # --- Cash: does profit turn into real money? ----------------------------
    "free_cash_flow": {
        "group": "Cash", "label": "Free cash flow", "unit": "$",
        "formula": "operating cash flow - capital spending",
        "meaning": "Real cash left after paying to keep the business running. It pays dividends, buybacks and debt.",
        "higher_is_better": True,
    },
    "fcf_margin_pct": {
        "group": "Cash", "label": "Free cash flow margin %", "unit": "%",
        "formula": "free cash flow / revenue",
        "meaning": "Cents of spare cash from each $1 of sales.",
        "higher_is_better": True,
    },
    "cash_conversion": {
        "group": "Cash", "label": "Cash conversion", "unit": "x",
        "formula": "operating cash flow / net income",
        "meaning": "Does reported profit show up as real cash? Around 1 or more is healthy. Well below 1 is worth a closer look.",
        "higher_is_better": True,
    },
}

# The growth ratios compare one year with the year before.
# The TTM column has no "year before" in our data, so these stay blank there.
GROWTH_RATIOS = ["revenue_growth_pct", "eps_growth_pct", "fcf_growth_pct"]

# Ratios built on free cash flow. Left blank for banks and insurers.
CASH_FLOW_RATIOS = ["fcf_yield_pct", "fcf_growth_pct", "free_cash_flow", "fcf_margin_pct", "cash_conversion"]

# Yahoo industry names that start with these words get the bank treatment.
FINANCIAL_INDUSTRIES = ("Banks", "Insurance")


# ===========================================================================
# WHICH LINES WE READ FROM THE STATEMENTS
#
# Format:  our name: (which statement, Yahoo's name for the line)
# ===========================================================================

LINES = {
    "revenue": ("income", "Total Revenue"),
    "gross_profit": ("income", "Gross Profit"),
    "operating_income": ("income", "Operating Income"),
    "net_income": ("income", "Net Income"),
    "eps": ("income", "Diluted EPS"),
    "ebit": ("income", "EBIT"),                      # earnings before interest and taxes
    "ebitda": ("income", "EBITDA"),                  # ...and before depreciation and amortization
    "interest_expense": ("income", "Interest Expense"),
    "tax": ("income", "Tax Provision"),
    "pretax_income": ("income", "Pretax Income"),
    "diluted_shares": ("income", "Diluted Average Shares"),
    "total_assets": ("balance", "Total Assets"),
    "equity": ("balance", "Stockholders Equity"),
    "total_debt": ("balance", "Total Debt"),
    "cash": ("balance", "Cash And Cash Equivalents"),
    "current_assets": ("balance", "Current Assets"),
    "current_liabilities": ("balance", "Current Liabilities"),
    "inventory": ("balance", "Inventory"),
    "invested_capital": ("balance", "Invested Capital"),
    "shares_outstanding": ("balance", "Ordinary Shares Number"),
    "operating_cash_flow": ("cashflow", "Operating Cash Flow"),
    "free_cash_flow": ("cashflow", "Free Cash Flow"),
    "dividends_paid": ("cashflow", "Cash Dividends Paid"),
}

# The lines shown by statements(), in a sensible reading order.
# Yahoo has 40 to 70 lines per statement, most of them obscure.
KEY_LINES = {
    "income": [
        "Total Revenue", "Cost Of Revenue", "Gross Profit",
        "Research And Development", "Selling General And Administration",
        "Operating Income", "Interest Expense", "Pretax Income", "Tax Provision",
        "Net Income", "Diluted EPS", "Diluted Average Shares", "EBITDA",
    ],
    "balance": [
        "Total Assets", "Current Assets", "Cash And Cash Equivalents", "Inventory",
        "Total Liabilities Net Minority Interest", "Current Liabilities",
        "Total Debt", "Stockholders Equity", "Ordinary Shares Number",
    ],
    "cashflow": [
        "Operating Cash Flow", "Capital Expenditure", "Free Cash Flow",
        "Cash Dividends Paid", "Repurchase Of Capital Stock",
        "Issuance Of Debt", "Repayment Of Debt",
    ],
}


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _year_label(period_end) -> str:
    """Turn a period-end date like 2025-09-30 into "FY2025"."""
    return f"FY{pd.Timestamp(period_end).year}"


def _line(table: pd.DataFrame, name: str) -> pd.Series:
    """One line of a statement, like "Total Revenue", across all periods.

    If the company doesn't report that line (banks have no "Gross Profit"),
    hand back a row of blanks instead of crashing.
    """
    if name in table.index:
        return table.loc[name].astype(float)
    return pd.Series(np.nan, index=table.columns, dtype=float)


def _growth(values: pd.Series) -> pd.Series:
    """Percent change from each year to the next. Values must be newest first.

    Growth is left blank when last year's number was zero or negative,
    because "growth" from a loss doesn't mean anything sensible.
    """
    # .shift(-1) lines each year up with the year before it.
    last_year = values.shift(-1)
    return ((values / last_year - 1) * 100).where(last_year > 0)


def _trend(values: pd.Series, higher_is_better) -> str:
    """Compare the newest year with the oldest year we have. Values must be newest first.

    Returns "improving", "worsening", "steady" (changed less than 5%),
    or "n/a" when there isn't enough data or neither direction is better.
    """
    # No number for the newest year means we can't say where it's heading now.
    if len(values) == 0 or pd.isna(values.iloc[0]):
        return "n/a"

    values = values.dropna()
    if len(values) < 2 or higher_is_better is None:
        return "n/a"

    newest, oldest = values.iloc[0], values.iloc[-1]
    change = newest - oldest

    # Small moves count as "steady".
    if abs(change) <= 0.05 * abs(oldest):
        return "steady"

    went_up = change > 0
    return "improving" if went_up == higher_is_better else "worsening"


# ===========================================================================
# GATHERING THE RAW NUMBERS
# ===========================================================================

def _yearly_facts(ticker: str) -> pd.DataFrame:
    """The raw numbers we need, one row per business year, newest first."""
    tables = data.get_financial_statements(ticker)
    periods = tables["income"].columns

    # Build a table with one row per year and one column per line in LINES.
    facts = pd.DataFrame(index=periods)
    for our_name, (statement, yahoo_name) in LINES.items():
        facts[our_name] = _line(tables[statement], yahoo_name).reindex(periods)

    # Yahoo often adds an extra old year that's almost empty. Drop any year
    # with neither revenue nor net income.
    facts = facts.dropna(subset=["revenue", "net_income"], how="all")

    # Remember each year's end date (for its share price), then label it.
    facts["price_date"] = facts.index
    facts.index = [_year_label(d) for d in facts.index]
    return facts


def _ttm_facts(ticker: str) -> pd.DataFrame:
    """The raw numbers for the last 12 months, as a one-row table.

    Income and cash flow lines: the latest 4 quarters added up.
    Balance sheet lines: the latest quarter, because a balance sheet is a
    snapshot of one day, not a total over time.

    Returns an empty table if Yahoo has fewer than 4 quarters.
    """
    tables = data.get_financial_statements(ticker, quarterly=True)
    if tables["income"].shape[1] < 4:
        return pd.DataFrame()

    row = {}
    for our_name, (statement, yahoo_name) in LINES.items():
        values = _line(tables[statement], yahoo_name)
        if statement == "balance" or our_name == "diluted_shares":
            # A snapshot: take the newest quarter.
            row[our_name] = values.iloc[0] if len(values) else np.nan
        else:
            # A flow: add up the newest 4 quarters.
            # min_count=4 means "stay blank unless all 4 quarters have a number".
            row[our_name] = values.iloc[:4].sum(min_count=4)

    # If a quarter's EPS was missing, work it out from profit and shares instead.
    if pd.isna(row["eps"]) and row["diluted_shares"]:
        row["eps"] = row["net_income"] / row["diluted_shares"]

    # TTM valuations use today's price, so the price date is today.
    row["price_date"] = pd.Timestamp.today().normalize()
    return pd.DataFrame([row], index=["TTM"])


def _currency_fix(ticker: str) -> float:
    """The exchange rate that puts the share price in the statements' currency.

    Most companies report in the currency their stock trades in, so this is 1.
    Some don't: Shopify trades in Canadian dollars on the TSX but reports in
    US dollars. For those, we convert the price at today's exchange rate so
    the valuation ratios compare like with like, and say so in a warning.
    """
    info = data.get_info(ticker)
    trades_in = info["currency"]
    reports_in = info["financial_currency"] or trades_in

    if trades_in and reports_in and trades_in != reports_in:
        warnings.warn(
            f"{ticker} trades in {trades_in} but reports in {reports_in}. "
            f"Prices were converted at today's rate for the valuation ratios."
        )
        return data.get_fx_rate(trades_in, reports_in)
    return 1.0


def _add_prices(facts: pd.DataFrame, ticker: str, fx: float) -> pd.DataFrame:
    """Add each period's share price, converted with fx from _currency_fix()."""
    # Plain prices (what you'd see on the news), from a little before the
    # oldest year-end until today.
    start = facts["price_date"].min() - pd.Timedelta(days=10)
    prices = data.get_prices(ticker, start=start, adjusted=False)[ticker]

    facts = facts.copy()
    facts["price"] = [data.price_on(prices, day) * fx for day in facts["price_date"]]
    return facts


# ===========================================================================
# THE RATIO MATH
# ===========================================================================

def _calculate(f: pd.DataFrame) -> pd.DataFrame:
    """Turn raw numbers into ratios. One row per period, one column per ratio.

    f is the raw-number table. f.revenue means "the revenue column".
    .where(condition) keeps a number only where the condition is True and
    leaves a blank elsewhere. We use it to skip ratios that make no sense,
    like a P/E when the company lost money.
    """
    r = pd.DataFrame(index=f.index)

    # --- Building blocks -----------------------------------------------------
    # Shares: use the balance sheet's count, or the average diluted shares.
    shares = f.shares_outstanding.fillna(f.diluted_shares)
    # EPS: use the reported number, or work it out.
    eps = f.eps.fillna(f.net_income / f.diluted_shares)
    # What the whole company is worth on the stock market.
    market_value = f.price * shares
    # Enterprise value: buying the whole company including its debt,
    # minus the cash you'd get with it.
    enterprise_value = market_value + f.total_debt.fillna(0) - f.cash.fillna(0)
    # The share of profit paid in tax. Only meaningful when there was a profit.
    tax_rate = (f.tax / f.pretax_income).where(f.pretax_income > 0).clip(0, 1)

    # --- Valuation -----------------------------------------------------------
    r["pe_ratio"] = (f.price / eps).where(eps > 0)
    r["price_to_book"] = (market_value / f.equity).where(f.equity > 0)
    r["price_to_sales"] = market_value / f.revenue
    r["ev_to_ebitda"] = (enterprise_value / f.ebitda).where(f.ebitda > 0)
    r["fcf_yield_pct"] = f.free_cash_flow / market_value * 100
    # Yahoo shows dividends paid as a negative number (cash going out).
    r["dividend_yield_pct"] = f.dividends_paid.abs() / market_value * 100

    # --- Profitability -------------------------------------------------------
    r["gross_margin_pct"] = f.gross_profit / f.revenue * 100
    r["operating_margin_pct"] = f.operating_income / f.revenue * 100
    r["net_margin_pct"] = f.net_income / f.revenue * 100
    r["roe_pct"] = (f.net_income / f.equity * 100).where(f.equity > 0)
    r["roa_pct"] = f.net_income / f.total_assets * 100
    r["roic_pct"] = f.ebit * (1 - tax_rate) / f.invested_capital * 100
    r["eps"] = eps

    # --- Debt and safety -----------------------------------------------------
    r["debt_to_equity"] = (f.total_debt / f.equity).where(f.equity > 0)
    r["current_ratio"] = f.current_assets / f.current_liabilities
    r["quick_ratio"] = (f.current_assets - f.inventory.fillna(0)) / f.current_liabilities
    r["interest_coverage"] = (f.ebit / f.interest_expense).where(f.interest_expense > 0)

    # --- Cash ----------------------------------------------------------------
    r["free_cash_flow"] = f.free_cash_flow
    r["fcf_margin_pct"] = f.free_cash_flow / f.revenue * 100
    r["cash_conversion"] = (f.operating_cash_flow / f.net_income).where(f.net_income > 0)

    # Dividing by zero gives "infinity". Turn any of those into blanks.
    return r.replace([np.inf, -np.inf], np.nan)


# ===========================================================================
# THE FUNCTIONS OTHER FILES USE
# ===========================================================================

def statements(ticker: str, key_lines_only: bool = True) -> dict:
    """The three financial statements, ready to read.

    Returns {"income": table, "balance": table, "cashflow": table}.
    Rows are line items, columns are business years like "FY2025", newest first.

    key_lines_only  True: just the important lines, in a sensible order.
                    False: every line Yahoo has (40 to 70 per statement).
    """
    tables = data.get_financial_statements(ticker)
    readable = {}
    for name, table in tables.items():
        if key_lines_only:
            # Keep the key lines this company actually reports, in our order.
            table = table.reindex([line for line in KEY_LINES[name] if line in table.index])
        # Drop nearly-empty old years, and label the columns "FY2025" etc.
        table = table.dropna(axis="columns", thresh=max(1, len(table) // 2))
        table.columns = [_year_label(c) for c in table.columns]
        readable[name] = table
    return readable


def ratios_table(ticker: str) -> pd.DataFrame:
    """Every ratio for every period, plus whether it's getting better.

    Returns a table with one ROW per ratio and these columns:
        group    the ratio's family, like "Valuation"
        label    its friendly name
        TTM      the last 12 months (if Yahoo has enough quarters)
        FY2025, FY2024, ...   each business year, newest first
        trend    "improving", "worsening", "steady" or "n/a", comparing the
                 newest business year with the oldest one shown

    Look up one number like this:  table.loc["pe_ratio", "TTM"]
    """
    yearly = _yearly_facts(ticker)
    if yearly.empty:
        warnings.warn(f"No financial statements for {ticker}. Funds and ETFs don't have them.")
        return pd.DataFrame(columns=["group", "label", "trend"])

    # Work out the currency conversion once (it warns if one is needed).
    fx = _currency_fix(ticker)

    # --- Yearly ratios, including growth ------------------------------------
    yearly = _add_prices(yearly, ticker, fx)
    yearly_ratios = _calculate(yearly)
    yearly_ratios["revenue_growth_pct"] = _growth(yearly["revenue"])
    yearly_ratios["eps_growth_pct"] = _growth(yearly_ratios["eps"])
    yearly_ratios["fcf_growth_pct"] = _growth(yearly["free_cash_flow"])

    # --- Last-12-months ratios (no growth, see GROWTH_RATIOS) ---------------
    ttm = _ttm_facts(ticker)
    if ttm.empty:
        all_ratios = yearly_ratios
    else:
        ttm_ratios = _calculate(_add_prices(ttm, ticker, fx))
        all_ratios = pd.concat([ttm_ratios, yearly_ratios])

    # --- Banks and insurers: blank the cash flow ratios ----------------------
    industry = data.get_info(ticker)["industry"] or ""
    if industry.startswith(FINANCIAL_INDUSTRIES):
        all_ratios[CASH_FLOW_RATIOS] = np.nan
        warnings.warn(
            f"{ticker} is in the {industry} industry. Cash flow ratios are left "
            f"blank, because its cash flow mixes in customer deposits and loans."
        )

    # --- Flip it: one row per ratio, one column per period -------------------
    # .T means "transpose": rows become columns and columns become rows.
    table = all_ratios[list(RATIOS)].T
    year_columns = [c for c in table.columns if c != "TTM"]

    # Add the friendly name, the family, and the trend.
    table.insert(0, "group", [RATIOS[key]["group"] for key in table.index])
    table.insert(1, "label", [RATIOS[key]["label"] for key in table.index])
    table["trend"] = [
        _trend(table.loc[key, year_columns].astype(float), RATIOS[key]["higher_is_better"])
        for key in table.index
    ]
    return table


def latest(ratios: pd.DataFrame, key: str) -> float:
    """One ratio's most recent value from a ratios_table(...).

    Uses the last 12 months (TTM) if there's a number there, otherwise
    the newest business year that has one. Blank if there's none at all.

    Example:  latest(table, "pe_ratio")  ->  39.45
    """
    periods = [c for c in ratios.columns if c not in ("group", "label", "trend")]
    for period in periods:                       # TTM first, then newest year first
        value = ratios.loc[key, period]
        if pd.notna(value):
            return float(value)
    return np.nan


def ratio_guide() -> pd.DataFrame:
    """Every ratio's family, formula and plain-English meaning, as a table."""
    guide = pd.DataFrame(RATIOS).T
    return guide[["group", "label", "unit", "formula", "meaning"]]


def ratio_chart(ratios: pd.DataFrame, keys: list, title: str = "Ratios over time"):
    """Line chart of chosen ratios across the years. Pass in ratios_table(...).

    keys   which ratios to draw, like ["gross_margin_pct", "net_margin_pct"].
           Pick ratios with the same unit so they share one scale.
    """
    # Keep just the period columns, oldest first, with TTM last.
    periods = [c for c in ratios.columns if c not in ("group", "label", "trend")]
    in_time_order = [c for c in reversed(periods) if c != "TTM"] + (["TTM"] if "TTM" in periods else [])

    # Reshape into one row per (period, ratio) pair, which plotly likes.
    chart_data = ratios.loc[keys, in_time_order].T
    chart_data.columns = [RATIOS[key]["label"] for key in keys]

    fig = px.line(chart_data, markers=True, title=title, labels={"index": "", "value": "", "variable": ""})
    return fig


# ===========================================================================
# FORMATTING FOR DISPLAY
#
# These turn raw numbers into readable text for tables. They return COPIES
# full of text, so use them only for showing, never for more math.
# ===========================================================================

def format_money(value) -> str:
    """Make one big money number readable.

    416161000000 -> "416.16B", 98500000 -> "98.5M", 7.46 -> "7.46". Blank -> "n/a".
    """
    if pd.isna(value):
        return "n/a"
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.2f}B"
    if abs(value) >= 1e6:
        return f"{value / 1e6:,.1f}M"
    return f"{value:,.2f}"


def format_statement(table: pd.DataFrame) -> pd.DataFrame:
    """A statement from statements(...) with readable numbers like "416.16B"."""
    # .map() runs format_money on every single cell.
    return table.map(format_money)


def format_ratios(ratios: pd.DataFrame) -> pd.DataFrame:
    """The table from ratios_table(...) with readable numbers.

    Percents get a % sign, "times" ratios get an x, money gets B or M.
    The friendly label becomes the row name.
    """
    periods = [c for c in ratios.columns if c not in ("group", "label", "trend")]
    shown = ratios.copy()

    # Number columns can only hold numbers. "object" columns can hold text too.
    shown[periods] = shown[periods].astype(object)

    for key in ratios.index:
        unit = RATIOS[key]["unit"]
        for period in periods:
            value = ratios.loc[key, period]
            if pd.isna(value):
                text = "n/a"
            elif unit == "%":
                text = f"{value:.1f}%"
            elif unit == "x":
                text = f"{value:.2f}x"
            else:
                text = format_money(value)
            shown.loc[key, period] = text

    return shown.set_index("label")
