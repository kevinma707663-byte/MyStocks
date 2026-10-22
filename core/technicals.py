"""
technicals.py - MyAnalysis Part 3D: "What's the price doing?"

WHAT THIS FILE DOES
    Reads the price chart the way traders do. Fundamentals (Parts 3A to 3C)
    ask "is this a good business?" Technicals ask "what are buyers and
    sellers doing with the stock right now?"

THE TOOLS, IN PLAIN WORDS
    Moving average      the average closing price over the last 50 or 200
                        days. It smooths out daily noise so you see the trend.
    Golden cross        the 50-day average crosses ABOVE the 200-day: a
                        classic good sign. A death cross is the opposite.
    RSI                 the relative strength index, from 0 to 100. Above 70
                        means it ran up too fast and may cool off. Below 30
                        means it fell too fast and may bounce.
    Support             a "floor": a price where the stock kept bouncing UP.
    Resistance          a "ceiling": a price where it kept getting pushed DOWN.
    Breakout            closing above a ceiling on heavier trading than usual.
                        A breakdown is closing below a floor.
    Entry stop          a "buy only if" price just above the ceiling, so you
                        only get in if a breakout really happens.
    Protective stop     a "get me out" price below the floor. It caps your loss.
    ATR                 average true range: how much the price normally moves
                        in a day. Used as a safety cushion for stops.
    Retracement         a pullback after a big run. Pullbacks often pause at
                        38.2%, 50% or 61.8% of the run (Fibonacci levels).
    Reward to risk      distance up to the next ceiling divided by distance
                        down to the stop. 2 or more is usually seen as good.
    Momentum            how much the stock rose over 3, 6 and 12 months,
                        compared with the S&P 500. Winners tend to keep
                        winning for a while.

PRICES USED
    Plain prices (what your broker shows), so every level is a real price
    you could trade at. Momentum uses dividend-adjusted prices instead,
    because it compares total returns with the S&P 500.

THESE ARE SUGGESTED PRICE LEVELS, NOT TRADE ORDERS
    Technical signals are educated guesses about crowd behaviour. They are
    often wrong, especially over short periods.

THE FUNCTIONS OTHER FILES USE
    technical_summary(ticker)      -> every signal, the trade setup, and a 0 to 100 score
    technical_chart(summary)       -> candlestick chart with all the lines drawn on
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# numpy: math helpers. np.nan means "blank / not a number".
import numpy as np

# pandas: the library for tables of numbers.
import pandas as pd

# plotly: interactive charts. graph_objects gives finer control than
# plotly.express, which we need for candlesticks and stacked panels.
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Our own price fetcher. The dot means "from this same core/ folder".
from . import data


# ===========================================================================
# SETTINGS
# ===========================================================================

SHORT_AVERAGE = 50            # days in the short moving average
LONG_AVERAGE = 200            # days in the long moving average
RSI_DAYS = 14                 # days RSI looks back over
RSI_HIGH = 70                 # above this: ran up too fast
RSI_LOW = 30                  # below this: fell too fast
ATR_DAYS = 14                 # days ATR looks back over
CHART_DAYS = 252              # about one year of trading days

SWING_DAYS = 10               # a peak must be the highest price 10 days either side
LEVEL_TOLERANCE = 0.02        # peaks and dips within 2% count as the same level

BREAKOUT_DAYS = 5             # look for breakouts in the last 5 trading days
BREAKOUT_VOLUME = 1.5         # ...with at least 1.5x the usual trading volume

TESTING_ATR = 0.5             # a ceiling within half a day's move is "being tested"
ENTRY_BUFFER = 0.01           # entry stop sits 1% above the ceiling
STOP_CUSHION_ATR = 0.5        # protective stop sits half a day's move below the floor
MAX_STOP_ATR = 3.0            # if the floor is further than 3 days' moves away...
FALLBACK_STOP_ATR = 2.0       # ...put the stop 2 days' moves below the price instead

FIBONACCI = [0.382, 0.5, 0.618]

BENCHMARK = "SPY"
MOMENTUM_PERIODS = {"3 months": 3, "6 months": 6, "12 months": 12}


# ===========================================================================
# 1. INDICATORS: the lines traders draw on charts
# ===========================================================================

def _rsi(close: pd.Series, days: int = RSI_DAYS) -> pd.Series:
    """Relative strength index, from 0 to 100.

    It compares the size of recent up days with recent down days.
    Mostly up days pushes it toward 100. Mostly down days pushes it toward 0.
    """
    change = close.diff()                       # today's close minus yesterday's
    gains = change.clip(lower=0)                # keep the up moves, zero the rest
    losses = -change.clip(upper=0)              # keep the down moves, as positives
    # .ewm(...).mean() is a "smoothed" average that weights recent days more.
    # alpha = 1/14 is the standard recipe from RSI's inventor, J. Welles Wilder.
    average_gain = gains.ewm(alpha=1 / days, adjust=False).mean()
    average_loss = losses.ewm(alpha=1 / days, adjust=False).mean()
    strength = average_gain / average_loss
    return 100 - 100 / (1 + strength)


def _atr(bars: pd.DataFrame, days: int = ATR_DAYS) -> pd.Series:
    """Average true range: how much the price normally moves in a day, in dollars.

    The "true range" of a day is the biggest of:
        high - low                      (the day's own swing)
        |high - yesterday's close|      (a jump up overnight)
        |low - yesterday's close|       (a drop overnight)
    """
    previous_close = bars["Close"].shift(1)
    true_range = pd.concat(
        [
            bars["High"] - bars["Low"],
            (bars["High"] - previous_close).abs(),
            (bars["Low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.ewm(alpha=1 / days, adjust=False).mean()


def _with_indicators(ticker: str) -> pd.DataFrame:
    """Two years of daily bars, plus every indicator as an extra column.

    We fetch two years so the 200-day average is ready for the whole
    one-year chart.
    """
    bars = data.get_price_bars(ticker, period="2y")
    bars["avg_50"] = bars["Close"].rolling(SHORT_AVERAGE).mean()
    bars["avg_200"] = bars["Close"].rolling(LONG_AVERAGE).mean()
    bars["rsi"] = _rsi(bars["Close"])
    bars["atr"] = _atr(bars)
    bars["avg_volume"] = bars["Volume"].rolling(SHORT_AVERAGE).mean()
    return bars


# ===========================================================================
# 2. SUPPORT AND RESISTANCE: the floors and ceilings
# ===========================================================================

def _levels(bars: pd.DataFrame, price: float) -> pd.DataFrame:
    """Find the floors and ceilings from the past year's peaks and dips.

    Step 1: a PEAK is a day whose high is the highest of the 10 days on
            either side. A DIP is the same for lows. The year's highest high
            and lowest low always count too, because traders watch them
            closely even when they happened in the last few days.
    Step 2: peaks and dips within 2% of each other are grouped into one
            level. More touches means a stronger level.
    Step 3: levels below today's price are support (floors). Levels above
            are resistance (ceilings). A broken ceiling often becomes a floor,
            which is why peaks and dips are grouped together.

    Returns a table with one row per level: price, kind, touches, last_touch.
    """
    year = bars.iloc[-CHART_DAYS:]
    window = 2 * SWING_DAYS + 1

    # center=True looks both backward AND forward, so the last 10 days
    # can't be confirmed as peaks yet. That's on purpose.
    is_peak = year["High"] == year["High"].rolling(window, center=True).max()
    is_dip = year["Low"] == year["Low"].rolling(window, center=True).min()

    # Collect (day, price) pairs. A set throws away exact duplicates, so the
    # year's high isn't counted twice when it's also a confirmed peak.
    points = set(year.loc[is_peak, "High"].items()) | set(year.loc[is_dip, "Low"].items())
    points.add((year["High"].idxmax(), year["High"].max()))
    points.add((year["Low"].idxmin(), year["Low"].min()))
    points = sorted(points, key=lambda point: point[1])     # lowest price first

    # Group points that sit within 2% of each other.
    groups = []
    for day, level_price in points:
        if groups and abs(level_price - np.mean(groups[-1]["prices"])) <= LEVEL_TOLERANCE * level_price:
            groups[-1]["prices"].append(level_price)
            groups[-1]["days"].append(day)
        else:
            groups.append({"prices": [level_price], "days": [day]})

    rows = []
    for group in groups:
        level_price = float(np.mean(group["prices"]))
        rows.append(
            {
                "price": level_price,
                "kind": "support" if level_price < price else "resistance",
                "touches": len(group["prices"]),
                "last_touch": max(group["days"]).date(),
            }
        )
    return pd.DataFrame(rows, columns=["price", "kind", "touches", "last_touch"])


# ===========================================================================
# 3. THE SIGNALS
# ===========================================================================

def _trend_signal(bars: pd.DataFrame) -> dict:
    """Up, down or sideways, using the two moving averages."""
    last = bars.iloc[-1]
    if pd.isna(last["avg_200"]):
        return {"reading": "not enough history", "points": 0,
                "why": "Needs 200 days of prices for the long-term average."}

    # Is the 200-day average itself rising? Compare with a month ago.
    rising = last["avg_200"] > bars["avg_200"].iloc[-22]

    # When did the 50-day last cross the 200-day? Look over the past year.
    above = (bars["avg_50"] > bars["avg_200"]).iloc[-CHART_DAYS:]
    flips = above[above != above.shift(1)].iloc[1:]           # days the side changed
    if len(flips):
        cross_day = flips.index[-1].date()
        cross = f"Last cross: a {'golden' if flips.iloc[-1] else 'death'} cross on {cross_day}."
    else:
        cross = "No golden or death cross in the past year."

    if last["Close"] > last["avg_200"] and last["avg_50"] > last["avg_200"] and rising:
        return {"reading": "uptrend", "points": +1,
                "why": f"Price and the 50-day average are above a rising 200-day average. {cross}"}
    if last["Close"] < last["avg_200"] and last["avg_50"] < last["avg_200"] and not rising:
        return {"reading": "downtrend", "points": -1,
                "why": f"Price and the 50-day average are below a falling 200-day average. {cross}"}
    return {"reading": "sideways", "points": 0,
            "why": f"The price and averages are mixed, with no clear direction. {cross}"}


def _averages_signal(bars: pd.DataFrame) -> dict:
    """Where today's price sits compared with the two moving averages."""
    last = bars.iloc[-1]
    if pd.isna(last["avg_200"]):
        return {"reading": "not enough history", "points": 0, "why": "Needs 200 days of prices."}
    above_short = last["Close"] > last["avg_50"]
    above_long = last["Close"] > last["avg_200"]
    detail = f"Price {last['Close']:.2f}, 50-day {last['avg_50']:.2f}, 200-day {last['avg_200']:.2f}."
    if above_short and above_long:
        return {"reading": "above both", "points": +1, "why": f"Buyers are in control for now. {detail}"}
    if not above_short and not above_long:
        return {"reading": "below both", "points": -1, "why": f"Sellers are in control for now. {detail}"}
    return {"reading": "in between", "points": 0, "why": f"Short and long term disagree. {detail}"}


def _rsi_signal(bars: pd.DataFrame) -> dict:
    """Has the stock run too far, too fast, either way?"""
    rsi = bars["rsi"].iloc[-1]
    if rsi > RSI_HIGH:
        return {"reading": f"{rsi:.0f}, overbought", "points": -1,
                "why": "It ran up fast. Stocks often cool off or pause after a run like this."}
    if rsi < RSI_LOW:
        return {"reading": f"{rsi:.0f}, oversold", "points": +1,
                "why": "It fell fast. Stocks often bounce after a drop like this."}
    return {"reading": f"{rsi:.0f}, normal", "points": 0,
            "why": f"Between {RSI_LOW} and {RSI_HIGH}, so neither stretched up nor down."}


def _breakout_signal(bars: pd.DataFrame, levels: pd.DataFrame) -> dict:
    """Did the price close through a ceiling or floor in the last 5 days, on heavy trading?"""
    recent = bars.iloc[-(BREAKOUT_DAYS + 1):]          # one extra day for "yesterday"
    found = None
    for i in range(1, len(recent)):
        yesterday, today = recent.iloc[i - 1], recent.iloc[i]
        volume_ratio = today["Volume"] / today["avg_volume"] if today["avg_volume"] else np.nan
        for level_price in levels["price"]:
            crossed_up = yesterday["Close"] < level_price <= today["Close"]
            crossed_down = yesterday["Close"] > level_price >= today["Close"]
            if (crossed_up or crossed_down) and volume_ratio >= BREAKOUT_VOLUME:
                found = {
                    "direction": "breakout" if crossed_up else "breakdown",
                    "level": level_price,
                    "day": recent.index[i].date(),
                    "volume_ratio": volume_ratio,
                }
    if found is None:
        return {"reading": "none", "points": 0,
                "why": f"No close through a floor or ceiling on heavy trading in the last {BREAKOUT_DAYS} days."}
    good = found["direction"] == "breakout"
    side = "above a ceiling" if good else "below a floor"
    return {
        "reading": found["direction"],
        "points": +1 if good else -1,
        "why": (f"Closed {side} at {found['level']:.2f} on {found['day']}, "
                f"with {found['volume_ratio']:.1f}x the usual trading volume."),
    }


def _momentum(ticker: str) -> pd.DataFrame:
    """Returns over 3, 6 and 12 months, next to the S&P 500's.

    Uses dividend-adjusted prices, so dividends count as part of the return.
    """
    prices = data.get_prices([ticker, BENCHMARK], period="2y").ffill()
    today = prices.index[-1]
    first_day = prices[ticker].first_valid_index()       # when the stock started trading
    rows = []
    for label, months in MOMENTUM_PERIODS.items():
        start = today - pd.DateOffset(months=months)
        # A stock that wasn't trading yet at the start gets a blank, not a
        # return from its first day (that wouldn't be a fair comparison).
        if start < first_day - pd.Timedelta(days=7):
            stock = np.nan
        else:
            stock = (prices[ticker].iloc[-1] / data.price_on(prices[ticker], start) - 1) * 100
        market = (prices[BENCHMARK].iloc[-1] / data.price_on(prices[BENCHMARK], start) - 1) * 100
        rows.append({"period": label, "stock_pct": stock, "sp500_pct": market, "difference": stock - market})
    return pd.DataFrame(rows).set_index("period")


def _momentum_signal(momentum: pd.DataFrame) -> dict:
    """Score momentum: 1 point for each period that's up, 1 for each that beats the S&P 500.

    Periods with no data (a new stock) are left out of the count.
    """
    known = momentum.dropna(subset=["stock_pct"])
    if known.empty:
        return {"reading": "not enough history", "points": 0, "why": "The stock hasn't traded for 3 months yet."}
    points = int((known["stock_pct"] > 0).sum() + (known["difference"] > 0).sum())
    out_of = 2 * len(known)
    why = f"{points} of {out_of} checks passed (up over the period, and beating the S&P 500)."
    if points / out_of >= 5 / 6:
        return {"reading": "strong", "points": +1, "why": why}
    if points / out_of <= 1 / 6:
        return {"reading": "weak", "points": -1, "why": why}
    return {"reading": "mixed", "points": 0, "why": why}


# ===========================================================================
# 4. THE TRADE SETUP: entry, stop, retracements, reward to risk
# ===========================================================================

def _trade_setup(bars: pd.DataFrame, levels: pd.DataFrame) -> dict:
    """Suggested price levels around today's price."""
    last = bars.iloc[-1]
    price, atr = float(last["Close"]), float(last["atr"])

    floors = levels[levels["kind"] == "support"]
    ceilings = levels[levels["kind"] == "resistance"]
    floor = float(floors["price"].max()) if len(floors) else np.nan       # nearest floor below

    # A ceiling within half a day's move is being TESTED right now. Measuring
    # the reward up to it would be silly (it's only cents away), so the
    # reward is measured to the next ceiling beyond it.
    tested = ceilings[ceilings["price"] <= price + TESTING_ATR * atr]
    beyond = ceilings[ceilings["price"] > price + TESTING_ATR * atr]
    tested_ceiling = float(tested["price"].min()) if len(tested) else np.nan
    ceiling = float(beyond["price"].min()) if len(beyond) else np.nan      # next ceiling with room above

    # --- Entry stop: "buy only if it closes above the ceiling" ---------------
    if pd.notna(tested_ceiling):
        entry_stop = tested_ceiling * (1 + ENTRY_BUFFER)
        entry_why = f"The price is testing the ceiling at {tested_ceiling:.2f} right now, so 1% above it."
    elif pd.notna(ceiling):
        entry_stop = ceiling * (1 + ENTRY_BUFFER)
        entry_why = f"1% above the nearest ceiling at {ceiling:.2f}."
    else:
        # No ceiling in the past year means it's at new highs.
        recent_high = float(bars["High"].iloc[-20:].max())
        entry_stop = recent_high * (1 + ENTRY_BUFFER)
        entry_why = f"No ceiling in the past year (new highs), so 1% above the 20-day high of {recent_high:.2f}."

    # --- Protective stop: "get me out if it falls below the floor" -----------
    if pd.notna(floor) and price - floor <= MAX_STOP_ATR * atr:
        stop = floor - STOP_CUSHION_ATR * atr
        stop_why = f"Half a normal day's move ({STOP_CUSHION_ATR * atr:.2f}) below the floor at {floor:.2f}."
    else:
        stop = price - FALLBACK_STOP_ATR * atr
        reason = "the nearest floor is far below" if pd.notna(floor) else "there's no floor in the past year"
        stop_why = f"Two normal days' moves ({FALLBACK_STOP_ATR * atr:.2f}) below today's price, because {reason}."

    # --- Reward to risk ------------------------------------------------------
    risk = price - stop
    reward = ceiling - price if pd.notna(ceiling) else np.nan
    reward_to_risk = reward / risk if pd.notna(reward) and risk > 0 else np.nan

    return {
        "price": price,
        "daily_move_atr": atr,
        "next_floor": floor,
        "ceiling_being_tested": tested_ceiling,
        "next_ceiling": ceiling,
        "entry_stop": entry_stop,
        "entry_why": entry_why,
        "protective_stop": stop,
        "stop_why": stop_why,
        "stop_distance_pct": risk / price * 100,
        "reward_to_risk": reward_to_risk,
    }


def _setup_signal(setup: dict) -> dict:
    """Is the reward worth the risk from here?"""
    ratio = setup["reward_to_risk"]
    testing = ""
    if pd.notna(setup["ceiling_being_tested"]):
        testing = f"It's testing the ceiling at {setup['ceiling_being_tested']:.2f} right now. "
    if pd.isna(ratio):
        return {"reading": "no ceiling", "points": 0,
                "why": f"{testing}There's no higher ceiling in the past year to measure the reward against."}
    detail = (f"{testing}Up to the next ceiling: {setup['next_ceiling'] - setup['price']:.2f}. "
              f"Down to the stop: {setup['price'] - setup['protective_stop']:.2f}.")
    if ratio >= 2:
        return {"reading": f"{ratio:.1f} to 1, good", "points": +1, "why": f"The possible gain is at least twice the possible loss. {detail}"}
    if ratio < 1:
        return {"reading": f"{ratio:.1f} to 1, poor", "points": -1, "why": f"The possible loss is bigger than the possible gain. {detail}"}
    return {"reading": f"{ratio:.1f} to 1, fair", "points": 0, "why": f"Gain and loss are similar in size. {detail}"}


def _retracements(bars: pd.DataFrame) -> dict:
    """Fibonacci levels for the past year's big move.

    If the lowest low came BEFORE the highest high, the big move was UP, and
    the levels are where a pullback might pause on the way down. If the high
    came first, the move was DOWN, and the levels are where a bounce might
    stall on the way up.
    """
    year = bars.iloc[-CHART_DAYS:]
    low_day, high_day = year["Low"].idxmin(), year["High"].idxmax()
    low, high = float(year["Low"].min()), float(year["High"].max())
    move = high - low
    price = float(year["Close"].iloc[-1])

    if low_day < high_day:
        direction = "up"
        levels = {f"{f:.1%}": high - f * move for f in FIBONACCI}
        given_back = (high - price) / move if move else np.nan
        where = f"The stock has given back {given_back:.0%} of its run from {low:.2f} to {high:.2f}."
    else:
        direction = "down"
        levels = {f"{f:.1%}": low + f * move for f in FIBONACCI}
        won_back = (price - low) / move if move else np.nan
        where = f"The stock has won back {won_back:.0%} of its fall from {high:.2f} to {low:.2f}."

    return {
        "direction": direction,
        "low": low, "low_day": low_day.date(),
        "high": high, "high_day": high_day.date(),
        "levels": levels,
        "where": where,
    }


# ===========================================================================
# 5. THE MAIN FUNCTION
# ===========================================================================

def technical_summary(ticker: str) -> dict:
    """Read the chart for one stock.

    Returns a dictionary:
        {
          "company":      "NVDA",
          "price":        today's close,
          "as_of":        the date of that close,
          "signals":      table with one row per signal: reading, points
                          (+1 good sign, 0 neutral, -1 warning sign), why
          "setup":        the suggested entry stop, protective stop, nearest
                          floor and ceiling, and reward to risk
          "retracements": the past year's big move and its Fibonacci levels
          "levels":       every floor and ceiling found, with touches
          "momentum":     3, 6 and 12-month returns vs the S&P 500
          "score":        0 to 100, where 50 is neutral
          "verdict":      "positive", "mixed" or "negative"
          "bars":         the daily prices and indicators, for the chart
        }
    """
    ticker = data.clean_tickers(ticker)[0]
    bars = _with_indicators(ticker)
    price = float(bars["Close"].iloc[-1])

    levels = _levels(bars, price)
    setup = _trade_setup(bars, levels)
    momentum = _momentum(ticker)

    signals = {
        "Trend": _trend_signal(bars),
        "Moving averages": _averages_signal(bars),
        "RSI": _rsi_signal(bars),
        "Breakout": _breakout_signal(bars, levels),
        "Reward to risk": _setup_signal(setup),
        "Momentum": _momentum_signal(momentum),
    }
    signals = pd.DataFrame(signals).T[["reading", "points", "why"]]
    signals["points"] = signals["points"].astype(int)

    # Average the points (-1 to +1) and stretch onto 0 to 100, with 50 neutral.
    score = float(50 + 50 * signals["points"].mean())
    verdict = "positive" if score >= 60 else "negative" if score <= 40 else "mixed"

    return {
        "company": ticker,
        "price": price,
        "as_of": bars.index[-1].date(),
        "signals": signals,
        "setup": setup,
        "retracements": _retracements(bars),
        "levels": levels.sort_values("price", ascending=False).reset_index(drop=True),
        "momentum": momentum,
        "score": score,
        "verdict": verdict,
        "bars": bars,
    }


# ===========================================================================
# 6. THE CHART
# ===========================================================================

def technical_chart(summary: dict, max_levels: int = 3):
    """Candlestick chart with everything drawn on. Pass in technical_summary(...).

    Top panel:     candles, 50 and 200-day averages, the nearest floors
                   (green) and ceilings (red), Fibonacci levels (grey dots),
                   the entry stop (blue) and protective stop (orange)
    Middle panel:  trading volume
    Bottom panel:  RSI, with the 30 and 70 lines

    max_levels  how many floors and ceilings to draw on each side
    """
    bars = summary["bars"].iloc[-CHART_DAYS:]
    setup = summary["setup"]

    # Three panels stacked, sharing the same dates along the bottom.
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.62, 0.15, 0.23],
    )

    # --- Top panel: candles and averages ------------------------------------
    fig.add_trace(go.Candlestick(
        x=bars.index, open=bars["Open"], high=bars["High"], low=bars["Low"], close=bars["Close"],
        name="Price",
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=bars.index, y=bars["avg_50"], name="50-day average", line={"width": 1.5}), row=1, col=1)
    fig.add_trace(go.Scatter(x=bars.index, y=bars["avg_200"], name="200-day average", line={"width": 1.5}), row=1, col=1)

    # A flat line across the whole chart. Drawn as a chart line (not a plain
    # shape) so it gets a legend entry and shows its exact price on hover.
    first_day, last_day = bars.index[0], bars.index[-1]

    def flat_line(price, name, color, dash, group, first_in_group):
        fig.add_trace(go.Scatter(
            x=[first_day, last_day], y=[price, price], mode="lines",
            line={"color": color, "dash": dash, "width": 1.2},
            name=group, legendgroup=group, showlegend=first_in_group,
            hovertemplate=f"{name}: %{{y:.2f}}<extra></extra>",
        ), row=1, col=1)

    # A small text label sitting on a line, at the left or right edge.
    def label(price, text, side, shift=0):
        fig.add_annotation(
            x=first_day if side == "left" else last_day, y=price, text=text,
            xanchor=side, yanchor="bottom", yshift=shift, showarrow=False,
            font={"size": 10}, bgcolor="rgba(255,255,255,0.7)", row=1, col=1,
        )

    # Nearest floors (green) and ceilings (red), labelled on the left.
    levels = summary["levels"]
    floors = levels[levels["kind"] == "support"].nlargest(max_levels, "price")
    ceilings = levels[levels["kind"] == "resistance"].nsmallest(max_levels, "price")
    for i, (_, level) in enumerate(floors.iterrows()):
        flat_line(level["price"], "Floor", "green", "dash", "Floors (support)", i == 0)
        label(level["price"], f"floor {level['price']:.2f} ({level['touches']}x)", "left")
    for i, (_, level) in enumerate(ceilings.iterrows()):
        flat_line(level["price"], "Ceiling", "red", "dash", "Ceilings (resistance)", i == 0)
        label(level["price"], f"ceiling {level['price']:.2f} ({level['touches']}x)", "left")

    # Fibonacci levels (grey dots): no text labels, to keep the chart tidy.
    # Hover over a dotted line to see which level it is.
    for i, (name, level_price) in enumerate(summary["retracements"]["levels"].items()):
        flat_line(level_price, f"Fibonacci {name}", "grey", "dot", "Fibonacci levels", i == 0)

    # Entry stop (blue) and protective stop (orange), labelled on the right.
    # The entry label sits just above its line and the stop label just
    # below its line, so they never land on top of each other.
    flat_line(setup["entry_stop"], "Entry stop", "blue", "solid", "Entry stop", True)
    label(setup["entry_stop"], f"entry stop {setup['entry_stop']:.2f}", "right")
    flat_line(setup["protective_stop"], "Protective stop", "orange", "solid", "Protective stop", True)
    label(setup["protective_stop"], f"protective stop {setup['protective_stop']:.2f}", "right", shift=-16)

    # --- Middle panel: volume -----------------------------------------------
    fig.add_trace(go.Bar(x=bars.index, y=bars["Volume"], name="Volume", marker_color="lightgrey"), row=2, col=1)

    # --- Bottom panel: RSI ---------------------------------------------------
    fig.add_trace(go.Scatter(x=bars.index, y=bars["rsi"], name="RSI", line={"color": "purple", "width": 1.5}), row=3, col=1)
    fig.add_hline(y=RSI_HIGH, line_dash="dash", line_color="red", row=3, col=1)
    fig.add_hline(y=RSI_LOW, line_dash="dash", line_color="green", row=3, col=1)

    fig.update_layout(
        title=f"{summary['company']}: price chart with technical levels",
        height=800,
        xaxis_rangeslider_visible=False,     # hide plotly's mini slider under candles
        legend={"orientation": "h", "y": -0.05},
    )
    fig.update_yaxes(title_text="Price", row=1, col=1)
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="RSI", range=[0, 100], row=3, col=1)
    return fig
