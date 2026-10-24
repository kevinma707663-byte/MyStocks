"""
my_risks.py - the MyRisks section: "Where could my portfolio get hurt?"

WHAT THIS FILE DOES
    Breaks your portfolio's risk into eight plain-English areas, gives each
    one a level (low, medium or high), suggests what you could do about the
    biggest ones, and adds it all up into a risk score from 0 to 100
    (higher = riskier).

THE EIGHT AREAS
    Concentration      too many eggs in one basket? Your biggest holding, your
                       top 3, and how many equal-sized stocks your portfolio
                       really behaves like ("effective number of stocks").
    Sector             too much money in one industry?
    Currency           how much of your money is in a foreign currency, and what
                       a 10% move in the exchange rate would do to your total.
    Moving together    do your stocks rise and fall together? If they do, owning
                       several protects you less than you'd think. Measured with
                       correlation: 1 = always move together, 0 = unrelated.
    Who brings risk    each stock's share of your money next to its share of
                       your ups and downs. A small holding can bring big swings.
    Market risk        beta: how much you tend to move when the S&P 500 moves.
                       Beta 1.2 means a 10% market fall has tended to mean 12% for you.
    Worst drop         the biggest fall from a peak over the past few years.
    Bad day            "value at risk": on a bad day, the kind that happens about
                       1 day in 20, how much money you could lose.

HOW THE SCORE WORKS
    Each area's level counts as low = 0, medium = 50, high = 100, and the
    score is their average. 60 or more is a high overall level, 35 to 60
    medium, below 35 low.

DATA
    The same dividend-adjusted daily prices as MyOptimizer, over the days
    every stock traded. Each stock's moves are in its own currency, and
    currency risk gets its own area instead.

PAST RISK ISN'T A PROMISE
    These numbers describe the past few years. Markets can do things they
    haven't done recently, so treat them as a guide, not a guarantee.

THE FUNCTIONS OTHER FILES USE
    portfolio_risks(portfolio)     -> the full risk report for what you own
    mix_risks(mix, value)          -> the same for any mix, like {"AAPL": 50, "KO": 50}
                                      (handy for MyOptimizer's best mix or MyEdit)
    sector_chart(report)           -> donut of your money by sector
    correlation_chart(report)      -> grid of which stocks move together
    risk_share_chart(report)       -> money share vs risk share for each stock
    drawdown_chart(report)         -> how far below its high your portfolio was, day by day
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
from . import my_stocks as ms


# ===========================================================================
# SETTINGS
# ===========================================================================

YEARS = 3                  # years of past prices to measure risk on
TRADING_DAYS = 252         # trading days in a year
BENCHMARK = "SPY"          # the S&P 500 fund, for market risk
HOME_CURRENCY = "CAD"      # the currency your total is counted in
FX_MOVE_PCT = 10           # the exchange-rate move used in the currency check
MARKET_FALL_PCT = 20       # the market fall used in the stress test
BAD_DAY_PCT = 5            # "a bad day" = the worst 5% of days (1 day in 20)
TOGETHER_PAIR = 0.7        # two stocks this correlated count as "moving together"

# Thresholds for each area's level: (medium from, high from).
LIMITS = {
    # 25% / 35%, so MyOptimizer's default 30% cap counts as medium, not high.
    "biggest_holding_pct": (25, 35),
    "effective_stocks": (8, 4),          # FEWER is riskier, so these count down
    "biggest_sector_pct": (35, 50),
    "foreign_currency_pct": (75, 101),   # can only reach "medium"
    "average_correlation": (0.4, 0.6),
    "biggest_risk_share_pct": (25, 40),
    "beta": (0.9, 1.2),
    "worst_drop_pct": (20, 30),          # as a positive number: a 25% fall = 25
    "bad_day_pct": (1.5, 2.5),
}

LEVEL_POINTS = {"low": 0, "medium": 50, "high": 100}


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _level(value: float, key: str) -> str:
    """Turn a measurement into "low", "medium" or "high" using LIMITS."""
    medium, high = LIMITS[key]
    if pd.isna(value):
        return "low"
    if key == "effective_stocks":               # fewer stocks = riskier
        return "high" if value < high else "medium" if value < medium else "low"
    return "high" if value >= high else "medium" if value >= medium else "low"


def _worse(*levels: str) -> str:
    """The riskier of several levels."""
    return max(levels, key=lambda level: LEVEL_POINTS[level])


def _money(amount: float, currency: str) -> str:
    """$1,234 in a currency, for messages."""
    return f"${amount:,.0f} {currency}"


# ===========================================================================
# THE MAIN CALCULATION
# ===========================================================================

def _risks(weights: pd.Series, sectors: pd.Series, currencies: pd.Series,
           value: float, home_currency: str, years: int) -> dict:
    """Work out all eight areas for one mix.

    weights     share of your money in each stock, adding up to 1
    sectors     each stock's sector
    currencies  each stock's trading currency
    value       the total value in the home currency, for dollar amounts
    """
    # --- Daily returns for the stocks and the S&P 500 -------------------------
    returns = data.get_daily_returns(list(weights.index) + [BENCHMARK], years)
    stocks = [t for t in weights.index if t in returns.columns]
    w = weights[stocks] / weights[stocks].sum()       # re-add to 1 if any were dropped
    stock_returns = returns[stocks]
    portfolio = stock_returns @ w                    # the mix's daily % change
    market = returns[BENCHMARK]

    areas, top = [], []                              # top = (points, suggestion)

    # --- 1. Concentration --------------------------------------------------------
    biggest = w.idxmax()
    biggest_pct = w.max() * 100
    top3_pct = w.nlargest(3).sum() * 100
    effective = 1 / (w ** 2).sum()                   # how many equal-sized stocks it acts like
    level = _worse(_level(biggest_pct, "biggest_holding_pct"), _level(effective, "effective_stocks"))
    areas.append({"area": "Concentration", "level": level,
                  "reading": f"Biggest: {biggest} {biggest_pct:.0f}%. Top 3: {top3_pct:.0f}%. Acts like {effective:.1f} equal stocks."})
    if level != "low":
        top.append((LEVEL_POINTS[level], f"{biggest} is {biggest_pct:.0f}% of your money, and your portfolio acts like only "
                                         f"{effective:.1f} equal-sized stocks. Spreading money across more stocks would lower this."))

    # --- 2. Sector ---------------------------------------------------------------
    by_sector = w.groupby(sectors[stocks].fillna("Fund or other")).sum().sort_values(ascending=False) * 100
    top_sector, top_sector_pct = by_sector.index[0], by_sector.iloc[0]
    level = _level(top_sector_pct, "biggest_sector_pct")
    how_many = f"{len(by_sector)} sector" + ("" if len(by_sector) == 1 else "s")
    areas.append({"area": "Sector", "level": level,
                  "reading": f"{top_sector_pct:.0f}% in {top_sector}, across {how_many}."})
    if level != "low":
        top.append((LEVEL_POINTS[level], f"{top_sector_pct:.0f}% of your money is in {top_sector}. "
                                         f"Adding stocks from other sectors would spread the risk."))

    # --- 3. Currency -------------------------------------------------------------
    by_currency = w.groupby(currencies[stocks]).sum() * 100
    foreign_pct = by_currency.drop(home_currency, errors="ignore").sum()
    fx_hit = value * foreign_pct / 100 * FX_MOVE_PCT / 100
    level = _level(foreign_pct, "foreign_currency_pct")
    split = ", ".join(f"{c} {p:.0f}%" for c, p in by_currency.sort_values(ascending=False).items())
    areas.append({"area": "Currency", "level": level,
                  "reading": f"{split}. A {FX_MOVE_PCT}% move in exchange rates would change your total by about {_money(fx_hit, home_currency)}."})
    if level != "low":
        top.append((LEVEL_POINTS[level], f"{foreign_pct:.0f}% of your money is outside {home_currency}. If those currencies fell "
                                         f"{FX_MOVE_PCT}% against the {home_currency}, you'd lose about {_money(fx_hit, home_currency)}."))

    # --- 4. Moving together -------------------------------------------------------
    correlation = stock_returns.corr()
    # The average correlation between DIFFERENT stocks, weighted by how much
    # money is in each pair. (A stock always correlates 1 with itself, so the
    # diagonal is left out.)
    pair_weights = np.outer(w, w)
    np.fill_diagonal(pair_weights, 0)
    average_corr = float((correlation.values * pair_weights).sum() / pair_weights.sum()) if pair_weights.sum() else np.nan
    # Every pair once: keep the grid's upper triangle (above the diagonal),
    # flatten it into a list of pairs, and drop the blanks.
    upper = np.triu(np.ones(correlation.shape, dtype=bool), k=1)
    pairs = correlation.where(upper).stack().dropna().sort_values(ascending=False)
    close_pairs = pairs[pairs >= TOGETHER_PAIR]
    level = _level(average_corr, "average_correlation")
    if len(pairs):
        reading = (f"Average correlation {average_corr:.2f}. "
                   f"Closest pair: {pairs.index[0][0]} and {pairs.index[0][1]} ({pairs.iloc[0]:.2f}).")
    else:
        reading = "Only one stock, so there's nothing to compare."
    areas.append({"area": "Moving together", "level": level, "reading": reading})
    if level != "low" or len(close_pairs):
        a, b = pairs.index[0]
        top.append((max(LEVEL_POINTS[level], 50 if len(close_pairs) else 0),
                    f"{a} and {b} move very closely together (correlation {pairs.iloc[0]:.2f}), so owning both "
                    f"protects you less than you'd think."))

    # --- 5. Who brings the risk ------------------------------------------------------
    yearly_cov = stock_returns.cov() * TRADING_DAYS
    portfolio_swings = float(np.sqrt(w @ yearly_cov @ w))
    # Each stock's contribution: its weight x how much it moves WITH the whole mix.
    contribution = w * (yearly_cov @ w) / portfolio_swings
    shares = pd.DataFrame({"money %": w * 100, "risk %": contribution / portfolio_swings * 100})
    shares = shares.sort_values("risk %", ascending=False)
    riskiest = shares.index[0]
    level = _level(shares["risk %"].iloc[0], "biggest_risk_share_pct")
    areas.append({"area": "Who brings risk", "level": level,
                  "reading": f"{riskiest}: {shares.loc[riskiest, 'money %']:.0f}% of your money, "
                             f"{shares.loc[riskiest, 'risk %']:.0f}% of your risk. Yearly swings {portfolio_swings * 100:.1f}%."})
    # A suggestion only when a stock brings MORE risk than its share of money
    # (1.5 times or more, and at least 15% of the risk). Otherwise it would
    # just repeat the concentration warning.
    outsized = shares[(shares["risk %"] > 1.5 * shares["money %"]) & (shares["risk %"] >= 15)]
    if len(outsized):
        t = outsized.index[0]
        top.append((max(LEVEL_POINTS[level], 50),
                    f"{t} is {shares.loc[t, 'money %']:.0f}% of your money but {shares.loc[t, 'risk %']:.0f}% of your risk. "
                    f"Trimming it would calm the portfolio down the most."))

    # --- 6. Market risk ------------------------------------------------------------
    beta = float(portfolio.cov(market) / market.var())
    stress_pct = beta * MARKET_FALL_PCT
    stress_hit = value * stress_pct / 100
    level = _level(beta, "beta")
    areas.append({"area": "Market risk", "level": level,
                  "reading": f"Beta {beta:.2f}. If the S&P 500 fell {MARKET_FALL_PCT}%, you'd expect about -{stress_pct:.0f}% "
                             f"({_money(stress_hit, home_currency)})."})
    if level != "low":
        top.append((LEVEL_POINTS[level], f"Your beta is {beta:.2f}: when the S&P 500 falls 10%, your portfolio has tended to fall "
                                         f"about {beta * 10:.0f}%. Steadier stocks, like consumer staples, would lower it."))

    # --- 7. Worst drop ---------------------------------------------------------------
    growth = (1 + portfolio).cumprod()
    peak = np.maximum(growth.cummax(), 1.0)          # the starting $1 counts as a high point
    underwater = (growth / peak - 1) * 100           # how far below the high, each day, in %
    worst_drop = float(underwater.min())
    worst_day = underwater.idxmin().date()
    stock_drops = {}
    for t in stocks:
        g = (1 + stock_returns[t]).cumprod()
        stock_drops[t] = float(((g / np.maximum(g.cummax(), 1.0)) - 1).min() * 100)
    stock_drops = pd.Series(stock_drops, name="worst drop %").sort_values()
    level = _level(-worst_drop, "worst_drop_pct")
    areas.append({"area": "Worst drop", "level": level,
                  "reading": f"{worst_drop:.1f}% at its worst, on {worst_day}. "
                             f"Worst single stock: {stock_drops.index[0]} {stock_drops.iloc[0]:.0f}%."})
    if level != "low":
        top.append((LEVEL_POINTS[level], f"Your mix fell {abs(worst_drop):.0f}% at its worst (on {worst_day}). "
                                         f"Ask yourself if you could sit through that again without selling."))

    # --- 8. Bad day (value at risk) -------------------------------------------------
    # The 5th percentile: 1 day in 20 was this bad or worse.
    bad_day = float(-np.percentile(portfolio, BAD_DAY_PCT) * 100)
    # Expected shortfall: the AVERAGE loss on those worst 1-in-20 days.
    cutoff = np.percentile(portfolio, BAD_DAY_PCT)
    shortfall = float(-portfolio[portfolio <= cutoff].mean() * 100)
    level = _level(bad_day, "bad_day_pct")
    areas.append({"area": "Bad day", "level": level,
                  "reading": f"About 1 day in 20, you could lose {bad_day:.1f}% ({_money(value * bad_day / 100, home_currency)}) "
                             f"or more. On those days the average loss is {shortfall:.1f}%."})
    if level != "low":
        top.append((LEVEL_POINTS[level], f"On a bad day (1 in 20), you could lose about {_money(value * bad_day / 100, home_currency)}. "
                                         f"If that would worry you, a steadier mix would help."))

    # --- Add it all up -----------------------------------------------------------------
    areas = pd.DataFrame(areas).set_index("area")
    score = float(areas["level"].map(LEVEL_POINTS).mean())
    overall = "high" if score >= 60 else "medium" if score >= 35 else "low"
    top.sort(key=lambda item: item[0], reverse=True)   # highest-level risks first

    return {
        "score": score,
        "level": overall,
        "areas": areas,
        "top_risks": [text for _, text in top[:3]],
        "value": value,
        "home_currency": home_currency,
        "period": {"start": returns.index[0].date(), "end": returns.index[-1].date(),
                   "years": round(len(returns) / TRADING_DAYS, 1)},
        "weights": (w * 100).round(1),
        "sectors": by_sector.round(1),
        "currencies": by_currency.round(1),
        "correlation": correlation,
        "risk_shares": shares.round(1),
        "beta": beta,
        "stress": {"market_fall_pct": MARKET_FALL_PCT, "expected_fall_pct": stress_pct, "expected_loss": stress_hit},
        "underwater": underwater,
        "stock_drops": stock_drops.round(1),
        "bad_day": {"loss_pct": bad_day, "loss": value * bad_day / 100,
                    "average_bad_day_pct": shortfall, "average_bad_day_loss": value * shortfall / 100},
    }


# ===========================================================================
# THE FUNCTIONS OTHER FILES USE
# ===========================================================================

def portfolio_risks(portfolio: dict, years: int = YEARS, home_currency: str = HOME_CURRENCY) -> dict:
    """The full risk report for what you own.

    portfolio  a portfolio from portfolio.py (or st.session_state.portfolio)

    Your weights come from MyStocks (each stock's slice of your pie, using
    today's exchange rate), and dollar amounts use your total in CAD.

    Returns a dictionary:
        {
          "score":       0 to 100, higher = riskier
          "level":       "low", "medium" or "high"
          "areas":       table: the eight areas, each with a level and a reading
          "top_risks":   up to 3 plain-English risks with suggestions, worst first
          "sectors", "currencies", "weights":  your money split three ways, in %
          "correlation": which stocks move together (a grid from -1 to 1)
          "risk_shares": each stock's money % vs risk %
          "beta", "stress":  market risk and a market-fall test
          "underwater":  how far below its high the portfolio was each day, in %
          "stock_drops": each stock's worst drop, in %
          "bad_day":     the 1-in-20 bad day loss, in % and dollars
          "period", "value", "home_currency"
        }
    """
    positions = ms.positions_table(portfolio)
    if positions.empty:
        raise ValueError("Your portfolio is empty, so there's no risk to measure yet.")
    positions = positions.set_index("ticker")

    # Your total in the home currency, converting each currency group.
    rates = {c: data.get_fx_rate(c, home_currency) for c in positions["currency"].unique()}
    value = float((positions["value"] * positions["currency"].map(rates)).sum())

    return _risks(positions["weight_pct"] / 100, positions["sector"], positions["currency"],
                  value, home_currency, years)


def mix_risks(mix: dict, value: float = 10_000, years: int = YEARS, home_currency: str = HOME_CURRENCY) -> dict:
    """The same risk report for any mix, like MyOptimizer's best mix or your MyEdit.

    mix    {ticker: % of your money}, like {"AAPL": 40, "KO": 60}
    value  the pretend total, for dollar amounts. Default $10,000.
    """
    tickers = data.clean_tickers(list(mix))
    weights = pd.Series([float(mix[t]) for t in mix], index=tickers)
    weights = weights[weights > 0]
    if len(weights) == 0:
        raise ValueError("The mix has no stocks with money in them.")
    sectors = pd.Series({t: data.get_info(t)["sector"] for t in weights.index})
    currencies = pd.Series({t: ms.currency_of(t) for t in weights.index})
    return _risks(weights / weights.sum(), sectors, currencies, value, home_currency, years)


# ===========================================================================
# CHARTS
# ===========================================================================

def sector_chart(report: dict):
    """Donut chart of your money by sector."""
    sectors = report["sectors"].reset_index()
    sectors.columns = ["sector", "percent"]
    fig = px.pie(sectors, names="sector", values="percent", hole=0.45,
                 title="Your money by sector")
    fig.update_traces(textinfo="label+percent")
    return fig


def correlation_chart(report: dict):
    """A grid showing which stocks move together.

    Dark red = they move together (close to 1). White = unrelated (0).
    Blue = they tend to move in opposite directions (below 0).
    """
    corr = report["correlation"]
    fig = px.imshow(
        corr.values, x=list(corr.columns), y=list(corr.index),
        zmin=-1, zmax=1, color_continuous_scale="RdBu_r", text_auto=".2f",
        title="Which stocks move together (1 = always, 0 = unrelated)",
        labels={"color": "Correlation"},
    )
    return fig


def risk_share_chart(report: dict):
    """Each stock's share of your money next to its share of your risk."""
    shares = report["risk_shares"].reset_index(names="ticker")
    shares = shares.melt(id_vars="ticker", var_name="share of", value_name="percent")
    shares["share of"] = shares["share of"].map({"money %": "Your money", "risk %": "Your risk"})
    fig = px.bar(
        shares, x="ticker", y="percent", color="share of", barmode="group",
        color_discrete_map={"Your money": "#64748b", "Your risk": "#dc2626"},
        title="Who brings the risk: share of money vs share of ups and downs",
        labels={"ticker": "", "percent": "%", "share of": ""},
    )
    return fig


def drawdown_chart(report: dict):
    """How far below its highest point the portfolio was, day by day.

    0% means it was at a new high. The lowest point is the worst drop.
    """
    underwater = report["underwater"]
    fig = go.Figure(go.Scatter(
        x=underwater.index, y=underwater.values, fill="tozeroy",
        line={"color": "#dc2626"}, name="Below the high",
        hovertemplate="%{x|%Y-%m-%d}: %{y:.1f}%<extra></extra>",
    ))
    worst_day = underwater.idxmin()
    fig.add_annotation(x=worst_day, y=underwater.min(), text=f"worst: {underwater.min():.1f}%",
                       showarrow=True, arrowhead=2, ay=30)
    fig.update_layout(title="How far below its high your portfolio was",
                      yaxis_title="% below the high", height=380)
    return fig
