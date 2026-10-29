"""
my_stocks.py - the MyStocks section: "What do I own, and am I winning?"

WHAT THIS FILE DOES
    Takes your portfolio (the stack of receipts from portfolio.py) and works
    out the standard numbers: what each stock is worth today, your gains,
    how much each stock moved today, and how big a slice of your pie it is.

CANADIAN AND US STOCKS STAY SEPARATE
    Stocks are grouped by the currency they trade in (CAD or USD). Each
    group's dollar amounts stay in its own currency, so exchange rate swings
    never blur how your stocks actually did. The only place we convert is
    the pie slices, which need one currency to compare sizes.

THE S&P 500 TWIN
    For every purchase you made, an imaginary twin spent the same amount on
    the S&P 500 (the SPY fund) on the same day. If your stocks grew more than
    the twin's, you beat the market. Both groups are compared to SPY by
    percent growth, ignoring exchange rates.

PRICES USED
    Plain prices, the kind your broker shows, not dividend-adjusted ones.
    Dividends you received are not counted as gains, and the twin's
    S&P 500 price doesn't count dividends either, so it's a fair fight.

THE FUNCTIONS OTHER FILES USE
    positions_table(portfolio)          -> one row per stock with all the numbers
    portfolio_summary(portfolio)        -> headline numbers per currency group
    value_history(portfolio, "CAD")     -> daily value of you vs your twin
    allocation_chart(positions)         -> pie chart of where your money is
    value_chart(history, "CAD")         -> line chart of you vs your twin
    currency_of(ticker)                 -> "CAD" or "USD"

    The charts come back as plotly figures. Show them with fig.show() in
    the notebook, or st.plotly_chart(fig) in Streamlit.

PERCENTS
    Every column or key ending in _pct is a percent number: 5.0 means 5%.
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# warnings: shows a gentle message without stopping the program.
import warnings

# numpy: math helpers. We use np.nan, which means "blank / not a number".
import numpy as np

# pandas: the library for tables of numbers.
import pandas as pd

# plotly.express: quick, interactive charts.
import plotly.express as px

# Our own files. The dot means "from this same core/ folder".
from . import data
from . import portfolio as pf


# ===========================================================================
# SETTINGS
# ===========================================================================

# The fund every group is compared against: SPY tracks the S&P 500.
BENCHMARK = "SPY"

# The currency used ONLY for pie slices and the combined total.
HOME_CURRENCY = "CAD"

# Ticker endings for Canadian exchanges: Toronto, TSX Venture, NEO, and CSE.
CANADIAN_ENDINGS = (".TO", ".V", ".NE", ".CN")

# The columns of positions_table(), in order.
POSITION_COLUMNS = [
    "ticker", "name", "currency", "sector",
    "shares", "avg_cost", "cost", "price", "value",
    "gain", "gain_pct", "day_change", "day_change_pct",
    "weight_pct", "pe_ratio", "dividend_yield_pct",
]

# The two lines on the value chart.
YOU = "You"
TWIN = "S&P 500 twin"


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def currency_of(ticker: str) -> str:
    """Which currency a stock trades in, like "CAD" or "USD".

    Asks Yahoo first. If Yahoo doesn't say, guesses from the ticker:
    Canadian tickers end in .TO, .V, .NE or .CN.
    """
    reported = data.get_info(ticker).get("currency")
    if reported:
        return reported.upper()
    return "CAD" if ticker.upper().endswith(CANADIAN_ENDINGS) else "USD"


def _pct(part, whole) -> float:
    """part / whole as a percent (5.0 means 5%).

    Gives NaN ("not a number", a blank) instead of crashing when whole is 0.
    """
    return part / whole * 100 if whole else np.nan


def _receipts(portfolio: dict) -> pd.DataFrame:
    """All purchases as a table, with two extra columns added:

        cost      shares x buy price, what that purchase cost
        currency  which currency group the stock belongs to
    """
    table = pf.holdings_table(portfolio)
    table["cost"] = table["shares"] * table["buy_price"]
    # Turn "2024-01-15" text into real dates so we can compare them.
    table["buy_date"] = pd.to_datetime(table["buy_date"])
    table["currency"] = [currency_of(t) for t in table["ticker"]]
    return table



# ===========================================================================
# 1. ONE ROW PER STOCK
# ===========================================================================

def positions_table(portfolio: dict, home_currency: str = HOME_CURRENCY) -> pd.DataFrame:
    """One row per stock, with every standard number.

    Columns:
        ticker, name, currency, sector
        shares              total shares across all your purchases
        avg_cost            total paid / total shares
        cost                total paid
        price               latest price
        value               shares x price, what it's worth now
        gain                value - cost, in the stock's own currency
        gain_pct            gain as a percent of what you paid
        day_change          how much the value moved since yesterday's close
        day_change_pct      the same move as a percent
        weight_pct          this stock's slice of your whole pie,
                            using today's exchange rate
        pe_ratio            price-to-earnings
        dividend_yield_pct  yearly dividends as a percent of the price

    Canadian stocks come first, then US, biggest first within each group.
    """
    receipts = _receipts(portfolio)

    # Nothing owned yet: hand back an empty table with the right columns.
    if receipts.empty:
        return pd.DataFrame(columns=POSITION_COLUMNS)

    # --- Combine receipts into one row per stock ----------------------------
    # groupby("ticker") makes a pile of receipts for each stock,
    # then .agg() adds up the shares and the cost in each pile.
    combined = receipts.groupby("ticker", sort=False).agg(
        shares=("shares", "sum"),
        cost=("cost", "sum"),
        currency=("currency", "first"),
    )

    # --- Today's and yesterday's prices ------------------------------------
    # The last 5 days of plain prices. .ffill() fills holiday gaps by
    # carrying the last known price forward.
    try:
        recent = data.get_prices(list(combined.index), period="5d", adjusted=False).ffill()
    except ValueError:
        # Yahoo had no prices for ANY of them (usually a typo in every ticker).
        # Keep going with an empty price table, so every row shows a blank
        # price instead of the whole section stopping.
        warnings.warn(f"No price data for {list(combined.index)}. Check the tickers.")
        recent = pd.DataFrame()

    # --- Build each row ------------------------------------------------------
    rows = []
    for ticker, stock in combined.iterrows():
        info = data.get_info(ticker)

        # Latest price and yesterday's close. If Yahoo had no prices for this
        # ticker, leave them blank (a warning was already shown).
        if ticker in recent.columns:
            price = recent[ticker].iloc[-1]
            yesterday = recent[ticker].iloc[-2] if len(recent) > 1 else price
        else:
            price = yesterday = np.nan

        # The core math.
        value = stock["shares"] * price
        gain = value - stock["cost"]
        day_change = stock["shares"] * (price - yesterday)

        # Yahoo gives dividend yield as a fraction (0.02), so turn it into 2.0.
        dividend_yield = info["dividend_yield"]
        dividend_yield_pct = dividend_yield * 100 if dividend_yield is not None else np.nan

        rows.append(
            {
                "ticker": ticker,
                "name": info["name"],
                "currency": stock["currency"],
                "sector": info["sector"],
                "shares": stock["shares"],
                "avg_cost": stock["cost"] / stock["shares"],
                "cost": stock["cost"],
                "price": price,
                "value": value,
                "gain": gain,
                "gain_pct": _pct(gain, stock["cost"]),
                "day_change": day_change,
                "day_change_pct": _pct(price - yesterday, yesterday),
                "pe_ratio": info["pe_ratio"],
                "dividend_yield_pct": dividend_yield_pct,
            }
        )

    table = pd.DataFrame(rows)

    # --- Weights: each stock's slice of the whole pie ------------------------
    # CAD and USD can't be added directly, so for this ONE column we convert
    # every value into the home currency at today's exchange rate.
    rates = {cur: data.get_fx_rate(cur, home_currency) for cur in table["currency"].unique()}
    value_in_home = table["value"] * table["currency"].map(rates)
    table["weight_pct"] = value_in_home / value_in_home.sum() * 100

    # Canadian first, then US. Within each, biggest value first.
    table = table.sort_values(["currency", "value"], ascending=[True, False])
    return table.reset_index(drop=True)[POSITION_COLUMNS]


# ===========================================================================
# 2. YOU VS YOUR S&P 500 TWIN, DAY BY DAY
# ===========================================================================

def value_history(portfolio: dict, currency: str) -> pd.DataFrame:
    """Daily value of one currency group, next to its S&P 500 twin.

    Each purchase only counts from the day you made it. On that same day,
    the twin spends the same amount on the S&P 500. Both lines include the
    money you added, so the gap between them is how far ahead of (or behind)
    the market you are.

    This uses the shares you own NOW. If you sold some, the chart shows
    your remaining shares as if you'd always held that many.

    Returns a table with a "You" column and an "S&P 500 twin" column,
    one row per trading day, in that group's currency.
    """
    currency = currency.strip().upper()

    # Keep only the purchases in this currency group.
    receipts = _receipts(portfolio)
    receipts = receipts[receipts["currency"] == currency]
    if receipts.empty:
        return pd.DataFrame(columns=[YOU, TWIN])

    # Start a week before the first purchase, so there's always a price on or
    # before each buy date, even if you bought on a weekend.
    first_buy = receipts["buy_date"].min()
    start = first_buy - pd.Timedelta(days=7)

    # Plain prices for every stock in the group, plus the S&P 500.
    # .ffill() fills holiday gaps with the last price.
    # .bfill() fills any blanks at the very start with the first price.
    tickers = list(receipts["ticker"].unique()) + [BENCHMARK]
    prices = data.get_prices(tickers, start=start, adjusted=False).ffill().bfill()
    sp500 = prices[BENCHMARK]

    # Skip stocks Yahoo had no prices for (a warning was already shown).
    # If that's every stock in the group, there's no line to draw.
    receipts = receipts[receipts["ticker"].isin(prices.columns)]
    if receipts.empty:
        return pd.DataFrame(columns=[YOU, TWIN])

    # Two running totals that start at zero on every day.
    you = pd.Series(0.0, index=prices.index)
    twin = pd.Series(0.0, index=prices.index)

    for _, receipt in receipts.iterrows():
        # True on every day from the buy date onward, False before it.
        owned = prices.index >= receipt["buy_date"]

        # Your line: shares x that day's price, but only on days you owned it.
        # .where(owned, 0.0) means "keep the number where owned is True, else 0".
        you += (prices[receipt["ticker"]] * receipt["shares"]).where(owned, 0.0)

        # The twin's line: on the buy day it spends the same money on the
        # S&P 500, which buys this many "S&P 500 shares"...
        twin_shares = receipt["cost"] / data.price_on(sp500, receipt["buy_date"])
        # ...then holds them.
        twin += (sp500 * twin_shares).where(owned, 0.0)

    history = pd.DataFrame({YOU: you, TWIN: twin})

    # Drop the extra week we fetched before the first purchase.
    return history.loc[history.index >= first_buy]


# ===========================================================================
# 3. THE HEADLINE NUMBERS
# ===========================================================================

def portfolio_summary(portfolio: dict, home_currency: str = HOME_CURRENCY) -> dict:
    """The headline numbers, one set per currency group, plus a combined total.

    Returns a dictionary like:

        {
          "groups": {
            "CAD": {
              "stocks": 2,                   how many different stocks
              "value": 5400.0,               what they're worth now
              "cost": 5000.0,                what you paid
              "gain": 400.0,                 value - cost
              "gain_pct": 8.0,               gain as a percent
              "day_change": -12.0,           move since yesterday's close
              "day_change_pct": -0.2,
              "realized_gain": 150.0,        gains locked in by selling
              "sp500_twin_gain_pct": 6.5,    how the twin did
              "beat_sp500_by_pct": 1.5,      positive means you beat it
            },
            "USD": { ... },
          },
          "combined": {
            "currency": "CAD",
            "value": 12345.0,                everything, converted to CAD
            "fx_rates": {"USD": 1.38},       the rates used
          },
        }

    Each group's amounts are in its own currency. Only "combined" converts.
    """
    positions = positions_table(portfolio, home_currency)
    receipts = _receipts(portfolio)

    # The sells from the trade diary, with each one's currency group.
    trades = pf.trades_table(portfolio)
    sells = trades[trades["action"] == "sell"].copy()
    sells["currency"] = [currency_of(t) for t in sells["ticker"]]

    # Every currency group you own now, or sold from in the past.
    currencies = sorted(set(positions["currency"]) | set(sells["currency"]))

    groups = {}
    for cur in currencies:
        # This group's stocks.
        held = positions[positions["currency"] == cur]

        # Only stocks with a price count toward the totals. A mistyped ticker
        # has no price, so counting what you paid for it would look like a
        # 100% loss. (The S&P 500 twin skips those stocks too.)
        priced = held.dropna(subset=["price"])

        # Add up the group.
        value = priced["value"].sum()
        cost = priced["cost"].sum()
        gain = value - cost
        day_change = priced["day_change"].sum()
        yesterday_value = value - day_change

        # How the S&P 500 twin did: its value today vs the same money spent.
        history = value_history(portfolio, cur)
        twin_now = history[TWIN].iloc[-1] if not history.empty else np.nan
        gain_pct = _pct(gain, cost)
        twin_gain_pct = _pct(twin_now - cost, cost)

        # float(...) turns pandas' special number type into a plain Python
        # number, so it prints as 8121.7 instead of np.float64(8121.7).
        groups[cur] = {
            "stocks": len(held),
            "value": float(value),
            "cost": float(cost),
            "gain": float(gain),
            "gain_pct": float(gain_pct),
            "day_change": float(day_change),
            "day_change_pct": float(_pct(day_change, yesterday_value)),
            "realized_gain": float(sells.loc[sells["currency"] == cur, "realized_gain"].sum()),
            "sp500_twin_gain_pct": float(twin_gain_pct),
            "beat_sp500_by_pct": float(gain_pct - twin_gain_pct),
        }

    # The combined total: every group converted into the home currency.
    rates = {cur: data.get_fx_rate(cur, home_currency) for cur in currencies}
    combined_value = float(sum(groups[cur]["value"] * rates[cur] for cur in currencies))

    return {
        "groups": groups,
        "combined": {
            "currency": home_currency,
            "value": combined_value,
            # Only list the rates that actually converted something.
            "fx_rates": {cur: rate for cur, rate in rates.items() if cur != home_currency},
        },
    }


# ===========================================================================
# 4. CHARTS
# ===========================================================================

def allocation_chart(positions: pd.DataFrame, home_currency: str = HOME_CURRENCY):
    """Donut chart of where your money is. Pass in positions_table(...).

    Slice sizes compare CAD and USD stocks using today's exchange rate.
    """
    fig = px.pie(
        positions,
        names="ticker",          # one slice per stock
        values="weight_pct",     # slice size = its share of the pie
        hole=0.4,                # the hole in the middle makes it a donut
        title=f"Where your money is (sizes compared in {home_currency})",
    )
    # Show the ticker and its percent on each slice.
    fig.update_traces(textinfo="label+percent")
    return fig


def value_chart(history: pd.DataFrame, currency: str):
    """Line chart of you vs your S&P 500 twin. Pass in value_history(...)."""
    fig = px.line(
        history,
        title=f"Your {currency} stocks vs the S&P 500 twin",
        labels={"value": f"Value ({currency})", "variable": "", "date": ""},
    )
    return fig
