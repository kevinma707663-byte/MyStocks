"""
warnings_sidebar.py - the warnings sidebar: "Am I falling into a common trap?"

WHAT THIS FILE DOES
    Before you record a buy or a sell, it checks for the classic mistakes
    investors make and gives you friendly, plain-English warnings. It is a
    helper on your shoulder, never a gatekeeper: it NEVER blocks a trade.
    If the market data it needs isn't there (Yahoo is down, or the ticker
    has a typo), you get a "Couldn't check" heads-up instead of an error.
    Real input mistakes, like selling more than you own or typing "ten"
    for shares, still stop with a clear message, as they always have.

    It also has standing warnings, which look at what you already own
    without any trade (for example, a loser you've held for a long time).

THE TRAPS IT LOOKS FOR
    When you BUY
      Chasing (FOMO)        buying right after a big run-up, out of fear of
                            missing out. Prices that ran up fast often cool off.
      Averaging down        buying more of a stock you're already losing money
                            on, hoping to "get back to even" faster.
      Too much in one place after this buy, one stock or one sector would be
                            a very big slice of your money. Skipped for your
                            first stock (every portfolio starts at 100% in one
                            stock) and for adding to your only stock. MyRisks
                            still flags a one-stock portfolio as high risk.
      Superficial loss      buying back a stock within 30 days of selling it at
                            a loss. In Canada that loss can't be claimed for tax.

    When you SELL
      Loss aversion         selling a winner while keeping losers. People hate
                            locking in a loss, so they sell what's up and hold
                            what's down: the opposite of what usually helps.
      Panic selling         selling right after a sharp drop in the stock or
                            the whole market.
      Quick flip            selling shares you bought less than 30 days ago.
      Superficial loss      selling at a loss when you bought the same stock in
                            the last 30 days (the same Canadian tax rule).

    Any trade
      Overtrading           lots of trades in the last 30 days. Every trade costs
                            fees and attention, and busy traders usually do worse.

    Standing warnings (no trade needed)
      Holding a loser       a stock down a lot that you've held over a year.
                            Ask yourself: would I buy it today at this price?
      Too much in one place one stock or one sector is a very big slice already.
                            Only checked once you own 2 or more stocks.
      Ticker not found      a stock with no price, usually a typo. It's left out
                            of your totals and the other checks until it's fixed.

TWO LEVELS
    "heads-up"   worth a second thought
    "caution"    a well-known trap; think it through before trading

THESE ARE SUGGESTIONS, NOT RULES, AND NOT TAX ADVICE.

THE FUNCTIONS OTHER FILES USE
    check_trade(portfolio, action, ticker, shares, price)  -> warnings for one trade
    trade(portfolio, action, ticker, shares, price)        -> check, then record the trade
    standing_warnings(portfolio)                           -> warnings about what you already own
    warnings_table(warnings)                               -> the warnings as a table
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# date / timedelta: for "in the last 30 days" checks.
from datetime import date, timedelta

# warnings: Python's own module. We use it to hide other sections' messages
# while borrowing their numbers. (This file has a different name on purpose,
# so it doesn't clash with it.)
import warnings

# pandas: the library for tables of numbers.
import pandas as pd

# Our own files. The dot means "from this same core/ folder".
from . import data
from . import portfolio as pf
from . import my_stocks as ms
from . import technicals as ta


# ===========================================================================
# SETTINGS
# ===========================================================================

RUN_UP_PCT = 30            # up this much in 3 months counts as a big run-up
OVERBOUGHT_RSI = 70        # RSI above this = ran up too fast (Part 3D)
AVERAGING_DOWN_PCT = -15   # buying more of a stock down this much or more
MAX_STOCK_PCT = 25         # one stock above this share of your money
MAX_SECTOR_PCT = 40        # one sector above this share of your money
WINNER_PCT = 10            # a "winner" is up at least this much
LOSER_PCT = -10            # a "loser" is down at least this much
PANIC_STOCK_DROP_PCT = -10 # the stock fell this much in the last 5 trading days
PANIC_MARKET_DROP_PCT = -5 # the S&P 500 fell this much in the last 5 trading days
QUICK_FLIP_DAYS = 30       # selling shares bought less than this many days ago
TAX_WINDOW_DAYS = 30       # Canada's superficial loss rule: 30 days either side
BUSY_TRADES = 5            # this many trades in 30 days counts as overtrading
LONG_LOSER_PCT = -20       # a long-held loser is down at least this much...
LONG_LOSER_DAYS = 365      # ...and held at least this long

BENCHMARK = "SPY"


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _warning(trap: str, level: str, message: str, tip: str) -> dict:
    """One warning, in the shape every function here returns."""
    return {"trap": trap, "level": level, "message": message, "tip": tip}


def _to_day(value) -> date:
    """A trade date as a real date. None means today."""
    if value is None or value == "":
        return date.today()
    return pd.Timestamp(value).date()


def _change_pct(ticker: str, trading_days: int) -> float:
    """How much a price moved over the last `trading_days` days, in %."""
    prices = data.get_prices(ticker, period="6mo")[ticker].dropna()
    if len(prices) <= trading_days:
        return float("nan")
    return float((prices.iloc[-1] / prices.iloc[-1 - trading_days] - 1) * 100)


def _trades_in_window(portfolio: dict, day: date, days: int) -> pd.DataFrame:
    """Trades from the diary within `days` days of `day` (before or after)."""
    trades = pf.trades_table(portfolio)
    if trades.empty:
        return trades
    when = pd.to_datetime(trades["date"]).dt.date
    return trades[(when >= day - timedelta(days=days)) & (when <= day + timedelta(days=days))]


def _values_in_home(positions: pd.DataFrame) -> pd.Series:
    """Each position's value converted into Canadian dollars, by ticker."""
    rates = {c: data.get_fx_rate(c, ms.HOME_CURRENCY) for c in positions["currency"].unique()}
    return (positions["value"] * positions["currency"].map(rates)).set_axis(positions["ticker"])


# ===========================================================================
# THE CHECKS FOR ONE TRADE
# ===========================================================================

def check_trade(portfolio: dict, action: str, ticker: str, shares, price, trade_date=None) -> list:
    """Warnings for one trade, BEFORE it's recorded. Never blocks anything.

    portfolio   your portfolio (from portfolio.py, or st.session_state.portfolio)
    action      "buy" or "sell"
    ticker      like "NVDA" or "RY.TO"
    shares      how many shares
    price       the price per share
    trade_date  "YYYY-MM-DD" or a date. Leave it out for today.

    Returns a list of warnings. Each one is a dictionary:
        {"trap": "Chasing (FOMO)", "level": "caution",
         "message": "what's going on, in plain English",
         "tip": "a question or idea to think about"}
    An empty list means no traps spotted.
    """
    action = action.strip().lower()
    if action not in ("buy", "sell"):
        raise ValueError('Action must be "buy" or "sell".')
    ticker = data.clean_tickers(ticker)[0]
    shares = pf._positive_number(shares, "Shares")      # "ten" -> a plain-English error
    price = pf._positive_number(price, "Price")
    day = _to_day(trade_date)

    found = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")        # other sections' messages aren't needed here
        try:
            # Only stocks with a price can be checked. A mistyped ticker has none,
            # and standing_warnings() already flags it.
            positions = ms.positions_table(portfolio).dropna(subset=["price"])
            mine = positions[positions["ticker"] == ticker]

            if action == "buy":
                found += _buy_checks(portfolio, positions, mine, ticker, shares, price, day)
            else:
                found += _sell_checks(portfolio, positions, mine, ticker, shares, price, day)
        except Exception:
            # These checks need market data. If it isn't there (Yahoo is down,
            # or the ticker has a typo), say so instead of stopping: the
            # sidebar must never block a trade. "Exception" catches every
            # kind of failure on purpose, because a download can fail in many ways.
            found = [_warning(
                "Couldn't check", "heads-up",
                f"There's no market data for {ticker} right now, so this trade wasn't checked for traps.",
                "Check the spelling (Canadian stocks need .TO at the end, like RY.TO). "
                "If it's right, Yahoo may be busy: try again in a minute.",
            )]

        # --- Any trade: overtrading (only needs your diary, so it always runs) --------------------------------------------
        recent = _trades_in_window(portfolio, day, 30)
        recent = recent[pd.to_datetime(recent["date"]).dt.date <= day]     # only the past 30 days
        if len(recent) + 1 >= BUSY_TRADES:
            found.append(_warning(
                "Overtrading", "heads-up",
                f"This would be trade number {len(recent) + 1} in the last 30 days.",
                "Every trade costs fees and attention, and busy traders usually do worse than patient ones. "
                "Is this trade part of a plan?",
            ))
    return found


def _buy_checks(portfolio, positions, mine, ticker, shares, price, day) -> list:
    found = []

    # --- Chasing (FOMO): a big run-up or an overbought RSI -------------------------
    run_up = _change_pct(ticker, 63)          # about 3 months of trading days
    try:
        rsi_reading = ta.technical_summary(ticker)["signals"].loc["RSI", "reading"]
        rsi = float(rsi_reading.split(",")[0])
    except Exception:
        rsi = float("nan")
    if run_up >= RUN_UP_PCT or rsi > OVERBOUGHT_RSI:
        detail = f"It's up {run_up:.0f}% in about 3 months" if run_up >= RUN_UP_PCT else "It's up a lot recently"
        if rsi > OVERBOUGHT_RSI:
            detail += f", and its RSI is {rsi:.0f} (above {OVERBOUGHT_RSI} means it ran up too fast)"
        found.append(_warning(
            "Chasing (FOMO)", "caution",
            f"{detail}.",
            "Buying because a price has been rising fast is the fear of missing out. Prices that run up "
            "quickly often cool off. Would you still buy it if it hadn't moved?",
        ))

    # --- Averaging down: buying more of a stock you're losing money on -------------
    if not mine.empty and mine["gain_pct"].iloc[0] <= AVERAGING_DOWN_PCT:
        found.append(_warning(
            "Averaging down", "caution",
            f"You're already down {abs(mine['gain_pct'].iloc[0]):.0f}% on {ticker}, and this buys more.",
            "Buying more lowers your average cost, which can feel like getting back to even faster. "
            "That's the break-even trap. Would you buy it today if you didn't already own it?",
        ))

    # --- Too much in one place, AFTER this buy -------------------------------------
    if not positions.empty and not (len(positions) == 1 and not mine.empty):
        values = _values_in_home(positions)
        currency = ms.currency_of(ticker)
        added = shares * price * data.get_fx_rate(currency, ms.HOME_CURRENCY)
        after = values.copy()
        after[ticker] = after.get(ticker, 0) + added
        stock_pct = after[ticker] / after.sum() * 100
        if stock_pct > MAX_STOCK_PCT:
            found.append(_warning(
                "Too much in one stock", "caution",
                f"After this buy, {ticker} would be {stock_pct:.0f}% of your money.",
                f"If {ticker} has a bad year, it would hit your whole portfolio hard. "
                f"Many investors keep any one stock under {MAX_STOCK_PCT}%.",
            ))
        sectors = dict(zip(positions["ticker"], positions["sector"]))
        sectors[ticker] = data.get_info(ticker)["sector"]
        sector = sectors[ticker]
        if sector:
            in_sector = sum(v for t, v in after.items() if sectors.get(t) == sector)
            sector_pct = in_sector / after.sum() * 100
            if sector_pct > MAX_SECTOR_PCT:
                found.append(_warning(
                    "Too much in one sector", "heads-up",
                    f"After this buy, {sector_pct:.0f}% of your money would be in {sector}.",
                    "Stocks in the same industry often fall together. Would a different sector spread the risk?",
                ))

    # --- Superficial loss: buying back within 30 days of selling at a loss ---------
    window = _trades_in_window(portfolio, day, TAX_WINDOW_DAYS)
    loss_sales = window[(window["action"] == "sell") & (window["ticker"] == ticker) & (window["realized_gain"] < 0)]
    if not loss_sales.empty:
        found.append(_warning(
            "Superficial loss (tax)", "heads-up",
            f"You sold {ticker} at a loss on {loss_sales['date'].iloc[-1]}, within 30 days of this buy.",
            "In Canada, buying back the same stock within 30 days of selling it at a loss can stop you "
            "claiming that loss for tax (the superficial loss rule). This isn't tax advice: check with an accountant.",
        ))
    return found


def _sell_checks(portfolio, positions, mine, ticker, shares, price, day) -> list:
    found = []
    if mine.empty:
        return found                       # selling what you don't own: portfolio.py will say so

    gain_pct = (price / mine["avg_cost"].iloc[0] - 1) * 100

    # --- Loss aversion: selling a winner while holding losers -----------------------
    losers = positions[(positions["ticker"] != ticker) & (positions["gain_pct"] <= LOSER_PCT)]
    if gain_pct >= WINNER_PCT and not losers.empty:
        names = ", ".join(f"{t} ({g:.0f}%)" for t, g in zip(losers["ticker"], losers["gain_pct"]))
        found.append(_warning(
            "Loss aversion", "caution",
            f"You're selling {ticker} at a {gain_pct:.0f}% gain while holding losers: {names}.",
            "People hate locking in a loss, so they sell winners early and hold losers too long, hoping "
            "to get back to even. Is this the stock you'd really want to sell?",
        ))

    # --- Panic selling: right after a sharp drop -----------------------------------
    stock_drop = _change_pct(ticker, 5)
    market_drop = _change_pct(BENCHMARK, 5)
    if stock_drop <= PANIC_STOCK_DROP_PCT or market_drop <= PANIC_MARKET_DROP_PCT:
        what = (f"{ticker} fell {abs(stock_drop):.0f}% in the last 5 trading days" if stock_drop <= PANIC_STOCK_DROP_PCT
                else f"the S&P 500 fell {abs(market_drop):.0f}% in the last 5 trading days")
        found.append(_warning(
            "Panic selling", "caution",
            f"You're selling right after a sharp drop: {what}.",
            "Selling in a hurry after a fall often locks in the worst price. Has anything changed "
            "about the business, or just the price?",
        ))

    # --- Quick flip: shares bought less than 30 days ago ----------------------------
    receipts = pf.holdings_table(portfolio)
    newest = pd.to_datetime(receipts.loc[receipts["ticker"] == ticker, "buy_date"]).max().date()
    held_days = (day - newest).days
    if held_days < QUICK_FLIP_DAYS:
        found.append(_warning(
            "Quick flip", "heads-up",
            f"You bought {ticker} only {held_days} days ago.",
            "Quick trades are mostly guesses about short-term moves. Was this the plan when you bought it?",
        ))

    # --- Superficial loss: selling at a loss with a buy in the last 30 days ----------
    if gain_pct < 0:
        window = _trades_in_window(portfolio, day, TAX_WINDOW_DAYS)
        recent_buys = window[(window["action"] == "buy") & (window["ticker"] == ticker)]
        if not recent_buys.empty:
            found.append(_warning(
                "Superficial loss (tax)", "heads-up",
                f"You're selling {ticker} at a loss, and you bought it within the last 30 days.",
                "In Canada, a loss on shares bought within 30 days before or after the sale can be denied for "
                "tax (the superficial loss rule). This isn't tax advice: check with an accountant.",
            ))
    return found


# ===========================================================================
# CHECK, THEN RECORD
# ===========================================================================

def trade(portfolio: dict, action: str, ticker: str, shares, price, trade_date=None) -> tuple:
    """Check a trade for traps, then record it anyway.

    Returns (portfolio, warnings). The trade is always recorded: the warnings
    are suggestions only. Mistakes like selling more than you own still raise
    a ValueError from portfolio.py, as before.
    """
    found = check_trade(portfolio, action, ticker, shares, price, trade_date)
    if action.strip().lower() == "buy":
        pf.add_holding(portfolio, ticker, shares, price, trade_date)
    else:
        pf.sell_holding(portfolio, ticker, shares, price, trade_date)
    return portfolio, found


# ===========================================================================
# STANDING WARNINGS: WHAT YOU ALREADY OWN
# ===========================================================================

def standing_warnings(portfolio: dict) -> list:
    """Warnings about what you already own, no trade needed. Good for an always-on sidebar."""
    found = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        positions = ms.positions_table(portfolio)
        if positions.empty:
            return found

        # --- A ticker with no price (usually a typo) ------------------------------------
        for ticker in positions.loc[positions["price"].isna(), "ticker"]:
            found.append(_warning(
                "Ticker not found", "caution",
                f"There's no price for {ticker}, so it's left out of your totals and checks.",
                "Check the spelling. Canadian stocks need .TO at the end, like RY.TO.",
            ))
        # The checks below only work on stocks with a price.
        positions = positions.dropna(subset=["price"])

        receipts = pf.holdings_table(portfolio)
        receipts["buy_date"] = pd.to_datetime(receipts["buy_date"])

        # --- Holding a loser for a long time ------------------------------------------
        for _, row in positions[positions["gain_pct"] <= LONG_LOSER_PCT].iterrows():
            first_buy = receipts.loc[receipts["ticker"] == row["ticker"], "buy_date"].min().date()
            held = (date.today() - first_buy).days
            if held >= LONG_LOSER_DAYS:
                found.append(_warning(
                    "Holding a loser", "caution",
                    f"{row['ticker']} is down {abs(row['gain_pct']):.0f}%, and you first bought it {held // 30} months ago.",
                    "Waiting to get back to even is the break-even trap. The price you paid doesn't matter "
                    "to the market. Would you buy it today at this price?",
                ))

        # --- Too much in one stock or one sector ------------------------------------------
        if len(positions) > 1:
            biggest = positions.loc[positions["weight_pct"].idxmax()]
            if biggest["weight_pct"] > MAX_STOCK_PCT:
                found.append(_warning(
                    "Too much in one stock", "heads-up",
                    f"{biggest['ticker']} is {biggest['weight_pct']:.0f}% of your money.",
                    f"Many investors keep any one stock under {MAX_STOCK_PCT}%. MyRisks shows the full picture.",
                ))
            by_sector = positions.dropna(subset=["sector"]).groupby("sector")["weight_pct"].sum()
            if len(by_sector) and by_sector.max() > MAX_SECTOR_PCT:
                found.append(_warning(
                    "Too much in one sector", "heads-up",
                    f"{by_sector.max():.0f}% of your money is in {by_sector.idxmax()}.",
                    "Stocks in the same industry often fall together. MyRisks shows the full picture.",
                ))

        # --- Overtrading lately -----------------------------------------------------------
        recent = _trades_in_window(portfolio, date.today(), 30)
        recent = recent[pd.to_datetime(recent["date"]).dt.date <= date.today()]
        if len(recent) >= BUSY_TRADES:
            found.append(_warning(
                "Overtrading", "heads-up",
                f"You've made {len(recent)} trades in the last 30 days.",
                "Busy traders usually do worse than patient ones. Is each trade part of a plan?",
            ))
    return found


def warnings_table(found: list) -> pd.DataFrame:
    """The warnings as a table, "caution" first. Empty table if there are none."""
    table = pd.DataFrame(found, columns=["trap", "level", "message", "tip"])
    return table.sort_values("level", key=lambda s: s.map({"caution": 0, "heads-up": 1})).reset_index(drop=True)
