"""
analysts.py - MyAnalysis Part 3E: "What are the experts saying?"

WHAT THIS FILE DOES
    Professional analysts at banks and research firms study companies full
    time. They publish ratings (buy, hold, sell), price targets, and profit
    forecasts. This file sums up what they're saying and, just as
    importantly, which way their opinions are MOVING.

THE PIECES
    Ratings breakdown   how many analysts say strong buy, buy, hold, sell
                        or strong sell, now and over the past three months
    Average rating      1 = strong buy, 2 = buy, 3 = hold, 4 = sell, 5 = strong sell
    Price targets       where analysts think the price will be in a year
    Rating changes      upgrades, downgrades and price target moves in the
                        last 90 days
    Forecasts           the average forecast of earnings per share (EPS),
                        and how it's changed

ANALYST MOMENTUM
    When analysts' opinions are moving up, the price often keeps rising for
    a while, and the reverse. We check four things:
        1. Are profit forecasts for this year and next higher than 90 days ago?
        2. In the last 30 days, did more analysts raise forecasts than cut them?
        3. In the last 90 days, were there more upgrades and target raises
           than downgrades and target cuts?
        4. Is the share of "buy" ratings higher than 3 months ago?

ANALYSTS LEAN OPTIMISTIC
    "Sell" ratings are rare, partly because analysts' firms often want to
    do business with the companies they cover. So an average near "hold"
    is a lukewarm sign, not a neutral one, and the scoring reflects that.

CANADIAN STOCKS
    Coverage is thinner. Individual price targets often come from US
    analysts covering the New York listing, so they may be in US dollars.
    The summary targets are in the stock's own currency. Momentum only uses
    whether a target went UP or DOWN, so the currency doesn't matter there.

THE 0 TO 100 SCORES
    Each signal is +1 (good sign), 0 (neutral) or -1 (warning sign).
    "momentum_score" averages the four momentum signals. "score" averages
    all six. Both stretch onto 0 to 100, where 50 is neutral.

THE FUNCTIONS OTHER FILES USE
    analyst_summary(ticker)     -> everything above, plus the scores
    ratings_chart(ratings)      -> stacked bars of ratings over four months
    targets_chart(summary)      -> the range of price targets next to today's price
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

# Our own price fetcher. The dot means "from this same core/ folder".
from . import data


# ===========================================================================
# SETTINGS
# ===========================================================================

# Yahoo's rating columns, and the score each one stands for (1 best, 5 worst).
RATINGS = {"strongBuy": 1, "buy": 2, "hold": 3, "sell": 4, "strongSell": 5}
RATING_NAMES = {"strongBuy": "strong buy", "buy": "buy", "hold": "hold", "sell": "sell", "strongSell": "strong sell"}

# Yahoo's period codes, in friendlier words.
PERIOD_NAMES = {"0m": "Now", "-1m": "1 month ago", "-2m": "2 months ago", "-3m": "3 months ago"}
FORECAST_NAMES = {"0q": "This quarter", "+1q": "Next quarter", "0y": "This year", "+1y": "Next year"}

# Yahoo's short codes for rating changes.
CHANGE_NAMES = {
    "up": "upgrade",
    "down": "downgrade",
    "init": "started covering",
    "main": "kept rating",
    "reit": "repeated rating",
}

LOOKBACK_DAYS = 90            # how far back to look for rating changes

# Average rating thresholds (1 = strong buy ... 5 = strong sell).
GOOD_AVERAGE = 2.0            # this or better: a clear "buy" consensus
LUKEWARM_AVERAGE = 2.6        # this or worse: many analysts on the fence

# Price target upside thresholds, in %.
GOOD_UPSIDE = 15
BAD_UPSIDE = 0

FORECAST_MOVE = 2.0           # forecasts moving more than 2% in 90 days counts
GOOD_SHARE = 0.7              # 70% or more of changes pointing up counts as good
BAD_SHARE = 0.3               # 30% or less pointing up counts as bad
MIN_CHANGES = 3               # fewer changes than this is too few to judge
BUY_SHARE_MOVE = 5            # buy share moving 5 points or more counts


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _ratings_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Rating counts per month, plus the buy share and the average rating."""
    if raw.empty:
        return pd.DataFrame()

    table = raw.set_index("period")[list(RATINGS)].astype(float)
    table.index = [PERIOD_NAMES.get(p, p) for p in table.index]

    total = table.sum(axis=1)
    # Average rating: each count times its score (1 to 5), divided by the total.
    weights = pd.Series(RATINGS)
    average = (table * weights).sum(axis=1) / total
    buy_share = (table["strongBuy"] + table["buy"]) / total * 100

    table = table.rename(columns=RATING_NAMES)
    table["total"] = total
    table["buy_pct"] = buy_share
    table["average"] = average
    return table


def _targets(raw: dict) -> dict:
    """Price targets plus how far each one is from today's price, in %."""
    price = raw.get("current")
    targets = {"price": price}
    for name in ["low", "median", "mean", "high"]:
        value = raw.get(name)
        targets[name] = value
        targets[f"{name}_upside_pct"] = (value / price - 1) * 100 if value and price else np.nan
    return targets


def _target_move(row) -> str:
    """Did this analyst raise, lower, keep, or newly set their price target?

    Uses the actual numbers when both are there, because Yahoo's own word
    ("Adjusts") doesn't always say which way it went.
    """
    new, old = row.get("currentPriceTarget"), row.get("priorPriceTarget")
    if pd.notna(new) and new > 0 and pd.notna(old) and old > 0:
        if new > old:
            return "raised"
        if new < old:
            return "lowered"
        return "kept"
    if pd.notna(new) and new > 0:
        return "set"
    return ""


def _recent_changes(raw: pd.DataFrame, days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    """Rating and price target changes in the last `days` days, newest first."""
    columns = ["firm", "change", "from_rating", "to_rating", "target_move", "target_from", "target_to"]
    if raw.empty:
        return pd.DataFrame(columns=columns)

    cutoff = pd.Timestamp.today() - pd.Timedelta(days=days)
    recent = raw[raw.index >= cutoff]

    table = pd.DataFrame(
        {
            "firm": recent["Firm"],
            "change": recent["Action"].map(CHANGE_NAMES).fillna(recent["Action"]),
            "from_rating": recent["FromGrade"],
            "to_rating": recent["ToGrade"],
            "target_move": recent.apply(_target_move, axis=1),
            "target_from": recent["priorPriceTarget"].where(recent["priorPriceTarget"] > 0),
            "target_to": recent["currentPriceTarget"].where(recent["currentPriceTarget"] > 0),
        }
    )
    table.index = table.index.date          # keep just the day, not the time
    table.index.name = "date"
    return table


def _forecasts(trend: pd.DataFrame, revisions: pd.DataFrame) -> pd.DataFrame:
    """EPS forecasts now vs 30 and 90 days ago, plus how many analysts raised or cut them."""
    if trend.empty:
        return pd.DataFrame()

    table = pd.DataFrame(index=trend.index)
    table["now"] = trend["current"].astype(float)
    table["30_days_ago"] = trend["30daysAgo"].astype(float)
    table["90_days_ago"] = trend["90daysAgo"].astype(float)
    # % change over 90 days. Blank when the old forecast was zero or a loss,
    # because a % change from a negative number is confusing.
    old = table["90_days_ago"]
    table["change_90d_pct"] = ((table["now"] / old - 1) * 100).where(old > 0)

    if not revisions.empty:
        table["raised_30d"] = revisions["upLast30days"].reindex(table.index)
        table["cut_30d"] = revisions["downLast30days"].reindex(table.index)
    else:
        table["raised_30d"] = np.nan
        table["cut_30d"] = np.nan

    table.index = [FORECAST_NAMES.get(p, p) for p in table.index]
    return table


def _share_signal(ups: float, downs: float, what: str) -> dict:
    """Turn counts of 'up' and 'down' moves into a signal."""
    total = ups + downs
    if total == 0:
        return {"reading": "none", "points": 0, "why": f"No {what}."}
    if total < MIN_CHANGES:
        return {"reading": "too few", "points": 0, "why": f"Only {int(total)} {what}, too few to judge."}
    share_up = ups / total
    detail = f"{int(ups)} up, {int(downs)} down."
    if share_up >= GOOD_SHARE:
        return {"reading": "mostly up", "points": +1, "why": f"Most {what} pointed up. {detail}"}
    if share_up <= BAD_SHARE:
        return {"reading": "mostly down", "points": -1, "why": f"Most {what} pointed down. {detail}"}
    return {"reading": "mixed", "points": 0, "why": f"The {what} were split. {detail}"}


# ===========================================================================
# THE SIX SIGNALS
# ===========================================================================

def _average_signal(ratings: pd.DataFrame) -> dict:
    """Consensus: what's the average rating right now?"""
    if ratings.empty:
        return {"reading": "no coverage", "points": 0, "why": "No analysts cover this stock."}
    now = ratings.iloc[0]
    detail = f"{int(now['total'])} analysts, {now['buy_pct']:.0f}% say buy or strong buy."
    if now["average"] <= GOOD_AVERAGE:
        return {"reading": f"{now['average']:.2f}, buy", "points": +1, "why": f"A clear buy consensus. {detail}"}
    if now["average"] >= LUKEWARM_AVERAGE:
        return {"reading": f"{now['average']:.2f}, lukewarm", "points": -1,
                "why": f"Many analysts are on the fence. Since analysts lean optimistic, that's a lukewarm sign. {detail}"}
    return {"reading": f"{now['average']:.2f}, leaning buy", "points": 0, "why": f"Mostly positive, but not a clear consensus. {detail}"}


def _upside_signal(targets: dict) -> dict:
    """Consensus: how far is the average price target above today's price?"""
    upside = targets.get("mean_upside_pct", np.nan)
    if pd.isna(upside):
        return {"reading": "no targets", "points": 0, "why": "No analyst price targets."}
    detail = f"Average target {targets['mean']:.2f} vs today's {targets['price']:.2f}."
    if upside > GOOD_UPSIDE:
        return {"reading": f"{upside:+.1f}%", "points": +1, "why": f"Analysts see plenty of room to rise. {detail}"}
    if upside < BAD_UPSIDE:
        return {"reading": f"{upside:+.1f}%", "points": -1,
                "why": f"The price is already above the average target, so analysts see it as fully priced. {detail}"}
    return {"reading": f"{upside:+.1f}%", "points": 0, "why": f"Some room to rise, but not a lot. {detail}"}


def _forecast_change_signal(forecasts: pd.DataFrame) -> dict:
    """Momentum: are profit forecasts for this year and next higher than 90 days ago?"""
    if forecasts.empty:
        return {"reading": "no forecasts", "points": 0, "why": "No profit forecasts available."}
    changes = forecasts.loc[forecasts.index.isin(["This year", "Next year"]), "change_90d_pct"].dropna()
    if changes.empty:
        return {"reading": "n/a", "points": 0, "why": "Can't compare forecasts with 90 days ago."}
    average = changes.mean()
    detail = "; ".join(f"{name}: {value:+.1f}%" for name, value in changes.items())
    if average > FORECAST_MOVE:
        return {"reading": f"{average:+.1f}%", "points": +1, "why": f"Analysts expect more profit than 90 days ago. {detail}."}
    if average < -FORECAST_MOVE:
        return {"reading": f"{average:+.1f}%", "points": -1, "why": f"Analysts expect less profit than 90 days ago. {detail}."}
    return {"reading": f"{average:+.1f}%", "points": 0, "why": f"Forecasts have barely moved. {detail}."}


def _revisions_signal(forecasts: pd.DataFrame) -> dict:
    """Momentum: in the last 30 days, did more analysts raise forecasts than cut them?"""
    if forecasts.empty:
        return {"reading": "no forecasts", "points": 0, "why": "No profit forecasts available."}
    years = forecasts.loc[forecasts.index.isin(["This year", "Next year"])]
    ups = years["raised_30d"].fillna(0).sum()
    downs = years["cut_30d"].fillna(0).sum()
    return _share_signal(ups, downs, "forecast changes in the last 30 days")


def _changes_signal(changes: pd.DataFrame) -> dict:
    """Momentum: more upgrades and target raises than downgrades and cuts in 90 days?"""
    ups = (changes["change"] == "upgrade").sum() + (changes["target_move"] == "raised").sum()
    downs = (changes["change"] == "downgrade").sum() + (changes["target_move"] == "lowered").sum()
    return _share_signal(ups, downs, f"rating and target changes in the last {LOOKBACK_DAYS} days")


def _buy_share_signal(ratings: pd.DataFrame) -> dict:
    """Momentum: is the share of buy ratings higher than 3 months ago?"""
    if len(ratings) < 2:
        return {"reading": "n/a", "points": 0, "why": "No rating history to compare with."}
    now, then = ratings["buy_pct"].iloc[0], ratings["buy_pct"].iloc[-1]
    change = now - then
    detail = f"{then:.0f}% {ratings.index[-1]} vs {now:.0f}% now."
    if change >= BUY_SHARE_MOVE:
        return {"reading": f"{change:+.0f} points", "points": +1, "why": f"More analysts say buy than before. {detail}"}
    if change <= -BUY_SHARE_MOVE:
        return {"reading": f"{change:+.0f} points", "points": -1, "why": f"Fewer analysts say buy than before. {detail}"}
    return {"reading": f"{change:+.0f} points", "points": 0, "why": f"About the same share as before. {detail}"}


# ===========================================================================
# THE MAIN FUNCTION
# ===========================================================================

def analyst_summary(ticker: str) -> dict:
    """What analysts think of one stock, and which way their views are moving.

    Returns a dictionary:
        {
          "company":        "NVDA",
          "ratings":        rating counts now and 1 to 3 months ago, with
                            the buy share and average rating (1 best, 5 worst)
          "targets":        low, median, mean and high price targets, and the
                            % gap from today's price to each
          "changes":        rating and target changes in the last 90 days
          "forecasts":      EPS forecasts now vs 30 and 90 days ago, and how
                            many analysts raised or cut them in 30 days
          "signals":        six signals: kind (consensus or momentum),
                            reading, points (+1, 0, -1), why
          "momentum_score": 0 to 100 from the four momentum signals
          "score":          0 to 100 from all six signals
          "verdict":        "positive", "mixed", "negative" or "no coverage"
          "target_currency_note":  a caution for stocks not priced in US dollars
        }
    """
    ticker = data.clean_tickers(ticker)[0]
    raw = data.get_analyst_data(ticker)

    ratings = _ratings_table(raw["ratings"])
    targets = _targets(raw["targets"])
    changes = _recent_changes(raw["actions"])
    forecasts = _forecasts(raw["forecasts"], raw["revisions"])

    signals = {
        "Average rating": ("consensus", _average_signal(ratings)),
        "Price target upside": ("consensus", _upside_signal(targets)),
        "Forecast changes (90 days)": ("momentum", _forecast_change_signal(forecasts)),
        "Forecast revisions (30 days)": ("momentum", _revisions_signal(forecasts)),
        "Rating and target changes (90 days)": ("momentum", _changes_signal(changes)),
        "Buy share trend": ("momentum", _buy_share_signal(ratings)),
    }
    signals = pd.DataFrame(
        [{"signal": name, "kind": kind, **result} for name, (kind, result) in signals.items()]
    ).set_index("signal")
    signals["points"] = signals["points"].astype(int)

    # No analysts at all (funds, tiny companies): no scores.
    if ratings.empty and forecasts.empty and pd.isna(targets.get("mean_upside_pct", np.nan)):
        momentum_score = score = np.nan
        verdict = "no coverage"
    else:
        momentum = signals[signals["kind"] == "momentum"]["points"]
        momentum_score = float(50 + 50 * momentum.mean())
        score = float(50 + 50 * signals["points"].mean())
        verdict = "positive" if score >= 60 else "negative" if score <= 40 else "mixed"

    # Individual targets for non-US-dollar stocks may be in US dollars.
    currency = data.get_info(ticker)["currency"]
    note = ""
    if currency and currency != "USD":
        note = (f"{ticker} trades in {currency}. The summary targets are in {currency}, but individual "
                f"analysts' targets often come from the US listing and may be in US dollars.")

    return {
        "company": ticker,
        "ratings": ratings,
        "targets": targets,
        "changes": changes,
        "forecasts": forecasts,
        "signals": signals,
        "momentum_score": momentum_score,
        "score": score,
        "verdict": verdict,
        "target_currency_note": note,
    }


# ===========================================================================
# CHARTS
# ===========================================================================

def ratings_chart(ratings: pd.DataFrame, company: str = ""):
    """Stacked bars of the rating counts, oldest month on the left.

    Pass in analyst_summary(...)["ratings"].
    """
    columns = list(RATING_NAMES.values())
    # Oldest first, and one row per (month, rating) pair, which plotly likes.
    chart_data = ratings[columns].iloc[::-1].reset_index(names="month")
    chart_data = chart_data.melt(id_vars="month", var_name="rating", value_name="analysts")

    fig = px.bar(
        chart_data, x="month", y="analysts", color="rating",
        category_orders={"rating": columns},
        color_discrete_map={
            "strong buy": "#15803d", "buy": "#86efac", "hold": "#d1d5db",
            "sell": "#fca5a5", "strong sell": "#b91c1c",
        },
        title=f"{company} analyst ratings over four months".strip(),
        labels={"month": "", "analysts": "Number of analysts", "rating": ""},
    )
    return fig


def targets_chart(summary: dict):
    """The range of analyst price targets, with today's price marked.

    Pass in analyst_summary(...).
    """
    targets = summary["targets"]
    points = {name: targets.get(name) for name in ["low", "median", "mean", "high"]}
    points = {name: value for name, value in points.items() if value}

    fig = go.Figure()
    # A grey bar from the lowest target to the highest.
    fig.add_trace(go.Scatter(
        x=[points.get("low"), points.get("high")], y=["Targets", "Targets"],
        mode="lines", line={"color": "lightgrey", "width": 14}, showlegend=False, hoverinfo="skip",
    ))
    # A dot for each target, with its name and value written next to it.
    # The median and mean are often close together, so the median's label
    # goes BELOW its dot and the others go above. That stops them overlapping.
    positions = ["bottom center" if name == "median" else "top center" for name in points]
    fig.add_trace(go.Scatter(
        x=list(points.values()), y=["Targets"] * len(points), mode="markers+text",
        marker={"size": 12, "color": "#2563eb"},
        text=[f"{name}<br>{value:.2f}" for name, value in points.items()],
        textposition=positions, showlegend=False,
        hovertemplate="%{text}<extra></extra>",
    ))
    # A red line at today's price, labelled at the top so it clears the axis numbers.
    if targets.get("price"):
        fig.add_vline(x=targets["price"], line_color="red", line_dash="dash",
                      annotation_text=f"today {targets['price']:.2f}", annotation_position="top right")

    fig.update_layout(
        title=f"{summary['company']}: where analysts think the price will be in a year",
        height=320, yaxis={"visible": False}, xaxis_title="Price",
    )
    return fig
