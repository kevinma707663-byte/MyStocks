"""
portfolio.py - the notebook where you write down what you own.

WHAT THIS FILE DOES
    Saves and loads your portfolio from a small text file (data/portfolio.json)
    so it's still there next time you open the app. It also records buys
    and sells.

WHAT A PORTFOLIO LOOKS LIKE IN CODE
    A dictionary with two lists:

        holdings - one row per purchase, like a stack of receipts
        trades   - a diary of every buy and sell. The warnings sidebar
                   will read this later to spot habits like panic selling.

    Example of what the file looks like:

        {
          "holdings": [
            {"ticker": "AAPL", "shares": 10.0, "buy_price": 150.0, "buy_date": "2024-01-15", "id": "3f9a1c2e"}
          ],
          "trades": [
            {"date": "2024-01-15", "action": "buy", "ticker": "AAPL", "shares": 10.0, "price": 150.0, "id": "3f9a1c2e"}
          ]
        }

    The "id" is a name tag linking a purchase to its diary line.

WHY EACH PURCHASE IS ITS OWN ROW
    If you buy AAPL twice at different prices, you get two rows. That keeps
    the real buy date and price of each purchase, which later chunks need
    (for example, "you've held this loser for 2 years").

STOCK SPLITS
    Enter shares and prices the way your broker shows them today. If a stock
    split 10-for-1 after you bought it, your broker already shows 10x the
    shares at 1/10th the price, and that's what goes in here.

THE FUNCTIONS OTHER FILES USE
    empty_portfolio()                -> a blank portfolio
    load_portfolio(path)             -> read from file
    save_portfolio(portfolio, path)  -> write to file
    add_holding(portfolio, ...)      -> record a new purchase
    sell_holding(portfolio, ...)     -> record a sale
    remove_holding(portfolio, row)   -> delete a purchase typed by mistake
    holdings_table(portfolio)        -> holdings as a table
    trades_table(portfolio)          -> trade diary as a table

IMPORTANT
    Nothing here saves automatically. Change the portfolio, then call
    save_portfolio() when you're happy with it.
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# json: reads and writes the portfolio file (JSON is a simple text format).
import json

# math: we use math.isfinite to catch blank (NaN) or infinite numbers.
import math

# uuid: makes a short random name tag for each purchase.
import uuid

# date / datetime: for handling buy dates like 2024-01-15.
from datetime import date, datetime

# Path: a safe way to build file paths that works on Windows and Mac.
from pathlib import Path

# pandas: the library for tables of numbers.
import pandas as pd


# ===========================================================================
# SETTINGS
# ===========================================================================

# The folder this whole project lives in.
# __file__ is this file (core/portfolio.py). .parent.parent goes up two levels.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Where the real portfolio is saved, unless someone asks for a different file.
DEFAULT_PATH = PROJECT_ROOT / "data" / "portfolio.json"

# Column names for the tables, so they always come out in the same order.
HOLDING_COLUMNS = ["ticker", "shares", "buy_price", "buy_date"]
TRADE_COLUMNS = ["date", "action", "ticker", "shares", "price", "realized_gain"]

# Computers store decimals slightly imprecisely (0.1 + 0.2 = 0.30000000000000004).
# Any share count smaller than this is treated as zero.
TINY = 1e-9


# ===========================================================================
# CREATE, LOAD AND SAVE
# ===========================================================================

def empty_portfolio() -> dict:
    """A brand-new portfolio with nothing in it."""
    return {"holdings": [], "trades": []}


def load_portfolio(path=DEFAULT_PATH) -> dict:
    """Read the portfolio file. If it doesn't exist yet, start empty."""
    # Make sure path is a Path object (someone might pass plain text).
    path = Path(path)

    # First time using the app? There's no file yet, so hand back a blank one.
    if not path.exists():
        return empty_portfolio()

    # Open the file and turn the JSON text back into a Python dictionary.
    # encoding="utf-8" makes sure odd characters read correctly on Windows.
    with path.open("r", encoding="utf-8") as f:
        portfolio = json.load(f)

    # If someone hand-edited the file and deleted a list, put an empty one back.
    # .setdefault only adds it if it's missing.
    portfolio.setdefault("holdings", [])
    portfolio.setdefault("trades", [])
    return portfolio


def save_portfolio(portfolio: dict, path=DEFAULT_PATH) -> None:
    """Write the portfolio to its file.

    It writes to a temporary file first and then swaps it in. If the computer
    crashes halfway through writing, your old file is still safe.
    """
    # Make sure path is a Path object.
    path = Path(path)

    # Create the folder (e.g. data/) if it doesn't exist yet.
    path.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: write everything to "portfolio.tmp".
    # indent=2 makes the file nicely spaced so humans can read it.
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(portfolio, f, indent=2)

    # Step 2: swap the temp file in place of the real one in one move.
    temp.replace(path)


# ===========================================================================
# INPUT CHECKERS (shared by buying and selling)
#
# Each one either hands back a clean value or raises a ValueError with a
# plain-English message, which a Streamlit form can show with st.error().
# ===========================================================================

def _clean_ticker(ticker) -> str:
    """Remove spaces and make CAPITALS ("aapl " -> "AAPL"). Blank isn't allowed."""
    ticker = str(ticker).strip().upper()
    if not ticker:
        raise ValueError("Ticker can't be blank.")
    return ticker


def _positive_number(value, label: str) -> float:
    """Turn the input into a decimal number and make sure it's above zero.

    label is the friendly name used in the error message, like "Shares".
    """
    # Convert to a decimal number. If someone typed "ten", this fails.
    try:
        number = float(value)
    except (TypeError, ValueError):
        # "from None" hides Python's confusing internal error and shows only ours.
        raise ValueError(f"{label} must be a number.") from None

    # float() also accepts "nan" (a blank number) and "inf" (infinity).
    # Neither is a real amount, so turn them away too.
    if not math.isfinite(number):
        raise ValueError(f"{label} must be a number.")

    # Zero or negative makes no sense for shares or prices.
    if number <= 0:
        raise ValueError(f"{label} must be more than 0.")
    return number


def _to_date(value) -> date:
    """Turn whatever we were given into a proper date.

    Accepts: "2024-01-15", a date, a datetime (date + time), or None.
    None or blank means "today".
    """
    # Nothing given: use today's date.
    if value is None or value == "":
        return date.today()

    # A datetime has a time attached. Keep just the date part.
    # (This check must come before the next one, because a datetime
    # also counts as a date in Python.)
    if isinstance(value, datetime):
        return value.date()

    # Already a date (e.g. from a Streamlit date picker): use it as-is.
    if isinstance(value, date):
        return value

    # Otherwise assume it's text like "2024-01-15" and convert it.
    return date.fromisoformat(str(value).strip())


def _past_date(value, label: str) -> date:
    """Like _to_date, but with friendly errors and no future dates allowed."""
    try:
        when = _to_date(value)
    except ValueError:
        raise ValueError(f"{label} must look like 2024-01-15.") from None

    # No time travel.
    if when > date.today():
        raise ValueError(f"{label} can't be in the future.")
    return when


# ===========================================================================
# BUYING
# ===========================================================================

def add_holding(portfolio: dict, ticker: str, shares, buy_price, buy_date=None) -> dict:
    """Write down a new purchase and log it in the trade diary.

    ticker     like "AAPL" or "RY.TO" (Canadian stocks end in .TO)
    shares     how many you bought. Fractions like 2.5 are fine.
    buy_price  what you paid per share
    buy_date   "YYYY-MM-DD" or a date. Leave it out to use today.

    Returns the same portfolio, now with the new purchase added.
    """
    # Check every input. Each checker stops here with a clear message if
    # something is wrong.
    ticker = _clean_ticker(ticker)
    shares = _positive_number(shares, "Shares")
    buy_price = _positive_number(buy_price, "Buy price")
    when = _past_date(buy_date, "Buy date")

    # A short random name tag, like "3f9a1c2e". The receipt and its diary
    # line both get it, so remove_holding() always deletes the right pair.
    tag = uuid.uuid4().hex[:8]

    # Add a "receipt" to the holdings list.
    # .isoformat() turns the date into text like "2024-01-15" for the file.
    portfolio["holdings"].append(
        {"ticker": ticker, "shares": shares, "buy_price": buy_price, "buy_date": when.isoformat(), "id": tag}
    )

    # Add a matching line to the trade diary.
    portfolio["trades"].append(
        {"date": when.isoformat(), "action": "buy", "ticker": ticker, "shares": shares, "price": buy_price, "id": tag}
    )
    return portfolio


# ===========================================================================
# SELLING
# ===========================================================================

def sell_holding(portfolio: dict, ticker: str, shares, sell_price, sell_date=None) -> dict:
    """Sell some shares of a stock you own, and log it in the trade diary.

    ticker      the stock you're selling
    shares      how many shares you sold
    sell_price  what you got per share
    sell_date   "YYYY-MM-DD" or a date. Leave it out to use today.

    HOW THE GAIN IS WORKED OUT (the "average cost" method)
        average cost = total you paid / total shares you own
        gain         = (sell price - average cost) x shares sold
        This is the same way Canada works out gains for taxes.

    WHAT HAPPENS TO YOUR RECEIPTS
        Every receipt for this stock shrinks by the same fraction. Sell a
        quarter of your shares, and each receipt loses a quarter of its
        shares. That keeps your average cost the same, which is the whole
        idea of the average cost method. Sell everything, and the receipts
        disappear.

    A SALE DATED IN THE PAST
        Only purchases made on or before the sell date count, both for how
        many shares you can sell and for the average cost. Shares you bought
        later aren't touched.

    Returns the same portfolio. The locked-in gain (or loss, if negative)
    is saved in the trade diary under "realized_gain".
    """
    # --- Check the inputs --------------------------------------------------
    ticker = _clean_ticker(ticker)
    shares = _positive_number(shares, "Shares")
    sell_price = _positive_number(sell_price, "Sell price")
    when = _past_date(sell_date, "Sell date")

    # Find every receipt for this stock.
    receipts = [h for h in portfolio["holdings"] if h["ticker"] == ticker]
    if not receipts:
        raise ValueError(f"You don't own any {ticker}.")

    # You can't sell before you first bought.
    first_buy = min(date.fromisoformat(h["buy_date"]) for h in receipts)
    if when < first_buy:
        raise ValueError(f"Sell date can't be before your first {ticker} purchase on {first_buy}.")

    # Only shares bought ON OR BEFORE the sell date can be sold. A sale
    # dated in February can't use shares you bought in March.
    receipts = [h for h in receipts if date.fromisoformat(h["buy_date"]) <= when]

    # You can't sell more than you owned on that day.
    owned = sum(h["shares"] for h in receipts)
    if shares > owned + TINY:
        raise ValueError(f"You only owned {owned:g} shares of {ticker} on {when}.")

    # --- Work out the gain ---------------------------------------------------
    total_paid = sum(h["shares"] * h["buy_price"] for h in receipts)
    average_cost = total_paid / owned
    realized_gain = (sell_price - average_cost) * shares

    # --- Shrink the receipts -------------------------------------------------
    # The fraction of shares you keep. Selling 25 of 100 keeps 0.75.
    keep = (owned - shares) / owned
    for h in receipts:
        h["shares"] *= keep

    # Throw away receipts that are now (practically) zero shares.
    portfolio["holdings"] = [
        h for h in portfolio["holdings"]
        if not (h["ticker"] == ticker and h["shares"] < TINY)
    ]

    # --- Write it in the trade diary -----------------------------------------
    portfolio["trades"].append(
        {
            "date": when.isoformat(),
            "action": "sell",
            "ticker": ticker,
            "shares": shares,
            "price": sell_price,
            "realized_gain": round(realized_gain, 2),  # rounded to the cent
        }
    )
    return portfolio


# ===========================================================================
# FIXING MISTAKES
# ===========================================================================

def remove_holding(portfolio: dict, row: int) -> dict:
    """Delete one purchase you typed by mistake.

    row  the purchase's row number in holdings_table(), starting at 0

    Its matching "buy" line in the trade diary is deleted too, because a
    typo isn't a real trade. Use sell_holding() for real sales.
    """
    # Make sure that row number exists.
    if not 0 <= row < len(portfolio["holdings"]):
        raise ValueError(f"There's no purchase in row {row}.")

    # Take the receipt out of the holdings list.
    receipt = portfolio["holdings"].pop(row)
    trades = portfolio["trades"]

    # Find its matching diary line.
    if "id" in receipt:
        # Purchases have a name tag shared with their diary line: use that.
        matches = [i for i, t in enumerate(trades) if t["action"] == "buy" and t.get("id") == receipt["id"]]
    else:
        # Purchases saved before name tags existed: same stock, date and price.
        # If two buys share all three, prefer the one with the same shares too.
        matches = [
            i for i, t in enumerate(trades)
            if t["action"] == "buy" and t["ticker"] == receipt["ticker"]
            and t["date"] == receipt["buy_date"] and t["price"] == receipt["buy_price"]
        ]
        same_shares = [i for i in matches if abs(trades[i]["shares"] - receipt["shares"]) < TINY]
        matches = same_shares or matches

    if matches:
        del trades[matches[0]]  # only remove one line
    return portfolio


# ===========================================================================
# SHOWING THE PORTFOLIO AS TABLES
# ===========================================================================

def holdings_table(portfolio: dict) -> pd.DataFrame:
    """Your holdings as a table, ready to print or to show with st.dataframe()."""
    # columns=... keeps the column order fixed, even when the list is empty.
    return pd.DataFrame(portfolio["holdings"], columns=HOLDING_COLUMNS)


def trades_table(portfolio: dict) -> pd.DataFrame:
    """The trade diary as a table. Buys have a blank realized_gain."""
    return pd.DataFrame(portfolio["trades"], columns=TRADE_COLUMNS)
