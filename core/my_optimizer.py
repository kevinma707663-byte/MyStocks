"""
my_optimizer.py - the MyOptimizer section: "Which mix of stocks best fits my rules?"

WHAT THIS FILE DOES
    You pick the stocks and set the rules. It tries thousands of different
    mixes (how much money goes in each stock) on the past few years of
    prices, throws out every mix that breaks your rules, fine-tunes the best
    one left, and shows it next to your current mix.

THE RULES YOU CAN SET (and their starting values)
    goal               what "best" means:
                         "sharpe"      highest Sharpe ratio (the default)
                         "low_risk"    smallest yearly swings
                         "high_return" highest yearly return
    max_drawdown_pct   the biggest drop from a peak you can stomach      25
    min_return_pct     the least you'll accept per year                  8
    max_weight_pct     the most in any one stock                         30
    min_weight_pct     the least in any one stock (0 lets it drop some)  0
    years              how many years of past prices to test on          3

THE WORDS, IN PLAIN ENGLISH
    Yearly return   how fast the money grew per year, on average ("CAGR")
    Yearly swings   how much it bounced around ("volatility"). Bigger means bumpier.
    Sharpe ratio    (average yearly return - what a safe 3-month US bill pays) / yearly swings.
                    Return per bump. Above 1 is good, above 2 is excellent.
                    This is the standard version: the average daily return
                    x 252 trading days. It comes out a little higher than the
                    "yearly return" above, because bumps slow down real growth.
    Worst drop      the biggest fall from a peak to a low ("max drawdown").
                    -25% means at its worst, $10,000 had shrunk to $7,500.

HOW IT WORKS
    1. Download dividend-adjusted daily prices for every stock.
    2. Make 20,000 random mixes that follow the weight limits, plus a few
       "corner" mixes that pile as much as allowed into the best stocks.
       Random mixes almost never land on corners, and that's where the
       highest-return mixes live, so tough return rules aren't missed.
    3. For each mix, replay the past: what it returned, how much it swung,
       and its worst drop. The mix is kept the same every day.
    4. Keep only the mixes that follow your rules, and pick the best for your goal.
    5. Fine-tune that mix with a math solver (scipy), and keep the result
       only if it still follows every rule.

CURRENCIES
    Each stock's returns are measured in its own currency, the same choice
    as MyStocks. Exchange-rate swings are left out.

IT'S BASED ON THE PAST
    The best mix for the last three years is rarely the best for the next
    three. Optimizers love whatever did best recently, which is why the
    "most in one stock" rule matters. Use it as a starting point.

MYEDIT: TWEAK THE BEST MIX BY HAND
    my_edit(result, {"KO": 20}) starts from the best mix and changes only
    the stocks you name. The others grow or shrink in proportion, so the
    total stays 100%. You see your edit next to your current mix and the
    best mix. MyEdit lets you break your rules on purpose, and tells you
    which ones your edit breaks. You can edit an edit, too.

THE FUNCTIONS OTHER FILES USE
    optimize(tickers, ...)               -> the best mix for a list of stocks
    optimize_portfolio(portfolio, ...)   -> the same, starting from what you own
    my_edit(result, changes)             -> MyEdit: your hand-tweaked version of the best mix
    cloud_chart(result)                  -> every mix tried, by risk and return
    growth_chart(result)                 -> $10,000 in each mix
    weights_chart(result)                -> each mix's weights, side by side
"""

# Lets us write type hints like list[str] on older Python versions too.
from __future__ import annotations

# warnings: a polite way to say "something looks off" without crashing.
import warnings

# numpy: fast math on big grids of numbers.
import numpy as np

# pandas: the library for tables of numbers.
import pandas as pd

# plotly: interactive charts.
import plotly.express as px
import plotly.graph_objects as go

# scipy's solver fine-tunes the best mix found.
from scipy.optimize import minimize

# Our own files. The dot means "from this same core/ folder".
from . import data
from . import my_stocks as ms
from . import portfolio as pf


# ===========================================================================
# SETTINGS
# ===========================================================================

GOALS = {"sharpe": "highest Sharpe ratio", "low_risk": "lowest risk", "high_return": "highest return"}

GOAL = "sharpe"
MAX_DRAWDOWN_PCT = 25
MIN_RETURN_PCT = 8
MAX_WEIGHT_PCT = 30
MIN_WEIGHT_PCT = 0
YEARS = 3

MIXES = 20_000            # how many random mixes to try
TRADING_DAYS = 252        # trading days in a year
MIN_SHARED_DAYS = 20      # fewer days of shared price history than this is too little to measure
SEARCH_STARTS = 5         # how many of the closest random mixes the closer search starts from
START_MONEY = 10_000      # for the growth chart
SEED = 42                 # fixed, so the same inputs always give the same answer
CHUNK = 2_000             # mixes replayed at a time, to keep memory use small

CURRENT, BEST, EDIT = "Your current mix", "Best mix", "Your edit"

# Column names in the weights table, and the mix each one belongs to.
WEIGHT_COLUMNS = {"current %": CURRENT, "best %": BEST, "edit %": EDIT}

# One fixed colour per mix, so every chart matches: grey current, red best, orange edit.
MIX_COLOURS = {CURRENT: "#64748b", BEST: "#dc2626", EDIT: "#f59e0b"}

# Columns of the comparison table, fixed so it's never shapeless (even when empty).
SUMMARY_COLUMNS = ["yearly return %", "yearly swings %", "Sharpe ratio", "worst drop %", f"${START_MONEY:,} became"]


# ===========================================================================
# SMALL HELPERS
# ===========================================================================

def _fit_limits(weights: np.ndarray, low: float, high: float) -> np.ndarray:
    """Nudge every mix so each weight is between `low` and `high` and they add up to 1.

    weights has one row per mix. Clipping alone breaks the "adds up to 1"
    rule, so whatever is missing (or extra) gets shared out among the
    stocks that still have room to move.
    """
    w = np.clip(weights, low, high)
    for _ in range(50):
        gap = 1 - w.sum(axis=1, keepdims=True)          # >0: too little, <0: too much
        if np.abs(gap).max() < 1e-12:
            break
        room = np.where(gap > 0, high - w, w - low)     # how far each weight can still move
        total = room.sum(axis=1, keepdims=True)
        share = np.divide(room, total, out=np.zeros_like(room), where=total > 0)
        w = np.clip(w + gap * share, low, high)
    return w


def _replay(returns: np.ndarray, weights: np.ndarray, risk_free: float) -> dict:
    """Replay the past for many mixes at once.

    returns  one row per day, one column per stock (daily % changes as decimals)
    weights  one row per mix, one column per stock

    Returns arrays, one value per mix: yearly return, yearly swings,
    Sharpe ratio and worst drop, all as decimals (0.08 means 8%).
    """
    years = returns.shape[0] / TRADING_DAYS
    pieces = {"return": [], "average": [], "swings": [], "drop": []}

    for start in range(0, len(weights), CHUNK):
        w = weights[start:start + CHUNK]
        daily = returns @ w.T                          # each mix's daily % change
        growth = np.cumprod(1 + daily, axis=0)         # $1 growing day by day
        pieces["return"].append(growth[-1] ** (1 / years) - 1)
        # The average day's return x 252 days: the standard input to Sharpe.
        pieces["average"].append(daily.mean(axis=0) * TRADING_DAYS)
        pieces["swings"].append(daily.std(axis=0, ddof=1) * np.sqrt(TRADING_DAYS))
        # The worst drop: how far below its highest point so far it ever fell.
        # The starting $1 counts as a high point too.
        peak = np.maximum(np.maximum.accumulate(growth, axis=0), 1.0)
        pieces["drop"].append((growth / peak - 1).min(axis=0))

    result = {name: np.concatenate(values) for name, values in pieces.items()}
    # A mix with no swings at all (only possible with made-up prices) would
    # divide by zero. numpy then gives "infinity" (endless return per bump),
    # which is fine here, so the warning about it is switched off.
    with np.errstate(divide="ignore", invalid="ignore"):
        result["sharpe"] = (result["average"] - risk_free) / result["swings"]
    return result


def _corner_mixes(returns: np.ndarray, low: float, high: float) -> np.ndarray:
    """A few hand-built "corner" mixes that random mixes almost never hit.

    Each one fills the stocks in a chosen order, giving each as much as the
    limit allows before moving on to the next. The three orders are:
    best return first, smallest worst drop first, and calmest first.
    High-return mixes are often corners like these, so they're worth trying.
    They don't cover every possibility (a well-balanced mix in the middle
    can beat them), which is why _search_for_a_fit() exists.
    """
    n = returns.shape[1]
    alone = _replay(returns, np.eye(n), 0.0)          # each stock on its own
    orders = [
        np.argsort(-alone["return"]),                 # best return first
        np.argsort(-alone["drop"]),                   # smallest worst drop first
        np.argsort(alone["swings"]),                  # calmest first
    ]
    corners = []
    for order in orders:
        w = np.full(n, low)                           # everyone starts at the minimum
        left = 1 - low * n                            # what's left to hand out
        for i in order:
            extra = min(high - low, left)             # as much as this stock may take
            w[i] += extra
            left -= extra
        corners.append(w)
    return np.array(corners)


def _search_for_a_fit(returns: np.ndarray, starts: list, low: float, high: float,
                      min_return: float, max_drop: float, risk_free: float):
    """Look harder for a mix that follows both rules, when none of the tried mixes did.

    From each starting mix, scipy's solver looks for the mix that beats
    BOTH rules by the widest margin. Returns the first mix that truly
    follows both, or None if none was found. None doesn't prove no mix
    exists: it means this search didn't find one.
    """
    n = returns.shape[1]

    def margins(w):
        # How far a mix is past each rule: positive means it follows it.
        stats = _replay(returns, np.asarray(w)[None, :], risk_free)
        return stats["return"][0] - min_return, stats["drop"][0] - max_drop

    for start in starts:
        # The solver works on n weights plus one extra number, m: the margin
        # both rules must beat. Making m as big as possible pushes the mix
        # toward following both rules with room to spare.
        x0 = np.append(start, min(margins(start)))
        solver = minimize(
            lambda x: -x[-1], x0, method="SLSQP",
            bounds=[(low, high)] * n + [(-10, 10)],
            constraints=[
                {"type": "eq", "fun": lambda x: x[:-1].sum() - 1},
                {"type": "ineq", "fun": lambda x: margins(x[:-1])[0] - x[-1]},
                {"type": "ineq", "fun": lambda x: margins(x[:-1])[1] - x[-1]},
            ],
            options={"maxiter": 200},
        )
        # Keep it only if, checked again from scratch, it truly follows both rules.
        w = _fit_limits(np.asarray(solver.x[:-1])[None, :], low, high)[0]
        if min(margins(w)) >= -1e-9:
            return w
    return None


def _goal_value(stats: dict, goal: str) -> np.ndarray:
    """A number to MAXIMIZE for each mix, whatever the goal."""
    if goal == "low_risk":
        return -stats["swings"]           # smaller swings = better, so flip the sign
    if goal == "high_return":
        return stats["return"]
    return stats["sharpe"]


def _summary_row(stats: dict, i: int, growth_end: float) -> dict:
    """One mix's numbers, as percents, for the comparison table."""
    return {
        "yearly return %": stats["return"][i] * 100,
        "yearly swings %": stats["swings"][i] * 100,
        "Sharpe ratio": stats["sharpe"][i],
        "worst drop %": stats["drop"][i] * 100,
        f"${START_MONEY:,} became": growth_end,
    }


# ===========================================================================
# THE MAIN FUNCTION
# ===========================================================================

def optimize(
    tickers: list,
    goal: str = GOAL,
    max_drawdown_pct: float = MAX_DRAWDOWN_PCT,
    min_return_pct: float = MIN_RETURN_PCT,
    max_weight_pct: float = MAX_WEIGHT_PCT,
    min_weight_pct: float = MIN_WEIGHT_PCT,
    years: int = YEARS,
    current: dict = None,
) -> dict:
    """Find the best mix of these stocks that follows your rules.

    tickers  the stocks to mix, like ["AAPL", "KO", "RY.TO"]
    current  optional, your current mix as {ticker: % of your money}, so
             it can be shown next to the best mix
    The rules are explained at the top of this file.

    Returns a dictionary:
        {
          "status":      "ok", or "no mix found" when no mix following every
                         rule was found (that doesn't prove none exists)
          "message":     a plain-English sentence about the result
          "tickers", "goal", "rules", "period", "risk_free_pct",
          "comparison":  table: your current mix vs the best mix
          "weights":     table: each stock's current %, best % and the change
          "growth":      table: $10,000 growing day by day in each mix
          "cloud":       table: every mix tried, and whether it fits your rules
          "best_weights", "current_weights":  {ticker: %}
        }

    Raises a ValueError with a plain-English message when the inputs can't
    work, like only one stock, or weight limits that can't add up to 100%.
    """
    if goal not in GOALS:
        raise ValueError(f"Goal must be one of {list(GOALS)}.")

    # Every rule must be a real number. A blank (NaN) would quietly pass
    # every check below, so it's turned away here.
    max_drawdown_pct = pf._finite_number(max_drawdown_pct, "The biggest drop allowed")
    min_return_pct = pf._finite_number(min_return_pct, "The minimum yearly return")
    max_weight_pct = pf._finite_number(max_weight_pct, "The most in one stock")
    min_weight_pct = pf._finite_number(min_weight_pct, "The least in one stock")
    years = int(pf._positive_number(years, "Years of history"))
    if max_drawdown_pct < 0:
        raise ValueError("The biggest drop allowed can't be below 0%.")
    if not (0 < max_weight_pct <= 100 and 0 <= min_weight_pct <= max_weight_pct):
        raise ValueError("Weight limits must be between 0% and 100%, with the least no more than the most.")
    if years < 1:
        raise ValueError("Years of history must be at least 1.")

    # --- 1. Prices and daily returns -----------------------------------------
    tickers = data.clean_tickers(tickers)
    returns = data.get_daily_returns(tickers, years)
    tickers = list(returns.columns)                   # some may have been dropped
    n = len(tickers)
    if n < 2:
        raise ValueError("MyOptimizer needs at least 2 stocks with price history to mix.")
    # The days every stock traded. Stocks whose histories barely overlap
    # leave too few days to measure anything.
    if returns.shape[0] < MIN_SHARED_DAYS:
        raise ValueError(
            f"These stocks only share {returns.shape[0]} trading days of price history, too few to measure. "
            f"Try stocks that have all traded for at least a month."
        )
    if returns.shape[0] < TRADING_DAYS:
        warnings.warn(f"Only {returns.shape[0]} trading days of shared history, less than a year. Results are shaky.")

    # --- 2. Check the weight limits can work at all ---------------------------
    low, high = min_weight_pct / 100, max_weight_pct / 100
    if n * high < 1 - 1e-9:
        raise ValueError(
            f"With {n} stocks and at most {max_weight_pct:g}% in each, the weights can't add up to 100%. "
            f"Raise the limit to at least {100 / n:.0f}%."
        )
    if n * low > 1 + 1e-9:
        raise ValueError(
            f"With {n} stocks and at least {min_weight_pct:g}% in each, the weights add up to more than 100%. "
            f"Lower the minimum to at most {100 / n:.0f}%."
        )

    risk_free = data.get_us_3m_yield() / 100
    max_drop = -max_drawdown_pct / 100
    min_return = min_return_pct / 100
    r = returns.values

    # --- 3. Thousands of random mixes, nudged to fit the weight limits --------
    # A "Dirichlet" draw gives random weights that already add up to 1.
    rng = np.random.default_rng(SEED)
    mixes = _fit_limits(rng.dirichlet(np.ones(n), size=MIXES), low, high)
    # Add the corner mixes, which random draws almost never land on, and
    # the equal split (the same % in every stock).
    corners = _corner_mixes(r, low, high)
    equal = _fit_limits(np.full((1, n), 1 / n), low, high)
    mixes = np.vstack([mixes, corners, equal])
    stats = _replay(r, mixes, risk_free)

    # --- 4. Which mixes follow the rules? --------------------------------------
    drop_ok = stats["drop"] >= max_drop
    return_ok = stats["return"] >= min_return
    fits = drop_ok & return_ok

    # --- Your current mix, for comparison -------------------------------------
    current_w = None
    if current:
        raw = np.array([pf._finite_number(current.get(t, 0), f"Your current weight for {t}") for t in tickers])
        if raw.sum() > 0:
            current_w = raw / raw.sum()
    current_stats = _replay(r, current_w[None, :], risk_free) if current_w is not None else None

    rules = {"goal": GOALS[goal], "biggest drop allowed": f"-{max_drawdown_pct:g}%",
             "minimum yearly return": f"{min_return_pct:g}%", "most in one stock": f"{max_weight_pct:g}%",
             "least in one stock": f"{min_weight_pct:g}%"}
    # The same rules as plain numbers, so MyEdit can check an edit against them.
    limits = {"max_drawdown_pct": max_drawdown_pct, "min_return_pct": min_return_pct,
              "max_weight_pct": max_weight_pct, "min_weight_pct": min_weight_pct}
    period = {"start": returns.index[0].date(), "end": returns.index[-1].date(),
              "years": round(returns.shape[0] / TRADING_DAYS, 1)}

    cloud = pd.DataFrame({
        "yearly return %": stats["return"] * 100,
        "yearly swings %": stats["swings"] * 100,
        "Sharpe ratio": stats["sharpe"],
        "worst drop %": stats["drop"] * 100,
        "fits rules": fits,
    })

    # --- 5. The best mix that fits ---------------------------------------------
    found_by_search = False
    if fits.any():
        score = np.where(fits, _goal_value(stats, goal), -np.inf)
        best_w = mixes[int(np.argmax(score))]
    else:
        # None of the tried mixes fits. Before saying so, look harder,
        # starting from the mixes that came closest, the equal split and
        # the corners.
        shortfall = np.maximum(min_return - stats["return"], 0) + np.maximum(max_drop - stats["drop"], 0)
        closest = mixes[np.argsort(shortfall)[:SEARCH_STARTS]]
        starts = list(closest) + list(equal) + list(corners)
        best_w = _search_for_a_fit(r, starts, low, high, min_return, max_drop, risk_free)
        found_by_search = best_w is not None

    # --- Nothing found: say which rule is the hardest ----------------------------
    if best_w is None:
        tried = (f"(It tried {len(mixes):,} mixes and a closer search. That doesn't prove no mix exists, "
                 f"but finding one is unlikely.)")
        if not drop_ok.any() and not return_ok.any():
            message = (f"No mix was found that keeps the worst drop within -{max_drawdown_pct:g}% OR returns "
                       f"{min_return_pct:g}% a year. Try allowing a bigger drop and a lower minimum return. {tried}")
        elif drop_ok.sum() < return_ok.sum():
            best_drop = stats["drop"][return_ok].max() * 100
            message = (f"No mix was found that returns at least {min_return_pct:g}% a year while keeping the worst "
                       f"drop within -{max_drawdown_pct:g}%. The drop rule is the hardest: the smallest drop among "
                       f"mixes that hit your return was {best_drop:.0f}%. Try allowing a bigger drop or a lower "
                       f"minimum return. {tried}")
        else:
            best_return = stats["return"][drop_ok].max() * 100
            message = (f"No mix was found that returns at least {min_return_pct:g}% a year while keeping the worst "
                       f"drop within -{max_drawdown_pct:g}%. The return rule is the hardest: the best return among "
                       f"mixes within your drop limit was {best_return:.1f}%. Try a lower minimum return or allowing "
                       f"a bigger drop. {tried}")
        return _package("no mix found", message, tickers, goal, rules, limits, period, risk_free, returns,
                        None, None, current_w, current_stats, cloud)

    # --- 6. Fine-tune the best mix ----------------------------------------------
    def replay_one(w):
        return _replay(r, np.asarray(w)[None, :], risk_free)

    best_score = _goal_value(replay_one(best_w), goal)[0]

    def objective(w):
        return -_goal_value(replay_one(w), goal)[0]

    solver = minimize(
        objective, best_w, method="SLSQP",
        bounds=[(low, high)] * n,
        constraints=[
            {"type": "eq", "fun": lambda w: w.sum() - 1},
            {"type": "ineq", "fun": lambda w: replay_one(w)["return"][0] - min_return},
            {"type": "ineq", "fun": lambda w: replay_one(w)["drop"][0] - max_drop},
        ],
        options={"maxiter": 200},
    )
    # Keep the solver's answer only if it truly follows every rule and is better.
    tuned = _fit_limits(np.asarray(solver.x)[None, :], low, high)[0]
    tuned_stats = replay_one(tuned)
    tuned_fits = tuned_stats["drop"][0] >= max_drop - 1e-9 and tuned_stats["return"][0] >= min_return - 1e-9
    if solver.success and tuned_fits and _goal_value(tuned_stats, goal)[0] > best_score:
        best_w, best_stats = tuned, tuned_stats
    else:
        best_stats = replay_one(best_w)

    if found_by_search:
        message = (f"None of the {len(mixes):,} mixes tried at first followed your rules, but a closer search "
                   f"found one. The best one for the {GOALS[goal]} is shown.")
    else:
        message = (f"Out of {len(mixes):,} mixes, {int(fits.sum()):,} follow your rules. "
                   f"The best one for the {GOALS[goal]} is shown.")
    return _package("ok", message, tickers, goal, rules, limits, period, risk_free, returns,
                    best_w, best_stats, current_w, current_stats, cloud)


def _package(status, message, tickers, goal, rules, limits, period, risk_free, returns,
             best_w, best_stats, current_w, current_stats, cloud) -> dict:
    """Build the tables every caller gets back, for both "ok" and "no mix found"."""
    growth, comparison = {}, {}
    if current_w is not None:
        growth[CURRENT] = START_MONEY * np.cumprod(1 + returns.values @ current_w)
        comparison[CURRENT] = _summary_row(current_stats, 0, growth[CURRENT][-1])
    if best_w is not None:
        growth[BEST] = START_MONEY * np.cumprod(1 + returns.values @ best_w)
        comparison[BEST] = _summary_row(best_stats, 0, growth[BEST][-1])

    weights = pd.DataFrame(index=pd.Index(tickers, name="ticker"))
    weights["current %"] = current_w * 100 if current_w is not None else np.nan
    weights["best %"] = best_w * 100 if best_w is not None else np.nan
    weights["change (points)"] = weights["best %"] - weights["current %"]

    return {
        "status": status,
        "message": message,
        "tickers": tickers,
        "goal": goal,
        "rules": rules,
        "period": period,
        "risk_free_pct": risk_free * 100,
        # One row per mix. Fixed columns, so MyEdit can add a row even when
        # there's no current mix and no mix fit the rules.
        "comparison": pd.DataFrame(list(comparison.values()), index=list(comparison.keys()), columns=SUMMARY_COLUMNS),
        "weights": weights.round(1),
        "growth": pd.DataFrame(growth, index=returns.index),
        "cloud": cloud,
        # float(...) makes plain numbers, so they print as 17.7, not np.float64(17.7).
        "best_weights": {t: float(round(w * 100, 1)) for t, w in zip(tickers, best_w)} if best_w is not None else {},
        "current_weights": {t: float(round(w * 100, 1)) for t, w in zip(tickers, current_w)} if current_w is not None else {},
        # Kept so MyEdit can replay an edited mix over exactly the same days.
        "daily_returns": returns,
        "risk_free": risk_free,
        "limits": limits,
    }


def optimize_portfolio(portfolio: dict, add: list = None, **rules) -> dict:
    """Optimize starting from what you own.

    portfolio  a portfolio from portfolio.py (or st.session_state.portfolio)
    add        optional extra tickers to consider, like ["MSFT", "TD.TO"].
               They start at 0% in your current mix.
    rules      any of optimize()'s rules, like max_weight_pct=40

    Your current mix uses each stock's slice of your pie from MyStocks
    (converted with today's exchange rate, like the pie chart).
    """
    positions = ms.positions_table(portfolio)
    tickers = list(positions["ticker"])
    # A stock with no current price (a typo, or Yahoo missing it today) has a
    # blank weight, so it starts at 0% instead.
    current = {t: w for t, w in zip(positions["ticker"], positions["weight_pct"]) if pd.notna(w)}

    # Nothing owned and nothing extra to try: explain what to do instead.
    if not tickers and not add:
        raise ValueError(
            "Your portfolio is empty, so there's nothing to optimize yet. Add some stocks first, "
            "or list at least 2 stocks you'd like to try (the 'add' list), like AAPL and KO."
        )

    # Start with what you own, then add any extra tickers you don't own yet.
    if add:
        tickers += [t for t in data.clean_tickers(add) if t not in tickers]
    return optimize(tickers, current=current, **rules)


# ===========================================================================
# MYEDIT: TWEAK THE BEST MIX BY HAND
# ===========================================================================

def my_edit(result: dict, changes: dict) -> dict:
    """MyEdit: your own hand-tweaked version of the best mix.

    result   what optimize(), optimize_portfolio() or an earlier my_edit() gave back
    changes  the stocks you want to set, as {ticker: % of your money},
             like {"KO": 20, "SHOP.TO": 15}

    HOW THE OTHER STOCKS ARE HANDLED
        Only the stocks you name are set exactly. The rest share whatever
        is left over in the same proportions they had before, so the total
        stays 100%. Name every stock to set them all yourself (they must
        then add up to 100%).

    WHERE IT STARTS FROM
        Your last edit if you're editing an edit, otherwise the best mix.
        If no mix fit your rules, it starts from your current mix (or an
        equal split), so you can still build one by hand.

    Returns the same dictionary as optimize(), plus:
        "edit_weights"  your edited mix, as {ticker: %}
        "breaks"        a list of your rules the edit breaks (empty if none)
    and "comparison", "weights" and "growth" gain a "Your edit" row or column.
    The charts show your edit automatically.
    """
    tickers = result["tickers"]
    start = (result.get("edit_weights") or result["best_weights"] or result["current_weights"]
             or {t: 100 / len(tickers) for t in tickers})

    # --- Check the changes make sense ----------------------------------------
    # Tidy each ticker and turn each weight into a real number. If someone
    # typed "twenty" instead of 20, or the box was blank (NaN), say so.
    tidy = {}
    for t, v in changes.items():
        t = data.clean_tickers(t)[0]
        try:
            tidy[t] = pf._finite_number(v, "Weight")
        except ValueError:
            # "from None" hides the first message and shows only this clearer one.
            raise ValueError(f'Weights must be numbers, like 20 for 20%. {t} has "{v}".') from None
    changes = tidy
    unknown = [t for t in changes if t not in tickers]
    if unknown:
        raise ValueError(f"{unknown} weren't part of this optimization. Add them to the stock list and optimize again.")
    if any(v < 0 for v in changes.values()):
        raise ValueError("A weight can't be below 0%.")
    set_total = sum(changes.values())
    if set_total > 100 + 1e-6:
        raise ValueError(f"The weights you set add up to {set_total:g}%, which is more than 100%.")

    # --- Share what's left among the stocks you didn't name -------------------
    others = [t for t in tickers if t not in changes]
    if not others:
        if abs(set_total - 100) > 0.5:
            raise ValueError(f"You set every stock, but they add up to {set_total:g}%, not 100%.")
        # Close enough (like 99.6% from rounding): scale them so they add up
        # to exactly 100%, keeping the same proportions.
        weights = {t: v / set_total * 100 for t, v in changes.items()}
    else:
        left = 100 - set_total
        before = sum(start.get(t, 0) for t in others)
        weights = dict(changes)
        for t in others:
            # Same proportions as before. If they were all 0%, split evenly.
            weights[t] = start.get(t, 0) / before * left if before > 0 else left / len(others)

    w = np.array([weights[t] for t in tickers]) / 100

    # --- Replay the edited mix over the same days ------------------------------
    returns = result["daily_returns"]
    stats = _replay(returns.values, w[None, :], result["risk_free"])
    # Never call a mix fine if its numbers came out blank: every rule check
    # below would quietly pass.
    if not all(np.isfinite(stats[k][0]) for k in ("return", "swings", "drop")):
        raise ValueError("Your edited mix couldn't be measured, so it can't be checked against your rules.")
    growth = result["growth"].copy()
    growth[EDIT] = START_MONEY * np.cumprod(1 + returns.values @ w)

    comparison = result["comparison"].copy()
    comparison.loc[EDIT] = _summary_row(stats, 0, growth[EDIT].iloc[-1])

    table = result["weights"].copy()
    table["edit %"] = (w * 100).round(1)
    table["edit vs best (points)"] = (table["edit %"] - table["best %"]).round(1)

    # --- Which of your rules does the edit break? ------------------------------
    limits = result["limits"]
    breaks = []
    if stats["drop"][0] * 100 < -limits["max_drawdown_pct"]:
        breaks.append(f"Its worst drop ({stats['drop'][0] * 100:.1f}%) is bigger than your limit of -{limits['max_drawdown_pct']:g}%.")
    if stats["return"][0] * 100 < limits["min_return_pct"]:
        breaks.append(f"Its yearly return ({stats['return'][0] * 100:.1f}%) is below your minimum of {limits['min_return_pct']:g}%.")
    too_big = [t for t in tickers if weights[t] > limits["max_weight_pct"] + 0.05]
    if too_big:
        breaks.append(f"{', '.join(too_big)} {'is' if len(too_big) == 1 else 'are'} above your limit of {limits['max_weight_pct']:g}% in one stock.")
    too_small = [t for t in tickers if weights[t] < limits["min_weight_pct"] - 0.05]
    if too_small:
        breaks.append(f"{', '.join(too_small)} {'is' if len(too_small) == 1 else 'are'} below your minimum of {limits['min_weight_pct']:g}% in one stock.")

    sharpe_change = stats["sharpe"][0] - comparison.loc[BEST, "Sharpe ratio"] if BEST in comparison.index else np.nan
    message = "Your edit follows all your rules." if not breaks else f"Your edit breaks {len(breaks)} of your rules."
    if pd.notna(sharpe_change):
        message += f" Its Sharpe ratio is {sharpe_change:+.2f} vs the best mix."

    return {
        **result,
        "message": message,
        "comparison": comparison,
        "weights": table,
        "growth": growth,
        "edit_weights": {t: float(round(weights[t], 1)) for t in tickers},
        "breaks": breaks,
    }


# ===========================================================================
# CHARTS
# ===========================================================================

def cloud_chart(result: dict, max_points: int = 4_000):
    """Every mix tried, placed by yearly swings (across) and yearly return (up).

    Coloured dots follow your rules (brighter = better Sharpe ratio), grey
    dots break them. The star is your current mix, the red diamond the best
    mix, and the orange circle your MyEdit version (if you made one).
    Up and to the left is good: more return for less bumpiness.
    """
    cloud = result["cloud"].sample(n=min(max_points, len(result["cloud"])), random_state=SEED)
    fits, breaks = cloud[cloud["fits rules"]], cloud[~cloud["fits rules"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=breaks["yearly swings %"], y=breaks["yearly return %"], mode="markers",
        marker={"size": 4, "color": "lightgrey"}, name="breaks your rules",
        hovertemplate="swings %{x:.1f}%<br>return %{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=fits["yearly swings %"], y=fits["yearly return %"], mode="markers",
        marker={"size": 5, "color": fits["Sharpe ratio"], "colorscale": "Viridis",
                "colorbar": {"title": "Sharpe"}, "showscale": True},
        name="follows your rules",
        hovertemplate="swings %{x:.1f}%<br>return %{y:.1f}%<extra></extra>",
    ))
    for label, symbol in [(CURRENT, "star"), (BEST, "diamond"), (EDIT, "circle")]:
        colour = MIX_COLOURS[label]
        if label in result["comparison"].index:
            row = result["comparison"].loc[label]
            fig.add_trace(go.Scatter(
                x=[row["yearly swings %"]], y=[row["yearly return %"]], mode="markers",
                marker={"size": 16, "symbol": symbol, "color": colour, "line": {"width": 1, "color": "white"}},
                name=label,
            ))
    fig.update_layout(
        title="Every mix tried: return vs bumpiness",
        xaxis_title="Yearly swings (%)", yaxis_title="Yearly return (%)",
        height=500, legend={"orientation": "h", "y": -0.18},
    )
    return fig


def growth_chart(result: dict):
    """How $10,000 would have grown in each mix: current, best, and your edit if you made one."""
    fig = px.line(
        result["growth"],
        color_discrete_map=MIX_COLOURS,
        title=f"${START_MONEY:,} invested on {result['period']['start']}",
        labels={"value": "Value ($)", "variable": "", "date": ""},
    )
    return fig


def weights_chart(result: dict):
    """Each mix's weights side by side, one group of bars per stock.

    Shows whichever mixes exist: current, best, and your MyEdit version.
    """
    # Keep the weight columns that exist and aren't blank (no current mix = blank).
    columns = [c for c in WEIGHT_COLUMNS if c in result["weights"] and result["weights"][c].notna().any()]
    table = result["weights"][columns].reset_index()
    table = table.melt(id_vars="ticker", var_name="mix", value_name="weight %")
    table["mix"] = table["mix"].map(WEIGHT_COLUMNS)
    fig = px.bar(
        table, x="ticker", y="weight %", color="mix", barmode="group",
        color_discrete_map=MIX_COLOURS,
        title="How much money goes in each stock", labels={"ticker": "", "mix": ""},
    )
    return fig
