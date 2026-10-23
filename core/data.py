"""
data.py - the price fetcher.

WHAT THIS FILE DOES
    Think of this file as the only kid allowed to call the store.
    Every other part of MyPortfolio asks this file for numbers, and this file
    gets them from Yahoo Finance using the free `yfinance` library.

WHY IT'S SEPARATE
    If we ever switch to a different data provider, this is the only file
    we have to change. Nothing else in the app talks to the internet.

THE FUNCTIONS OTHER FILES USE
    get_prices(tickers, period)       -> table of daily prices
    get_price_bars(ticker, period)    -> daily open, high, low, close and volume
    get_latest_prices(tickers)        -> today's price for each ticker
    get_info(ticker)                  -> company facts (sector, P/E, etc.)
    get_fx_rate("USD", "CAD")         -> today's exchange rate
    get_financial_statements(ticker)  -> income statement, balance sheet, cash flow
    price_on(prices, day)             -> the price on a day, or the closest day before
    get_group_companies(kind, key)    -> the biggest companies in an industry or sector
    get_us_10y_yield()                -> US 10-year government bond yield, daily
    get_us_inflation()                -> US inflation (yearly price rise), monthly
    get_us_gdp_growth()               -> US economic growth, quarterly
    get_analyst_data(ticker)          -> analyst ratings, price targets, rating changes, forecasts

WHERE THE ECONOMY NUMBERS COME FROM
    10-year yield  Yahoo Finance (ticker ^TNX)
    Inflation      US Bureau of Labor Statistics (BLS), the official source
    GDP growth     US Bureau of Economic Analysis, through DBnomics, a free
                   site that mirrors official statistics
    If those fail, we try the St. Louis Fed's FRED site as a backup.

HOW PROBLEMS ARE REPORTED
    Problems such as an unknown ticker are reported with `warnings.warn`.
    In Jupyter they show up as a pink box under the cell.
    In Streamlit the partner can catch them and show them with st.warning().
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# time: lets us check the clock, so we know how old a saved answer is.
import time

# warnings: a polite way to say "something looks off" without crashing.
import warnings

# io, json, urllib: built-in tools for downloading web pages and reading
# the CSV and JSON text that the economy websites send back.
import io
import json
import urllib.request

# pandas: the library for tables of numbers (called DataFrames).
import pandas as pd

# logging: controls which libraries are allowed to print messages.
import logging

# yfinance: the free library that downloads data from Yahoo Finance.
import yfinance as yf

# yfinance prints its own scary-looking errors (like "HTTP Error 404") for
# bad tickers. We already give a friendly warning ourselves, so we tell
# yfinance to stay quiet unless something truly critical happens.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)


# ===========================================================================
# SETTINGS
# ===========================================================================

# How long (in seconds) to remember an answer before asking Yahoo again.
# 60 seconds x 60 minutes = 1 hour. This keeps the app fast and stops us
# from sending Yahoo hundreds of identical requests.
CACHE_SECONDS = 60 * 60

# Economy numbers only change monthly or quarterly, so remember them for
# 12 hours. This also keeps us under the labour statistics site's limit
# of about 25 free requests a day.
ECONOMY_CACHE_SECONDS = 12 * 60 * 60

# The "memory box" (cache). It's a dictionary that looks like:
#     { the question we asked : (the time we got the answer, the answer) }
# The underscore at the front means "private, only used inside this file".
_cache: dict = {}

# Yahoo sends back ~150 facts per company with confusing names.
# We only keep the useful ones and give them friendlier names.
# Format is:  "our friendly name": "Yahoo's name for it"
INFO_FIELDS = {
    "name": "shortName",                               # e.g. "Apple Inc."
    "sector": "sector",                                # e.g. "Technology"
    "industry": "industry",                            # e.g. "Consumer Electronics"
    "currency": "currency",                            # currency the stock TRADES in, e.g. "USD"
    "financial_currency": "financialCurrency",         # currency its financial statements use
    "market_cap": "marketCap",                        # total value of the company in dollars
    "pe_ratio": "trailingPE",                          # price / last year's earnings per share
    "forward_pe": "forwardPE",                         # price / NEXT year's expected earnings
    "dividend_yield": "trailingAnnualDividendYield",   # yearly dividends / price. 0.02 means 2%
    "beta": "beta",                                    # how much it swings vs the market. 1 = same as market
    "industry_key": "industryKey",                     # Yahoo's code for the industry, e.g. "semiconductors"
    "sector_key": "sectorKey",                         # Yahoo's code for the sector, e.g. "technology"
    "insider_ownership": "heldPercentInsiders",        # share of stock owned by insiders. 0.04 means 4%
    "shares_outstanding": "sharesOutstanding",         # how many shares exist in total
}


# ===========================================================================
# SMALL HELPERS (used inside this file)
# ===========================================================================

def _remember(key, fetch, max_age=CACHE_SECONDS):
    """Return a saved answer if it's still fresh, otherwise call fetch() and save it.

    key      a label for the question, like ("prices", ("AAPL",), "1y")
    fetch    a function that actually goes and gets the answer from the internet
    max_age  how many seconds an answer stays fresh. One hour unless told otherwise.

    If fetch() fails (raises an error), nothing is saved, so the next call
    will try again instead of remembering the failure.
    """
    # Look in the memory box for this question. .get() returns None if it's not there.
    saved = _cache.get(key)

    # If we found something, check whether it's still fresh.
    if saved is not None:
        saved_at, value = saved                      # unpack (time saved, answer)
        age_in_seconds = time.time() - saved_at      # how long ago we saved it
        if age_in_seconds < max_age:                 # still fresh?
            return value                             # yes: reuse it, no internet needed

    # Not saved or too old: go get a fresh answer.
    value = fetch()

    # Save the fresh answer along with the current time.
    _cache[key] = (time.time(), value)
    return value


def clear_cache() -> None:
    """Forget every saved answer, so the next call downloads fresh data.

    Handy for a "Refresh prices" button in the Streamlit app.
    """
    _cache.clear()


def clean_tickers(tickers) -> list[str]:
    """Tidy up whatever the user typed into a neat list of tickers.

    Examples:
        "aapl"                     -> ["AAPL"]
        ["aapl", " msft ", "AAPL"] -> ["AAPL", "MSFT"]   (spaces gone, duplicate gone)
    """
    # If we got a single ticker as text, wrap it in a list so the loop below works.
    if isinstance(tickers, str):
        tickers = [tickers]

    cleaned = []                                     # start with an empty list
    for t in tickers:                                # look at each ticker one by one
        t = str(t).strip().upper()                   # remove spaces, make CAPITALS
        if t and t not in cleaned:                   # skip blanks and duplicates
            cleaned.append(t)                        # keep it

    # If nothing usable is left, stop with a clear message.
    if not cleaned:
        raise ValueError("Give me at least one ticker, like 'AAPL'.")
    return cleaned


# ===========================================================================
# THE THREE FUNCTIONS THE REST OF THE APP USES
# ===========================================================================

def get_prices(tickers, period: str = "1y", start=None, adjusted: bool = True) -> pd.DataFrame:
    """Daily closing prices.

    Returns a table where each ROW is a trading day and each COLUMN is a ticker:

                    AAPL     MSFT
        date
        2026-10-19  231.50   420.10
        2026-10-20  233.20   418.75

    tickers   one ticker like "AAPL" or a list like ["AAPL", "RY.TO"]
    period    how far back to go: "5d", "1mo", "3mo", "6mo", "1y", "2y",
              "5y", "10y" or "max"
    start     optional first day like "2024-01-15". If given, it replaces period.
    adjusted  True:  prices pretend every dividend was reinvested. This is
                     best for comparing returns, so the analysis, optimizer
                     and risk sections use it.
              False: the plain price you'd see on the news or at your broker.
                     MyStocks uses this so its numbers match your statements.

    Either way, stock splits are always accounted for.
    """
    # Tidy up the tickers first ("aapl " -> "AAPL").
    tickers = clean_tickers(tickers)

    # Turn any kind of date into plain text like "2024-01-15",
    # so it can be part of the memory box's label.
    if start is not None:
        start = str(pd.Timestamp(start).date())

    # This inner function does the real download. We hand it to _remember(),
    # which only calls it if we don't already have a fresh answer saved.
    def fetch():
        # Ask Yahoo for the data.
        #   start or period  -> how far back to go
        #   auto_adjust      -> whether to bake dividends into the prices
        #   progress=False   -> don't print a progress bar
        if start is not None:
            raw = yf.download(tickers, start=start, auto_adjust=adjusted, progress=False)
        else:
            raw = yf.download(tickers, period=period, auto_adjust=adjusted, progress=False)

        # If Yahoo sent back nothing at all, stop with a clear message.
        if raw is None or raw.empty:
            raise ValueError(f"No prices found for {tickers}. Check the tickers.")

        # Yahoo sends Open, High, Low, Close and Volume. We only want Close.
        close = raw["Close"]

        # Some yfinance versions hand back a single column (a "Series") when
        # you ask for one ticker. Turn it into a proper table so the shape is
        # always the same no matter how many tickers we asked for.
        if isinstance(close, pd.Series):
            close = close.to_frame(name=tickers[0])

        # Remove any ticker column that is completely empty (bad ticker).
        close = close.dropna(axis="columns", how="all")

        # Work out which tickers we actually got data for.
        found = [t for t in tickers if t in close.columns]
        if not found:
            raise ValueError(f"No prices found for {tickers}. Check the tickers.")

        # Warn (but don't crash) about any tickers that came back empty.
        missing = [t for t in tickers if t not in found]
        if missing:
            warnings.warn(f"No price data for {missing}. They were left out.")

        # Put columns in the same order the user asked for, and drop days
        # where none of the stocks traded (holidays etc.).
        close = close[found].dropna(how="all")

        # Give the table clean labels: rows are called "date", columns have no title.
        close.index.name = "date"
        close.columns.name = None
        return close

    # Ask the memory box. The label includes every setting, so
    # "AAPL for 1y" and "AAPL for 5y" are remembered separately.
    # .copy() hands back a duplicate, so nobody can accidentally scribble
    # on the saved version.
    label = ("prices", tuple(tickers), period, start, adjusted)
    return _remember(label, fetch).copy()


def get_latest_prices(tickers) -> pd.Series:
    """The most recent price for each ticker.

    Returns a simple list-like object (a pandas Series):
        AAPL    233.20
        MSFT    418.75
    """
    # Grab the last 5 days of prices (enough to get past a weekend or holiday).
    prices = get_prices(tickers, period="5d")

    # .ffill() = "forward fill": if a stock has a blank on the last day,
    # copy down its previous price. Then .iloc[-1] takes the last row.
    latest = prices.ffill().iloc[-1]

    # Label the result so it shows up nicely in tables.
    latest.name = "price"
    return latest


def get_info(ticker: str) -> dict:
    """Company facts for one ticker: name, sector, P/E, dividend yield and so on.

    Returns a dictionary like:
        {"ticker": "AAPL", "name": "Apple Inc.", "sector": "Technology", ...}

    If Yahoo doesn't answer, you still get the same dictionary back with
    blanks (None), so the app never crashes just because one fact is missing.
    """
    # Tidy the ticker and take the first one (this function is for ONE company).
    ticker = clean_tickers(ticker)[0]

    # The real download, only run if we don't have a fresh saved answer.
    def fetch():
        # .info asks Yahoo for the company's fact sheet (a big dictionary).
        raw = yf.Ticker(ticker).info

        # A real company has dozens of facts. A made-up ticker gets back
        # almost nothing, so treat that as a failure.
        if not raw or len(raw) < 5:
            raise ValueError("Yahoo returned no facts")

        # Keep only the facts we care about, renamed to our friendly names.
        # raw.get(...) returns None if Yahoo didn't include that fact.
        return {ours: raw.get(theirs) for ours, theirs in INFO_FIELDS.items()}

    try:
        # Try the memory box first, then the internet.
        facts = _remember(("info", ticker), fetch)
    except Exception as error:
        # Anything went wrong (no internet, bad ticker, Yahoo hiccup):
        # warn, and fill every fact with None so the shape stays the same.
        warnings.warn(f"Couldn't get company facts for {ticker} ({error}). Showing blanks.")
        facts = {ours: None for ours in INFO_FIELDS}

    # Put the ticker at the front, then all the facts.
    # The ** "unpacks" the facts dictionary into this new one.
    return {"ticker": ticker, **facts}


def get_fx_rate(from_currency: str, to_currency: str) -> float:
    """Today's exchange rate: how many `to_currency` you get for 1 `from_currency`.

    Example:
        get_fx_rate("USD", "CAD") -> 1.38
        means 1 US dollar buys 1.38 Canadian dollars.
    """
    # Tidy the currency codes ("usd " -> "USD").
    from_currency = from_currency.strip().upper()
    to_currency = to_currency.strip().upper()

    # Same currency on both sides: 1 dollar is 1 dollar.
    if from_currency == to_currency:
        return 1.0

    # Yahoo treats exchange rates like tickers, named like "USDCAD=X".
    pair = f"{from_currency}{to_currency}=X"
    return float(get_latest_prices(pair).iloc[0])


def get_financial_statements(ticker: str, quarterly: bool = False) -> dict:
    """The three financial statements for one company, straight from Yahoo.

    Returns a dictionary of three tables:
        {"income": ..., "balance": ..., "cashflow": ...}

    Each table has one ROW per line item (like "Total Revenue") and one
    COLUMN per period, newest first:

                          2025-09-30   2024-09-30   ...
        Total Revenue     416.16e9     391.04e9
        Net Income        112.01e9      93.74e9

    quarterly  False (default): one column per business year, usually 4 years.
               True: one column per quarter, usually the last 5 to 7 quarters.

    Yahoo already adjusts old share counts and earnings per share for stock
    splits, so old years line up with today's share price.

    If Yahoo doesn't answer, you get three empty tables and a warning.
    """
    # Tidy the ticker and take the first one (this is for ONE company).
    ticker = clean_tickers(ticker)[0]

    # The real download, only run if we don't have a fresh saved answer.
    def fetch():
        company = yf.Ticker(ticker)
        if quarterly:
            raw = {
                "income": company.quarterly_income_stmt,
                "balance": company.quarterly_balance_sheet,
                "cashflow": company.quarterly_cashflow,
            }
        else:
            raw = {
                "income": company.income_stmt,
                "balance": company.balance_sheet,
                "cashflow": company.cashflow,
            }

        tables = {}
        for name, table in raw.items():
            # Yahoo sometimes sends nothing at all. Use an empty table instead.
            if table is None:
                table = pd.DataFrame()
            # Remove periods (columns) that are completely blank.
            table = table.dropna(axis="columns", how="all")
            # Put the newest period first.
            table = table[sorted(table.columns, reverse=True)]
            tables[name] = table

        # All three empty means Yahoo had nothing for this ticker.
        if all(table.empty for table in tables.values()):
            raise ValueError("Yahoo returned no statements")
        return tables

    try:
        tables = _remember(("statements", ticker, quarterly), fetch)
    except Exception as error:
        warnings.warn(f"Couldn't get financial statements for {ticker} ({error}).")
        return {name: pd.DataFrame() for name in ("income", "balance", "cashflow")}

    # Hand back copies so nobody scribbles on the remembered answer.
    return {name: table.copy() for name, table in tables.items()}


def price_on(prices: pd.Series, day) -> float:
    """The price on `day`, or the closest earlier price if markets were closed.

    prices  one column of a get_prices() table, like get_prices("AAPL")["AAPL"]
    day     a date like "2024-01-15"

    Example: if `day` is a Saturday, you get Friday's closing price.
    """
    # .loc[:day] keeps every row up to and including that day.
    earlier = prices.loc[:pd.Timestamp(day)].dropna()
    if earlier.empty:
        # Nothing on or before that day, so use the first price we have.
        return float(prices.dropna().iloc[0])
    return float(earlier.iloc[-1])


def get_group_companies(kind: str, key: str) -> pd.DataFrame:
    """The biggest companies in one industry or sector, biggest first.

    kind  "industry" (narrow, like "semiconductors") or
          "sector" (broad, like "technology")
    key   Yahoo's code for it. get_info(ticker) gives you "industry_key"
          and "sector_key".

    Returns a table with one row per company:
                name                 market_weight
        NVDA    NVIDIA Corporation   0.45
        AVGO    Broadcom Inc.        0.14

    market_weight is the company's share of the whole group's value:
    0.45 means it's 45% of the industry.

    If Yahoo doesn't answer, you get an empty table and a warning.
    """
    def fetch():
        # yf.Industry and yf.Sector are Yahoo's industry and sector pages.
        group = yf.Industry(key) if kind == "industry" else yf.Sector(key)
        top = group.top_companies
        if top is None or top.empty:
            raise ValueError("Yahoo returned no companies")
        # Keep the two columns we use, with a friendlier name for the weight.
        top = top[["name", "market weight"]].rename(columns={"market weight": "market_weight"})
        return top.sort_values("market_weight", ascending=False)

    try:
        return _remember(("group", kind, key), fetch).copy()
    except Exception as error:
        warnings.warn(f"Couldn't get the companies in the {key} {kind} ({error}).")
        return pd.DataFrame(columns=["name", "market_weight"])


# ===========================================================================
# THE ECONOMY
# ===========================================================================

def _download_text(url: str, json_body: dict = None) -> str:
    """Download a web address and return its text.

    json_body  if given, it's sent along with the request (some sites want
               the question written in JSON instead of in the address)
    """
    headers = {"User-Agent": "Mozilla/5.0 (MyPortfolio student project)"}
    body = None
    if json_body is not None:
        body = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    # timeout=25: give up after 25 seconds instead of waiting forever.
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8", errors="replace")


def _fred_series(series_id: str) -> pd.Series:
    """One series from the St. Louis Fed's FRED site, our backup source.

    FRED sends a small CSV file with two columns: the date and the value.
    """
    text = _download_text(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}")
    # When FRED is down for maintenance it sends a web page, not a CSV.
    if text.lstrip().startswith("<"):
        raise ValueError("FRED is down for maintenance")
    table = pd.read_csv(io.StringIO(text))
    dates = pd.to_datetime(table.iloc[:, 0])
    values = pd.to_numeric(table.iloc[:, 1], errors="coerce")  # "." means missing
    return pd.Series(values.values, index=dates).dropna()


def _first_that_works(name: str, sources: list) -> pd.Series:
    """Try each (source name, fetch function) in order until one works.

    If they all fail, raise an error listing what went wrong with each.
    """
    problems = []
    for source_name, fetch in sources:
        try:
            series = fetch()
            if series.empty:
                raise ValueError("no data")
            return series
        except Exception as error:
            problems.append(f"{source_name}: {error}")
    raise ValueError(f"every source failed for {name} ({'; '.join(problems)})")


def get_us_10y_yield() -> pd.Series:
    """The US 10-year government bond yield, one number per trading day, in %.

    4.5 means 4.5%. This is the interest rate the US government pays to
    borrow for 10 years. It's the world's benchmark interest rate: mortgages,
    company loans, and stock values all take their cue from it.
    """
    try:
        # Yahoo treats it like a ticker: ^TNX. Five years of history.
        series = get_prices("^TNX", period="5y")["^TNX"].dropna()
        series.name = "10-year yield %"
        return series
    except Exception as error:
        warnings.warn(f"Couldn't get the US 10-year yield ({error}).")
        return pd.Series(dtype=float, name="10-year yield %")


def get_us_inflation() -> pd.Series:
    """US inflation, one number per month, in %.

    3.0 means prices are 3% higher than the same month a year earlier.
    Calculated from the consumer price index (CPI), which tracks the price
    of a typical basket of things people buy.
    """
    def from_bls():
        # The BLS wants the question as JSON: which series and which years.
        # We ask for 7 years, because a yearly change needs a year before it.
        this_year = pd.Timestamp.today().year
        answer = json.loads(
            _download_text(
                "https://api.bls.gov/publicAPI/v1/timeseries/data/",
                {"seriesid": ["CUUR0000SA0"], "startyear": str(this_year - 6), "endyear": str(this_year)},
            )
        )
        if answer.get("status") != "REQUEST_SUCCEEDED":
            raise ValueError(answer.get("message") or answer.get("status"))
        points = answer["Results"]["series"][0]["data"]
        # Each point looks like {"year": "2026", "period": "M09", "value": "336.9"}.
        # M01 to M12 are months. M13 is a yearly average, which we skip.
        # A month with no data has the value "-". October 2025 is like that,
        # because a US government shutdown stopped price collection.
        monthly = {}
        for p in points:
            if not p["period"].startswith("M") or p["period"] == "M13":
                continue
            value = pd.to_numeric(p["value"], errors="coerce")   # "-" becomes blank
            if pd.notna(value):
                monthly[pd.Timestamp(int(p["year"]), int(p["period"][1:]), 1)] = float(value)
        return pd.Series(monthly).sort_index()

    def from_fred():
        return _fred_series("CPIAUCSL")

    def fetch():
        price_index = _first_that_works("US inflation", [("BLS", from_bls), ("FRED", from_fred)])
        # Give every calendar month its own row, leaving missing months blank.
        # "MS" means "month start". Without this, a missing month would make
        # us compare with the wrong month a year earlier.
        price_index = price_index.asfreq("MS")
        # Turn the price index into "% higher than the same month a year earlier".
        # .shift(12) lines each month up with the month 12 rows (a year) before.
        inflation = ((price_index / price_index.shift(12) - 1) * 100).dropna()
        inflation.name = "Inflation %"
        return inflation

    try:
        return _remember(("economy", "inflation"), fetch, max_age=ECONOMY_CACHE_SECONDS).copy()
    except Exception as error:
        warnings.warn(f"Couldn't get US inflation ({error}).")
        return pd.Series(dtype=float, name="Inflation %")


def get_us_gdp_growth() -> pd.Series:
    """US economic growth, one number per quarter, in %.

    2.5 means the economy grew at a 2.5% yearly pace that quarter, after
    removing inflation. GDP (gross domestic product) is the value of
    everything the country produces. Below 0 means the economy shrank.
    """
    def from_dbnomics():
        answer = json.loads(
            _download_text("https://api.db.nomics.world/v22/series/BEA/NIPA-T10101/A191RL-Q?observations=1")
        )
        doc = answer["series"]["docs"][0]
        # Periods look like "2026-Q2". pd.Period understands that.
        dates = [pd.Period(p, freq="Q").start_time for p in doc["period"]]
        return pd.Series(doc["value"], index=dates, dtype=float).dropna()

    def from_fred():
        return _fred_series("A191RL1Q225SBEA")

    def fetch():
        growth = _first_that_works("US GDP growth", [("DBnomics", from_dbnomics), ("FRED", from_fred)])
        growth.name = "GDP growth %"
        return growth

    try:
        return _remember(("economy", "gdp"), fetch, max_age=ECONOMY_CACHE_SECONDS).copy()
    except Exception as error:
        warnings.warn(f"Couldn't get US GDP growth ({error}).")
        return pd.Series(dtype=float, name="GDP growth %")


def get_price_bars(ticker: str, period: str = "2y", adjusted: bool = False) -> pd.DataFrame:
    """Daily price bars for ONE ticker: open, high, low, close and volume.

    Returns a table with one row per trading day:

                    Open    High    Low     Close   Volume
        date
        2026-10-20  276.50  280.80  276.06  280.17  4526300

    Open    the first trade of the day
    High    the highest price that day
    Low     the lowest price that day
    Close   the last trade of the day
    Volume  how many shares changed hands

    adjusted  False (default): the plain prices your broker shows, so price
              levels like a stop are real prices you could actually trade at.
              True: dividends baked in, better for comparing returns.
              Either way, stock splits are always accounted for.
    """
    ticker = clean_tickers(ticker)[0]

    def fetch():
        raw = yf.download(ticker, period=period, auto_adjust=adjusted, progress=False)
        if raw is None or raw.empty:
            raise ValueError(f"No price bars found for {ticker}. Check the ticker.")
        # Yahoo labels columns twice, like ("Close", "AAPL"). Keep just "Close".
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        bars = raw[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
        bars.index.name = "date"
        return bars

    return _remember(("bars", ticker, period, adjusted), fetch).copy()


# ===========================================================================
# WHAT THE ANALYSTS SAY
# ===========================================================================

def get_analyst_data(ticker: str) -> dict:
    """Everything Yahoo has on what professional analysts think of a stock.

    Returns a dictionary of five pieces. Any piece Yahoo doesn't have comes
    back empty, so the app never crashes because one piece is missing.

        "ratings"    how many analysts say strong buy / buy / hold / sell /
                     strong sell, now ("0m") and 1, 2 and 3 months ago
        "targets"    where analysts think the price will be in a year:
                     {"current", "low", "mean", "median", "high"}
        "actions"    every rating change and price target change, newest
                     first: date, firm, old and new rating, target moves
        "forecasts"  the average forecast of earnings per share (EPS) for
                     this quarter, next quarter, this year and next year,
                     now and 7, 30, 60 and 90 days ago
        "revisions"  how many analysts raised or cut those forecasts in the
                     last 7 and 30 days
    """
    ticker = clean_tickers(ticker)[0]

    def fetch():
        company = yf.Ticker(ticker)

        # Each piece is fetched on its own, so one failure doesn't sink the rest.
        def safely(get, empty):
            try:
                value = get()
                return empty if value is None or len(value) == 0 else value
            except Exception:
                return empty

        pieces = {
            "ratings": safely(lambda: company.recommendations, pd.DataFrame()),
            "targets": safely(lambda: company.analyst_price_targets, {}),
            "actions": safely(lambda: company.upgrades_downgrades, pd.DataFrame()),
            "forecasts": safely(lambda: company.eps_trend, pd.DataFrame()),
            "revisions": safely(lambda: company.eps_revisions, pd.DataFrame()),
        }
        # If every piece is empty, Yahoo has nothing on this ticker.
        if all(len(piece) == 0 for piece in pieces.values()):
            raise ValueError("Yahoo has no analyst data")
        return pieces

    try:
        pieces = _remember(("analysts", ticker), fetch)
    except Exception as error:
        warnings.warn(f"Couldn't get analyst data for {ticker} ({error}).")
        pieces = {"ratings": pd.DataFrame(), "targets": {}, "actions": pd.DataFrame(),
                  "forecasts": pd.DataFrame(), "revisions": pd.DataFrame()}

    # Hand back copies so nobody scribbles on the remembered answer.
    return {name: (piece.copy() if hasattr(piece, "copy") else piece) for name, piece in pieces.items()}
