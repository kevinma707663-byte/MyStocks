"""
dcf.py - MyAnalysis Part 3F: "What's the business really worth?"

WHAT THIS FILE DOES
    Runs a DCF (discounted cash flow) model. The idea in one sentence:
    a business is worth all the cash it will ever hand back, shrunk down
    because a dollar in the future is worth less than a dollar today.

THE STEPS
    1. Start from the cash the business made over the last 12 months.
    2. Grow it for 10 years: years 1 to 5 at a growth rate, then years 6 to
       10 slowing down step by step to a long-term rate (2.5% by default).
    3. After year 10, assume it grows at that long-term rate forever. The
       value of "forever" is called the terminal value.
    4. Shrink every future dollar back to today using a discount rate.
       A higher discount rate means future money is worth less today.
    5. Add it all up, adjust for debt and cash, and divide by the number of
       shares. Compare that with today's price.

WHICH CASH?
    Most companies: free cash flow (the cash left after running the
    business and paying for new equipment), discounted at the WACC.
    Banks and insurers: dividends, discounted at the cost of equity.
    Their cash flow mixes in customer deposits and loans, so free cash
    flow means nothing for them. This is called a dividend discount model.

THE DISCOUNT RATE, IN PLAIN WORDS
    Cost of equity  what shareholders expect to earn: the US 10-year yield
                    plus extra for risk (beta x the equity risk premium)
    Beta            how much the stock swings vs the market. Raw betas jump
                    around, so like Bloomberg we pull them a third of the
                    way toward 1.
    Cost of debt    the interest rate the company pays, after tax
    WACC            weighted average cost of capital: the two costs above,
                    weighted by how much of the company is shares vs debt

A SIMPLIFICATION TO KNOW ABOUT
    The free cash flow from the cash flow statement is after interest.
    Strictly, a WACC model wants cash flow before interest. For most
    companies the difference is small, and it keeps the model simple.

A DCF IS ONLY AS GOOD AS ITS GUESSES
    Small changes to growth or the discount rate move the answer a lot.
    That's why every result comes with a sensitivity table showing how the
    value changes if the guesses are off. Every input can be changed.

THE FUNCTIONS OTHER FILES USE
    dcf_valuation(ticker, ...)    -> the value per share, every step, and a 0 to 100 score
    bridge_chart(result)          -> waterfall: how the value per share is built up
    sensitivity_chart(result)     -> heat map: value per share if the guesses are off
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# numpy: math helpers. np.nan means "blank / not a number".
import numpy as np

# pandas: the library for tables of numbers.
import pandas as pd

# plotly: interactive charts.
import plotly.express as px
import plotly.graph_objects as go

# Our own files. The dot means "from this same core/ folder".
from . import data
from . import financials as fin


# ===========================================================================
# SETTINGS (every one of these can be overridden when you call dcf_valuation)
# ===========================================================================

HIGH_GROWTH_YEARS = 5          # years 1 to 5 grow at the chosen growth rate
FADE_YEARS = 5                 # years 6 to 10 slow down to the long-term rate
TERMINAL_GROWTH_PCT = 2.5      # growth forever after year 10, roughly the economy's pace
EQUITY_RISK_PREMIUM_PCT = 5.0  # extra return investors want for owning stocks over bonds

GROWTH_CAP_PCT = 20.0          # very fast growth rarely lasts 5 years, so cap the default
GROWTH_FLOOR_PCT = 0.0         # and don't assume shrinking by default
FALLBACK_GROWTH_PCT = 5.0      # used when there's no forecast and no history

DEFAULT_TAX_PCT = 21.0         # used when we can't work out the company's own tax rate
DEBT_SPREAD_PCT = 1.5          # cost of debt when unknown: the 10-year yield + 1.5 points
FALLBACK_RISK_FREE_PCT = 4.5   # used only if the 10-year yield can't be fetched

MIN_SPREAD_PCT = 1.0           # the discount rate must beat long-term growth by 1 point
CHEAP_MARGIN_PCT = 15.0        # value 15% or more above the price counts as undervalued


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _newest(table: pd.DataFrame, line: str) -> float:
    """The newest number on one line of a statement, or blank."""
    if line not in table.index:
        return np.nan
    values = table.loc[line].dropna()
    return float(values.iloc[0]) if len(values) else np.nan


def _last_four_quarters(table: pd.DataFrame, line: str) -> float:
    """One line added up over the newest 4 quarters. Blank unless all 4 have a number."""
    if line not in table.index or table.shape[1] < 4:
        return np.nan
    return float(table.loc[line].iloc[:4].sum(min_count=4))


def _cash_numbers(ticker: str) -> dict:
    """The numbers the model needs, for the last 12 months where possible.

    Flows (cash, interest, tax) add up the last 4 quarters, or fall back to
    the newest business year. Balances (debt, cash) use the newest quarter.
    """
    quarters = data.get_financial_statements(ticker, quarterly=True)
    years = data.get_financial_statements(ticker)

    def flow(statement, line):
        value = _last_four_quarters(quarters[statement], line)
        return value if pd.notna(value) else _newest(years[statement], line)

    def balance(line):
        value = _newest(quarters["balance"], line)
        return value if pd.notna(value) else _newest(years["balance"], line)

    return {
        "free_cash_flow": flow("cashflow", "Free Cash Flow"),
        # Yahoo shows dividends paid as a negative number (cash going out).
        "dividends": abs(flow("cashflow", "Cash Dividends Paid")),
        "interest": flow("income", "Interest Expense"),
        "tax": flow("income", "Tax Provision"),
        "pretax": flow("income", "Pretax Income"),
        "debt": balance("Total Debt"),
        "cash": balance("Cash And Cash Equivalents"),
    }


def _default_growth(ticker: str) -> tuple:
    """A sensible growth rate for years 1 to 5, and where it came from.

    First choice: analysts' forecast of next year's earnings growth.
    Second choice: last year's revenue growth. Last resort: 5%.
    Whatever it is, it's kept between 0% and 20%.
    """
    growth, source = np.nan, ""

    # Analysts' earnings forecasts: this year ("0y") and next year ("+1y").
    forecasts = data.get_analyst_data(ticker)["forecasts"]
    if not forecasts.empty and {"0y", "+1y"} <= set(forecasts.index):
        this_year = float(forecasts.loc["0y", "current"])
        next_year = float(forecasts.loc["+1y", "current"])
        if this_year > 0 and next_year > 0:
            growth = (next_year / this_year - 1) * 100
            source = "analysts' forecast of next year's earnings growth"

    # No forecast: use last year's revenue growth from Part 3A.
    if pd.isna(growth):
        ratios = fin.ratios_table(ticker)
        if not ratios.empty:
            growth = fin.latest(ratios, "revenue_growth_pct")
            source = "last year's revenue growth"

    if pd.isna(growth):
        return FALLBACK_GROWTH_PCT, "a standard 5%, because there's no forecast or history"

    capped = float(np.clip(growth, GROWTH_FLOOR_PCT, GROWTH_CAP_PCT))
    if capped != growth:
        limit = "capped at 20%" if growth > GROWTH_CAP_PCT else "raised to 0%"
        source = f"{source} ({growth:.1f}%), {limit}"
    return capped, source


def _discount_rate(ticker: str, numbers: dict, market_value: float, use_dividends: bool, risk_premium_pct: float) -> dict:
    """Work out the discount rate, step by step, keeping every piece for the table."""
    # --- Risk-free rate: the US 10-year yield (from Part 3C) ----------------
    yields = data.get_us_10y_yield()
    risk_free = float(yields.iloc[-1]) if not yields.empty else FALLBACK_RISK_FREE_PCT

    # --- Beta, pulled a third of the way toward 1 ("Blume adjustment") ------
    raw_beta = data.get_info(ticker)["beta"]
    raw_beta = float(raw_beta) if raw_beta is not None else 1.0
    beta = 0.67 * raw_beta + 0.33

    # --- Cost of equity ------------------------------------------------------
    cost_of_equity = risk_free + beta * risk_premium_pct

    pieces = {
        "risk_free_pct": risk_free,
        "raw_beta": raw_beta,
        "beta": beta,
        "cost_of_equity_pct": cost_of_equity,
    }

    # Banks and insurers: dividends belong to shareholders only, so the
    # cost of equity IS the discount rate.
    if use_dividends:
        pieces["discount_rate_pct"] = cost_of_equity
        return pieces

    # --- Tax rate: the company's own, if it made a profit -------------------
    if numbers["pretax"] and numbers["pretax"] > 0 and pd.notna(numbers["tax"]):
        tax_rate = float(np.clip(numbers["tax"] / numbers["pretax"] * 100, 0, 35))
    else:
        tax_rate = DEFAULT_TAX_PCT

    # --- Cost of debt: interest paid / debt, kept within sensible bounds ----
    debt = numbers["debt"] if pd.notna(numbers["debt"]) else 0.0
    if pd.notna(numbers["interest"]) and numbers["interest"] > 0 and debt > 0:
        cost_of_debt = float(np.clip(numbers["interest"] / debt * 100, risk_free, risk_free + 8))
    else:
        cost_of_debt = risk_free + DEBT_SPREAD_PCT
    after_tax_debt = cost_of_debt * (1 - tax_rate / 100)

    # --- WACC: weight each cost by its share of the company -----------------
    equity_share = market_value / (market_value + debt)
    wacc = equity_share * cost_of_equity + (1 - equity_share) * after_tax_debt

    pieces.update({
        "tax_rate_pct": tax_rate,
        "cost_of_debt_pct": cost_of_debt,
        "after_tax_debt_pct": after_tax_debt,
        "equity_share_pct": equity_share * 100,
        "discount_rate_pct": wacc,
    })
    return pieces


def _run_model(base: float, growth_pct: float, terminal_pct: float, rate_pct: float) -> dict:
    """The core DCF math. Returns the 10-year table and the totals.

    base          the starting yearly cash (last 12 months)
    growth_pct    growth for years 1 to 5
    terminal_pct  growth forever after year 10
    rate_pct      the discount rate
    """
    g, gt, r = growth_pct / 100, terminal_pct / 100, rate_pct / 100

    rows = []
    cash = base
    for year in range(1, HIGH_GROWTH_YEARS + FADE_YEARS + 1):
        # Years 1 to 5: full growth. Years 6 to 10: step down evenly to the
        # long-term rate, so year 10 grows at exactly the long-term rate.
        if year <= HIGH_GROWTH_YEARS:
            growth = g
        else:
            steps_in = year - HIGH_GROWTH_YEARS
            growth = g - (g - gt) * steps_in / FADE_YEARS
        cash = cash * (1 + growth)
        # The discount factor: what $1 received in that year is worth today.
        factor = 1 / (1 + r) ** year
        rows.append({"year": year, "growth_pct": growth * 100, "cash_flow": cash,
                     "discount_factor": factor, "present_value": cash * factor})

    projection = pd.DataFrame(rows).set_index("year")

    # Terminal value: year 10's cash growing at the long-term rate forever.
    # The formula for "a payment that grows forever" is next year's cash
    # divided by (discount rate - growth rate).
    terminal_value = projection["cash_flow"].iloc[-1] * (1 + gt) / (r - gt)
    terminal_today = terminal_value * projection["discount_factor"].iloc[-1]

    return {
        "projection": projection,
        "pv_ten_years": float(projection["present_value"].sum()),
        "terminal_value": float(terminal_value),
        "pv_terminal": float(terminal_today),
    }


def _currency_rate(ticker: str) -> tuple:
    """(rate, note) to turn the statements' currency into the trading currency.

    Shopify reports in US dollars but trades in Canadian dollars on the TSX,
    so its value per share has to be converted before comparing with the price.
    """
    info = data.get_info(ticker)
    trades_in, reports_in = info["currency"], info["financial_currency"] or info["currency"]
    if trades_in and reports_in and trades_in != reports_in:
        note = f"{ticker} reports in {reports_in} but trades in {trades_in}, so the value was converted at today's rate."
        return data.get_fx_rate(reports_in, trades_in), note
    return 1.0, ""


# ===========================================================================
# THE MAIN FUNCTION
# ===========================================================================

def dcf_valuation(
    ticker: str,
    growth_pct: float = None,
    terminal_growth_pct: float = TERMINAL_GROWTH_PCT,
    discount_rate_pct: float = None,
    equity_risk_premium_pct: float = EQUITY_RISK_PREMIUM_PCT,
) -> dict:
    """Value one stock with a DCF.

    ticker                   like "AAPL" or "RY.TO"
    growth_pct               growth for years 1 to 5, in %. Leave it out to use
                             analysts' forecast (capped between 0% and 20%).
    terminal_growth_pct      growth forever after year 10, in %. Default 2.5.
    discount_rate_pct        leave it out to work it out (WACC, or cost of
                             equity for banks), or type your own, in %.
    equity_risk_premium_pct  extra return wanted for owning stocks, in %. Default 5.

    Returns a dictionary:
        {
          "company", "method"     ("free cash flow" or "dividends"),
          "currency",             the stock's trading currency
          "price",                today's price
          "value_per_share",      what the DCF says one share is worth
          "upside_pct",           value vs price, in %
          "verdict",              "undervalued", "fairly valued" or "overvalued"
          "score",                0 to 100, where 50 means value = price
          "assumptions",          table: every input, its value, where it came from
          "projection",           table: the 10 years of cash, discounted
          "bridge",               how the total value is built up
          "sensitivity",          table: value per share for other discount
                                  rates (rows) and long-term growth rates (columns)
          "notes",                plain-English cautions
          "inputs",               the raw numbers behind the assumptions
        }

    Raises a ValueError with a plain-English message when a DCF can't be
    run, for example when free cash flow is negative.
    """
    ticker = data.clean_tickers(ticker)[0]
    info = data.get_info(ticker)
    industry = info["industry"] or ""
    use_dividends = industry.startswith(fin.FINANCIAL_INDUSTRIES)
    method = "dividends" if use_dividends else "free cash flow"

    # --- 1. The starting cash -----------------------------------------------
    numbers = _cash_numbers(ticker)
    if all(pd.isna(v) for v in numbers.values()):
        raise ValueError(f"{ticker} has no financial statements, so a DCF can't value it. Funds and ETFs don't have them.")
    base = numbers["dividends"] if use_dividends else numbers["free_cash_flow"]
    if pd.isna(base) or base <= 0:
        what = "doesn't pay dividends" if use_dividends else "has negative free cash flow"
        raise ValueError(
            f"{ticker} {what} over the last 12 months, so a DCF can't value it. "
            f"Try price to sales in Part 3A instead."
        )

    # --- 2. Price, shares, and currency -------------------------------------
    price = float(data.get_latest_prices(ticker).iloc[0])
    shares = info["shares_outstanding"]
    if not shares:
        raise ValueError(f"Yahoo doesn't say how many shares {ticker} has, so a DCF can't divide the value up.")
    fx, currency_note = _currency_rate(ticker)
    # The company's market value in the statements' currency.
    market_value = price / fx * shares

    # --- 3. Growth and the discount rate ------------------------------------
    if growth_pct is None:
        growth_pct, growth_source = _default_growth(ticker)
    else:
        growth_source = "your own choice"

    rate = _discount_rate(ticker, numbers, market_value, use_dividends, equity_risk_premium_pct)
    if discount_rate_pct is None:
        discount_rate_pct = rate["discount_rate_pct"]
        rate_source = "cost of equity" if use_dividends else "WACC"
    else:
        rate_source = "your own choice"

    if discount_rate_pct - terminal_growth_pct < MIN_SPREAD_PCT:
        raise ValueError(
            f"The discount rate ({discount_rate_pct:.1f}%) must be at least {MIN_SPREAD_PCT:.0f} point above "
            f"long-term growth ({terminal_growth_pct:.1f}%), or the value of 'forever' becomes infinite."
        )

    # --- 4. Run the model ----------------------------------------------------
    model = _run_model(base, growth_pct, terminal_growth_pct, discount_rate_pct)
    debt = numbers["debt"] if pd.notna(numbers["debt"]) else 0.0
    cash = numbers["cash"] if pd.notna(numbers["cash"]) else 0.0

    def per_share(m: dict) -> float:
        """Total value -> value of one share, in the trading currency."""
        total = m["pv_ten_years"] + m["pv_terminal"]
        if not use_dividends:
            # Free cash flow belongs to lenders AND shareholders. Lenders are
            # owed the debt; the company's cash belongs to shareholders.
            total = total - debt + cash
        return total / shares * fx

    value = per_share(model)
    upside = (value / price - 1) * 100

    if upside >= CHEAP_MARGIN_PCT:
        verdict = "undervalued"
    elif upside <= -CHEAP_MARGIN_PCT:
        verdict = "overvalued"
    else:
        verdict = "fairly valued"
    # 50 = value equals price. +50% upside or more = 100, -50% or worse = 0.
    score = float(np.clip(50 + upside, 0, 100))

    # --- 5. Sensitivity: the value if the guesses are off -------------------
    rates = [discount_rate_pct + step for step in (-1.0, -0.5, 0.0, 0.5, 1.0)]
    terminals = [terminal_growth_pct + step for step in (-1.0, -0.5, 0.0, 0.5, 1.0)]
    grid = {}
    for t in terminals:
        column = {}
        for r in rates:
            column[f"{r:.1f}%"] = per_share(_run_model(base, growth_pct, t, r)) if r - t >= MIN_SPREAD_PCT else np.nan
        grid[f"{t:.1f}%"] = column
    sensitivity = pd.DataFrame(grid)
    sensitivity.index.name = "discount rate"
    sensitivity.columns.name = "long-term growth"

    # --- 6. The bridge: how the total value is built up ---------------------
    total_pv = model["pv_ten_years"] + model["pv_terminal"]
    bridge = {
        "next_10_years": model["pv_ten_years"],
        "after_year_10": model["pv_terminal"],
        "terminal_share_pct": model["pv_terminal"] / total_pv * 100,
        "debt": 0.0 if use_dividends else debt,
        "cash": 0.0 if use_dividends else cash,
        "equity_value": value * shares / fx,
        "shares": float(shares),
        "fx": fx,
    }

    # --- 7. The assumptions table ---------------------------------------------
    base_label = "Starting dividends (last 12 months)" if use_dividends else "Starting free cash flow (last 12 months)"
    rows = [
        (base_label, fin.format_money(base), "the cash flow statement"),
        ("Growth, years 1 to 5", f"{growth_pct:.1f}%", growth_source),
        ("Growth, years 6 to 10", f"slows to {terminal_growth_pct:.1f}%", "steps down evenly each year"),
        ("Growth after year 10", f"{terminal_growth_pct:.1f}%", "roughly the long-run pace of the economy"),
        ("Risk-free rate", f"{rate['risk_free_pct']:.2f}%", "US 10-year bond yield (Part 3C)"),
        ("Beta", f"{rate['raw_beta']:.2f} raw, {rate['beta']:.2f} adjusted", "Yahoo, pulled a third of the way toward 1"),
        ("Equity risk premium", f"{equity_risk_premium_pct:.1f}%", "a common long-run estimate"),
        ("Cost of equity", f"{rate['cost_of_equity_pct']:.2f}%", "risk-free + beta x premium"),
    ]
    if not use_dividends:
        rows += [
            ("Cost of debt, after tax", f"{rate['after_tax_debt_pct']:.2f}%",
             f"{rate['cost_of_debt_pct']:.2f}% interest, {rate['tax_rate_pct']:.0f}% tax rate"),
            ("Funded by shares", f"{rate['equity_share_pct']:.0f}%", "market value vs debt"),
        ]
    rows.append(("Discount rate", f"{discount_rate_pct:.2f}%", rate_source))
    assumptions = pd.DataFrame(rows, columns=["assumption", "value", "where it comes from"]).set_index("assumption")

    # --- 8. Cautions -------------------------------------------------------------
    notes = []
    if use_dividends:
        notes.append(f"{ticker} is in the {industry} industry, so dividends are valued instead of free cash flow.")
        notes.append(
            "A dividend model only counts cash paid out. It ignores share buybacks and money kept "
            "to grow the business, so it often comes out low for banks."
        )
    if bridge["terminal_share_pct"] > 75:
        notes.append(
            f"{bridge['terminal_share_pct']:.0f}% of the value comes from after year 10, so small changes to "
            f"long-term guesses move the answer a lot. Check the sensitivity table."
        )
    if currency_note:
        notes.append(currency_note)

    return {
        "company": ticker,
        "method": method,
        "currency": info["currency"],
        "price": price,
        "value_per_share": value,
        "upside_pct": upside,
        "verdict": verdict,
        "score": score,
        "assumptions": assumptions,
        "projection": model["projection"],
        "bridge": bridge,
        "sensitivity": sensitivity,
        "notes": notes,
        "inputs": {"base": base, "growth_pct": growth_pct, "terminal_growth_pct": terminal_growth_pct,
                   "discount_rate_pct": discount_rate_pct, **rate},
    }


# ===========================================================================
# CHARTS
# ===========================================================================

def bridge_chart(result: dict):
    """Waterfall chart: how the value of ONE share is built up, step by step.

    Each bar adds (or takes away) a piece, and the last bar is the total.
    A dashed line shows today's price, so you can see the gap at a glance.
    """
    b = result["bridge"]
    to_share = b["fx"] / b["shares"]          # total value -> per share, in trading currency

    # Banks are valued on dividends, so say "dividends" instead of "cash".
    what = "dividends" if result["method"] == "dividends" else "cash"
    labels = [f"Next 10 years of {what}", "Everything after year 10"]
    values = [b["next_10_years"] * to_share, b["after_year_10"] * to_share]
    kinds = ["relative", "relative"]
    if result["method"] == "free cash flow":
        labels += ["Minus debt", "Plus cash"]
        values += [-b["debt"] * to_share, b["cash"] * to_share]
        kinds += ["relative", "relative"]
    labels.append("Value of one share")
    values.append(0)                            # plotly works out the total itself
    kinds.append("total")

    fig = go.Figure(go.Waterfall(
        x=labels, y=values, measure=kinds,
        text=[f"{v:,.2f}" for v in values[:-1]] + [f"{result['value_per_share']:,.2f}"],
        # "auto" writes each number inside its bar when it fits, so labels
        # don't collide with the dashed price line.
        textposition="auto",
        connector={"line": {"color": "lightgrey"}},
    ))
    fig.add_hline(y=result["price"], line_dash="dash", line_color="red",
                  annotation_text=f"today's price {result['price']:,.2f}", annotation_position="top left")
    fig.update_layout(
        title=f"{result['company']}: how the DCF value of one share is built ({result['currency']})",
        yaxis_title=f"Per share ({result['currency']})", showlegend=False, height=450,
    )
    return fig


def sensitivity_chart(result: dict):
    """Heat map of the value per share for other discount rates and long-term growth rates.

    Green squares are worth more than today's price, red squares less.
    The middle square is the main answer.
    """
    table = result["sensitivity"]
    fig = px.imshow(
        table.values,
        x=list(table.columns), y=list(table.index),
        color_continuous_scale="RdYlGn",
        color_continuous_midpoint=result["price"],   # yellow = today's price
        text_auto=".2f", aspect="auto",
        labels={"x": "Growth after year 10", "y": "Discount rate", "color": "Value per share"},
    )
    fig.update_layout(
        title=f"{result['company']}: value per share if the guesses are off (today's price {result['price']:,.2f})",
        height=420,
    )
    return fig
