"""
economy.py - MyAnalysis Part 3C: "Is the economy helping or hurting?"

WHAT THIS FILE DOES
    Reads three big numbers about the US economy, labels each one in plain
    English, and works out whether each one is a HEADWIND (holding a stock
    back) or a TAILWIND (pushing it along) for a particular company.

WHY ONLY THE US
    Most Canadian investors hold lots of US stocks, and the US 10-year yield
    is the world's benchmark interest rate. Canada's rates and economy
    usually move the same way. So every stock uses the US numbers.

THE THREE NUMBERS
    Interest rates   the US 10-year government bond yield
    Inflation        how much higher prices are than a year ago (target: 2%)
    Economic growth  GDP growth, averaged over the last four quarters

HOW HEADWINDS AND TAILWINDS ARE WORKED OUT
    1. Each number gets a direction:
         rates      rising (+1), steady (0), falling (-1)
         inflation  above target (+1), near target (0), below target (-1)
         growth     strong (+1), normal (0), weak or shrinking (-1)
    2. Each sector has a sensitivity to each number, from common rules of
       thumb. Banks earn more when rates rise (+1). Real estate suffers (-1).
    3. Effect = direction x sensitivity. Above 0 is a tailwind, below 0 a headwind.
    4. The company's own numbers can make the rates effect bigger. Lots of
       debt, or a high P/E, makes rising rates hurt more (and falling rates
       help more).

THE 0 TO 100 SCORE
    50 means the economy is neutral for this stock. Higher means it's
    helping, lower means it's hurting. 60 or more is "helping", 40 or less
    is "hurting", in between is "mixed".

THESE ARE RULES OF THUMB
    They describe what USUALLY happens, not what WILL happen.

THE FUNCTIONS OTHER FILES USE
    snapshot()               -> the three numbers now, a year ago, and their labels
    economy_effects(ticker)  -> headwinds and tailwinds for one stock, plus a score
    sensitivity_table()      -> the rules of thumb for every sector
    economy_chart()          -> five-year chart of all three numbers
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

# The three topics, in the order they're shown.
TOPICS = ["Interest rates", "Inflation", "Economic growth"]

# Interest rates: a move smaller than this over a year counts as "steady".
RATE_STEADY_BAND = 0.25          # percentage points

# Inflation: central banks aim for 2%.
INFLATION_TARGET = 2.0
INFLATION_HIGH = 3.0             # above this is "above target"
INFLATION_LOW = 1.5              # below this is "below target"

# Economic growth, as the average of the last four quarters.
GROWTH_STRONG = 3.0              # above this is "strong"
GROWTH_WEAK = 1.5                # below this is "weak" (below 0 is "shrinking")

# Company numbers that make rising rates hurt more.
HIGH_DEBT_TO_EQUITY = 1.5
HIGH_PE = 30

# How each sector usually reacts. Yahoo's sector names, then:
#   (when rates RISE, when inflation is HIGH, when growth is STRONG)
#   +1 = usually helps, -1 = usually hurts, 0 = little effect
SECTOR_SENSITIVITY = {
    "Technology":             (-1,  0, +1),
    "Communication Services": (-1,  0, +1),
    "Consumer Cyclical":      (-1, -1, +1),
    "Consumer Defensive":     ( 0,  0,  0),
    "Healthcare":             ( 0,  0,  0),
    "Financial Services":     (+1,  0, +1),
    "Industrials":            ( 0,  0, +1),
    "Basic Materials":        ( 0, +1, +1),
    "Energy":                 ( 0, +1, +1),
    "Real Estate":            (-1,  0,  0),
    "Utilities":              (-1, -1,  0),
}

# Plain-English reasons behind each rule of thumb.
# Format:  topic: {sensitivity: reason}
REASONS = {
    "Interest rates": {
        -1: "Higher rates make borrowing pricier and make future profits worth less today.",
        +1: "Banks earn more on their loans when rates are higher.",
        0: "This sector usually isn't very sensitive to interest rates.",
    },
    "Inflation": {
        +1: "Rising prices for oil, metals and other raw materials boost what these companies sell.",
        -1: "Rising prices squeeze customers' budgets and push up costs faster than prices can follow.",
        0: "This sector can usually pass rising costs on to its customers.",
    },
    "Economic growth": {
        +1: "A strong economy means more spending on things people and businesses want but don't strictly need.",
        0: "People buy these things in good times and bad, so growth matters less.",
    },
}


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _rate_direction(change: float) -> tuple:
    """(label, signal) for interest rates, from their change over a year."""
    if pd.isna(change):
        return "unavailable", 0
    if change > RATE_STEADY_BAND:
        return "rising", +1
    if change < -RATE_STEADY_BAND:
        return "falling", -1
    return "steady", 0


def _inflation_level(value: float) -> tuple:
    """(label, signal) for inflation, compared with the 2% target."""
    if pd.isna(value):
        return "unavailable", 0
    if value > INFLATION_HIGH:
        return "above target", +1
    if value < INFLATION_LOW:
        return "below target", -1
    return "near target", 0


def _growth_level(value: float) -> tuple:
    """(label, signal) for economic growth."""
    if pd.isna(value):
        return "unavailable", 0
    if value > GROWTH_STRONG:
        return "strong", +1
    if value < 0:
        return "shrinking", -1
    if value < GROWTH_WEAK:
        return "weak", -1
    return "normal", 0


def _is_are(topic: str) -> str:
    """ "Interest rates are", but "Inflation is" and "Economic growth is"."""
    return f"{topic} are" if topic == "Interest rates" else f"{topic} is"


def _value_a_year_before(series: pd.Series) -> float:
    """The value about one year before the newest one."""
    if series.empty:
        return np.nan
    a_year_earlier = series.index[-1] - pd.DateOffset(years=1)
    return data.price_on(series, a_year_earlier)


# ===========================================================================
# 1. THE ECONOMY RIGHT NOW
# ===========================================================================

def snapshot() -> pd.DataFrame:
    """The three economy numbers now and a year ago, with plain-English labels.

    Returns a table with one row per topic and these columns:
        now          the latest reading, in %
        a_year_ago   the reading about a year earlier, in %
        change       now minus a year ago, in percentage points
        label        "rising", "above target", "normal" and so on
        signal       +1, 0 or -1, used to work out headwinds and tailwinds
        as_of        the date of the latest reading
        source       where the number came from

    If a source is down, that row shows blanks and "unavailable".
    """
    rows = []

    # --- Interest rates: the 10-year yield, daily --------------------------
    rates = data.get_us_10y_yield()
    now = rates.iloc[-1] if not rates.empty else np.nan
    year_ago = _value_a_year_before(rates)
    label, signal = _rate_direction(now - year_ago)
    rows.append({
        "topic": "Interest rates", "now": now, "a_year_ago": year_ago,
        "change": now - year_ago, "label": label, "signal": signal,
        "as_of": rates.index[-1].date() if not rates.empty else None,
        "source": "US 10-year bond yield (Yahoo Finance)",
    })

    # --- Inflation: yearly price rise, monthly ------------------------------
    inflation = data.get_us_inflation()
    now = inflation.iloc[-1] if not inflation.empty else np.nan
    year_ago = _value_a_year_before(inflation)
    label, signal = _inflation_level(now)
    rows.append({
        "topic": "Inflation", "now": now, "a_year_ago": year_ago,
        "change": now - year_ago, "label": label, "signal": signal,
        "as_of": inflation.index[-1].date() if not inflation.empty else None,
        "source": "US consumer prices (Bureau of Labor Statistics)",
    })

    # --- Economic growth: average of the last 4 quarters --------------------
    # One quarter on its own jumps around a lot (0.1% one quarter, 4.0% the
    # next), so we average the latest four, i.e. the past year.
    growth = data.get_us_gdp_growth()
    now = growth.iloc[-4:].mean() if len(growth) >= 4 else np.nan
    year_ago = growth.iloc[-8:-4].mean() if len(growth) >= 8 else np.nan
    label, signal = _growth_level(now)
    rows.append({
        "topic": "Economic growth", "now": now, "a_year_ago": year_ago,
        "change": now - year_ago, "label": label, "signal": signal,
        "as_of": growth.index[-1].date() if not growth.empty else None,
        "source": "US GDP growth, last 4 quarters averaged (Bureau of Economic Analysis)",
    })

    return pd.DataFrame(rows).set_index("topic")


# ===========================================================================
# 2. HEADWINDS AND TAILWINDS FOR ONE STOCK
# ===========================================================================

def _sensitivity(sector) -> tuple:
    """The sector's (rates, inflation, growth) sensitivity.

    Funds and anything without a sector get the average of all sectors,
    which stands in for "the whole market".
    """
    if sector in SECTOR_SENSITIVITY:
        return SECTOR_SENSITIVITY[sector]
    all_rows = np.array(list(SECTOR_SENSITIVITY.values()))
    return tuple(all_rows.mean(axis=0).round(2))


def _company_rate_tweaks(ticker: str, signal: int) -> tuple:
    """Extra rates effect from the company's own debt and P/E.

    Returns (extra effect, list of reasons). Only applies when rates are
    actually moving (signal is +1 or -1).
    """
    if signal == 0:
        return 0.0, []

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")      # Part 3A already showed these
        ratios = fin.ratios_table(ticker)
    if ratios.empty:
        return 0.0, []

    extra, reasons = 0.0, []
    moving = "rising" if signal > 0 else "falling"
    effect_word = "hurt more" if signal > 0 else "help more"

    # Lots of debt: rate changes hit its interest bill. Banks are skipped,
    # because borrowing (customer deposits) is their normal business.
    debt = fin.latest(ratios, "debt_to_equity")
    industry = data.get_info(ticker)["industry"] or ""
    if pd.notna(debt) and debt > HIGH_DEBT_TO_EQUITY and not industry.startswith(fin.FINANCIAL_INDUSTRIES):
        extra -= 0.5 * signal
        reasons.append(f"It carries a lot of debt ({debt:.1f}x equity), so {moving} rates {effect_word}.")

    # High P/E: much of its value is profit expected far in the future,
    # and higher rates shrink what future money is worth today.
    pe = fin.latest(ratios, "pe_ratio")
    if pd.notna(pe) and pe > HIGH_PE:
        extra -= 0.5 * signal
        reasons.append(f"Its P/E is high ({pe:.0f}x), so {moving} rates {effect_word}: its value leans on far-future profits.")

    return extra, reasons


def _verdict(effect: float) -> str:
    """Turn one topic's effect into a word."""
    if effect >= 0.5:
        return "tailwind"
    if effect <= -0.5:
        return "headwind"
    return "neutral"


def economy_effects(ticker: str) -> dict:
    """Is the economy helping or hurting this stock right now?

    Returns a dictionary:
        {
          "company": "NVDA",
          "sector":  "Technology",
          "effects": table with one row per topic:
                       reading         the economy number and its label
                       sector_effect   from the sector's rule of thumb
                       company_effect  extra from the company's debt and P/E
                       total           the two added together
                       verdict         "tailwind", "headwind" or "neutral"
                       why             plain-English reasons
          "score":   0 to 100, where 50 is neutral
          "verdict": "helping", "mixed" or "hurting"
        }
    """
    ticker = data.clean_tickers(ticker)[0]
    sector = data.get_info(ticker)["sector"]
    if sector not in SECTOR_SENSITIVITY:
        warnings.warn(f"{ticker} has no sector (funds don't), so the whole-market average is used.")

    economy = snapshot()
    sensitivities = dict(zip(TOPICS, _sensitivity(sector)))

    rows = []
    for topic in TOPICS:
        reading = economy.loc[topic]
        signal = int(reading["signal"])
        sensitivity = sensitivities[topic]

        # --- The sector's rule of thumb --------------------------------------
        sector_effect = float(sensitivity * signal)
        if reading["label"] == "unavailable":
            why = ["No data right now, so this counts as neutral."]
        elif signal == 0:
            why = [f"{_is_are(topic)} {reading['label']}, so no big push either way."]
        elif sector not in SECTOR_SENSITIVITY:
            # Funds: describe the whole-market average instead of a sector.
            size = "small" if abs(sector_effect) < 0.5 else ("negative" if sector_effect < 0 else "positive")
            why = [f"{_is_are(topic)} {reading['label']}. Averaged across all sectors, the effect is {size}."]
        else:
            # The reasons describe what happens when the number goes UP.
            key = int(np.sign(sensitivity))
            why = [REASONS[topic].get(key, REASONS[topic][0])]
            # If it's going DOWN (rates falling, inflation or growth low),
            # the same rule works the other way round.
            if signal < 0 and key != 0:
                why.append(f"{_is_are(topic)} {reading['label']} now, so that works in reverse.")

        # --- The company's own numbers (rates only) ---------------------------
        company_effect, extra_reasons = (0.0, [])
        if topic == "Interest rates":
            company_effect, extra_reasons = _company_rate_tweaks(ticker, signal)
        why += extra_reasons

        total = sector_effect + company_effect
        rows.append({
            "topic": topic,
            "reading": f"{reading['now']:.2f}%, {reading['label']}" if pd.notna(reading["now"]) else "unavailable",
            "sector_effect": sector_effect,
            "company_effect": company_effect,
            "total": total,
            "verdict": _verdict(total),
            "why": " ".join(why),
        })

    effects = pd.DataFrame(rows).set_index("topic")

    # Average effect, stretched onto 0 to 100 with 50 as neutral.
    # Effects run from about -2 to +2, so x25 maps them onto 0 to 100.
    score = float(np.clip(50 + 25 * effects["total"].mean(), 0, 100))
    if score >= 60:
        overall = "helping"
    elif score <= 40:
        overall = "hurting"
    else:
        overall = "mixed"

    return {"company": ticker, "sector": sector, "effects": effects, "score": score, "verdict": overall}


# ===========================================================================
# 3. THE RULES OF THUMB, AS A TABLE
# ===========================================================================

def sensitivity_table() -> pd.DataFrame:
    """How each sector usually reacts, in words."""
    words = {+1: "usually helps", -1: "usually hurts", 0: "little effect"}
    table = pd.DataFrame(
        SECTOR_SENSITIVITY,
        index=["When rates rise", "When inflation is high", "When growth is strong"],
    ).T
    return table.replace(words)


# ===========================================================================
# 4. FIVE-YEAR CHART
# ===========================================================================

def economy_chart():
    """One chart with all three numbers over about five years, in %.

    The 10-year yield is averaged by month so it's as smooth as the others.
    A dashed line marks the 2% inflation target.
    """
    five_years_ago = pd.Timestamp.today() - pd.DateOffset(years=5)
    series = {
        "10-year yield %": data.get_us_10y_yield().resample("MS").mean(),
        "Inflation %": data.get_us_inflation(),
        "GDP growth % (quarterly)": data.get_us_gdp_growth(),
    }

    # Reshape into one long table (date, which number, value), which plotly likes.
    pieces = []
    for name, values in series.items():
        values = values[values.index >= five_years_ago]
        pieces.append(pd.DataFrame({"date": values.index, "value": values.values, "number": name}))
    chart_data = pd.concat(pieces)

    fig = px.line(
        chart_data, x="date", y="value", color="number", markers=False,
        title="The US economy over five years",
        labels={"date": "", "value": "%", "number": ""},
    )
    fig.add_hline(y=INFLATION_TARGET, line_dash="dash", annotation_text="2% inflation target")
    return fig
