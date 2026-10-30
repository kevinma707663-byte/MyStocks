"""
Checks for the October 29 code review. Each test is one of the reviewer's
reproductions, turned into a check that must keep passing.

All of them run OFFLINE with made-up prices, except the one labelled "live".
"""
import json
import math
import warnings
from datetime import date

import numpy as np
import pandas as pd
import pytest

from core import coach
from core import data
from core import dcf
from core import my_optimizer as mo
from core import my_risks as mr
from core import my_stocks as ms
from core import portfolio as pf


class FakeInfo(dict):
    """Company facts where anything we didn't fill in is blank (None)."""
    def __missing__(self, key):
        return None


@pytest.fixture
def offline(monkeypatch):
    """Swap the internet functions for fake ones, for one test."""
    monkeypatch.setattr(data, "get_info", lambda t: FakeInfo(name=t, sector="Technology", currency="USD"))
    monkeypatch.setattr(data, "get_fx_rate", lambda a, b: 1.0)
    monkeypatch.setattr(data, "get_us_3m_yield", lambda: 4.0)
    return monkeypatch


# ===========================================================================
# 1. The order trades are typed in must not change the accounting
# ===========================================================================

def _gains_and_cost(p):
    gains = sum(t["realized_gain"] for t in p["trades"] if t["action"] == "sell")
    cost = sum(h["shares"] * h["buy_price"] for h in p["holdings"])
    return round(gains, 2), round(cost, 2)


def _enter(steps, order):
    p = pf.empty_portfolio()
    for name in order:
        steps[name](p)
    return p


AAA_TRADES = {
    "buy jan": lambda p: pf.add_holding(p, "AAA", 10, 100, "2025-01-10"),
    "sell feb": lambda p: pf.sell_holding(p, "AAA", 5, 150, "2025-02-10"),
    "buy mar": lambda p: pf.add_holding(p, "AAA", 10, 200, "2025-03-10"),
    "sell apr": lambda p: pf.sell_holding(p, "AAA", 10, 300, "2025-04-10"),
}


def test_a_backdated_sale_typed_last_gives_the_same_answer_as_in_date_order():
    in_order = _enter(AAA_TRADES, ["buy jan", "sell feb", "buy mar", "sell apr"])
    typed_late = _enter(AAA_TRADES, ["buy jan", "buy mar", "sell apr", "sell feb"])
    assert _gains_and_cost(in_order) == _gains_and_cost(typed_late) == (1583.33, 833.33)


def test_a_backdated_buy_typed_last_gives_the_same_answer_as_in_date_order():
    steps = {
        "buy jan": lambda p: pf.add_holding(p, "AAA", 10, 100, "2025-01-10"),
        "buy feb": lambda p: pf.add_holding(p, "AAA", 10, 200, "2025-02-10"),
        "sell apr": lambda p: pf.sell_holding(p, "AAA", 10, 300, "2025-04-10"),
    }
    in_order = _enter(steps, ["buy jan", "buy feb", "sell apr"])
    typed_late = _enter(steps, ["buy jan", "sell apr", "buy feb"])
    assert _gains_and_cost(in_order) == _gains_and_cost(typed_late) == (1500.0, 1500.0)


def test_removing_a_purchase_a_later_sale_needed_is_refused_and_changes_nothing():
    p = pf.empty_portfolio()
    pf.add_holding(p, "AAA", 10, 100, "2025-01-10")
    pf.add_holding(p, "AAA", 10, 200, "2025-03-10")
    pf.sell_holding(p, "AAA", 15, 300, "2025-04-10")
    before = json.dumps(p, sort_keys=True)
    with pytest.raises(ValueError, match="only owned 10 shares"):
        pf.remove_holding(p, 0)                       # the January purchase
    assert json.dumps(p, sort_keys=True) == before


def test_removing_a_mistaken_sale_puts_the_shares_back():
    p = pf.empty_portfolio()
    pf.add_holding(p, "AAA", 10, 100, "2025-01-10")
    pf.sell_holding(p, "AAA", 4, 150, "2025-02-10")
    pf.remove_trade(p, 1)                             # row 1 of the diary: the sale
    assert sum(h["shares"] for h in p["holdings"]) == pytest.approx(10)
    assert [t["action"] for t in p["trades"]] == ["buy"]


# ===========================================================================
# 2. Cost, value and the S&P 500 twin must use the same stocks
# ===========================================================================

def test_the_twin_uses_the_same_stocks_as_the_cost_and_value(offline):
    days = pd.bdate_range(end=date.today(), periods=300)

    def get_prices(tickers, period="1y", start=None, adjusted=True):
        tickers = data.clean_tickers(tickers)
        # BBB has history, but its latest quote is missing (a partial outage).
        known = {"AAA": 100.0, "SPY": 500.0} if period == "5d" and start is None else {"AAA": 100.0, "BBB": 50.0, "SPY": 500.0}
        found = {t: [known[t]] * len(days) for t in tickers if t in known}
        if not found:
            raise ValueError(f"No prices found for {tickers}. Check the tickers.")
        return pd.DataFrame(found, index=days)

    offline.setattr(data, "get_prices", get_prices)
    p = pf.empty_portfolio()
    pf.add_holding(p, "AAA", 10, 80, days[50].date().isoformat())     # cost 800, worth 1,000
    pf.add_holding(p, "BBB", 20, 50, days[50].date().isoformat())     # cost 1,000, no latest quote
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        group = ms.portfolio_summary(p)["groups"]["USD"]
    assert group["gain_pct"] == pytest.approx(25)
    assert group["sp500_twin_gain_pct"] == pytest.approx(0)            # SPY never moved
    assert group["beat_sp500_by_pct"] == pytest.approx(25)
    assert group["left_out"] == ["BBB"]


# ===========================================================================
# 3. Blank (NaN) numbers are turned away everywhere a weight or rule goes in
# ===========================================================================

def _returns(columns, n_days=300):
    rng = np.random.default_rng(3)
    days = pd.bdate_range(end=date.today(), periods=n_days)
    return pd.DataFrame({t: rng.normal(0.001, 0.01, n_days) for t in columns}, index=days)


@pytest.fixture
def three_stocks(offline):
    returns = _returns(["AAA", "BBB", "CCC", "SPY"])
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: returns[data.clean_tickers(tickers)])
    return returns


def test_myedit_turns_away_a_blank_weight(three_stocks):
    result = mo.optimize(["AAA", "BBB", "CCC"], min_return_pct=-100, max_drawdown_pct=100, max_weight_pct=60)
    with pytest.raises(ValueError, match="Weights must be numbers"):
        mo.my_edit(result, {"AAA": float("nan")})


@pytest.mark.parametrize("rules", [{"max_weight_pct": float("nan")}, {"min_return_pct": float("inf")},
                                   {"max_drawdown_pct": "lots"}, {"current": {"AAA": float("nan")}}])
def test_optimizer_rules_must_be_real_numbers(three_stocks, rules):
    with pytest.raises(ValueError, match="must be a number"):
        mo.optimize(["AAA", "BBB", "CCC"], **{"max_weight_pct": 60, **rules})


def test_mix_risks_turns_away_a_blank_weight(three_stocks):
    with pytest.raises(ValueError, match="Weights must be numbers"):
        mr.mix_risks({"AAA": float("nan"), "BBB": 50})


# ===========================================================================
# 4. "No mix fits" must not be said when a mix does fit
# ===========================================================================

def _see_saw(n_days=252, extra=0):
    """Two stocks that take turns going +10% and -9%. Half in each gains 0.5% every day."""
    days = pd.bdate_range(end=date.today(), periods=n_days)
    up_down = np.where(np.arange(n_days) % 2 == 0, 0.10, -0.09)
    columns = {"AAA": up_down, "BBB": -up_down + 0.01}
    for i in range(extra):
        columns[f"FLAT{i}"] = np.zeros(n_days)
    return pd.DataFrame(columns, index=days)


def test_an_interior_mix_is_found_when_corners_miss_it(offline):
    returns = _see_saw()
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: returns[data.clean_tickers(tickers)])
    best_possible = (1.005 ** 252 - 1) * 100                          # 251.4% with half in each
    result = mo.optimize(["AAA", "BBB"], goal="high_return", min_return_pct=best_possible - 1e-9,
                         max_drawdown_pct=100, max_weight_pct=100)
    assert result["status"] == "ok"


def test_a_closer_search_runs_when_no_tried_mix_fits(offline):
    # With a flat third stock, the only mixes that fit are close to 50/50/0:
    # not a corner, not the equal 33/33/33 split, and too narrow for random draws.
    returns = _see_saw(extra=1)
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: returns[data.clean_tickers(tickers)])
    best_possible = (1.005 ** 252 - 1) * 100
    result = mo.optimize(["AAA", "BBB", "FLAT0"], goal="high_return", min_return_pct=best_possible - 0.05,
                         max_drawdown_pct=100, max_weight_pct=100)
    assert result["status"] == "ok"
    assert result["best_weights"]["FLAT0"] < 5


def test_when_nothing_is_found_it_says_found_not_proven(three_stocks):
    result = mo.optimize(["AAA", "BBB", "CCC"], min_return_pct=500, max_weight_pct=60)
    assert result["status"] == "no mix found"
    assert "doesn't prove" in result["message"]


# ===========================================================================
# 5. DCF: interest under financing still has its tax saving taken out
# ===========================================================================

def test_both_ways_of_reporting_interest_give_the_same_cash_flow():
    # The reviewer's example: 10 of interest, a 20% tax rate.
    taxes = {"tax": 20.0, "pretax": 100.0, "interest": 10.0}
    operating = dcf._unlevered_cash({**taxes, "free_cash_flow": 90.0, "interest_paid_in_financing": float("nan")})
    financing = dcf._unlevered_cash({**taxes, "free_cash_flow": 100.0, "interest_paid_in_financing": -10.0})
    assert operating[0] == pytest.approx(98)
    assert financing[0] == pytest.approx(98)


def test_a_company_that_paid_no_tax_had_no_tax_saving():
    loss = {"tax": 0.0, "pretax": -50.0, "interest": 10.0}
    operating = dcf._unlevered_cash({**loss, "free_cash_flow": 90.0, "interest_paid_in_financing": float("nan")})
    financing = dcf._unlevered_cash({**loss, "free_cash_flow": 100.0, "interest_paid_in_financing": -10.0})
    assert operating[0] == financing[0] == pytest.approx(100)


# ===========================================================================
# 6. The coach's checks enforce its rules, not just its prompt
# ===========================================================================

class FakeClient:
    def __init__(self, note):
        self.note = note
        self.messages = self

    @property
    def beta(self):
        return self

    def create(self, **request):
        from types import SimpleNamespace
        return SimpleNamespace(stop_reason="end_turn", content=[
            SimpleNamespace(type="text", text=json.dumps({"note": self.note, "biases": []}))])


def _coach(note, offline):
    return coach.coach_note(pf.empty_portfolio(), "buy", "NVDA", 10, 200, found=[], client=FakeClient(note))


@pytest.mark.parametrize("note", [
    "Buy now. This stock will rise 200%.",
    "You should sell before it drops.",
    "I recommend holding on. It's going to climb.",
])
def test_advice_and_predictions_are_thrown_away(offline, note):
    assert _coach(note, offline)["status"] == "unavailable"


def test_a_note_over_the_word_limit_is_thrown_away(offline):
    long_note = " ".join(["Take a breath before you trade."] * 30)          # 180 words
    assert _coach(long_note, offline)["status"] == "unavailable"


def test_a_percent_must_match_a_percent_in_the_facts(offline):
    # 200 is the price, so "$200" is fine, but "200%" is not a fact.
    assert _coach("At $200 a share, why today?", offline)["status"] == "ok"
    assert _coach("It's up 200% this year. Why today?", offline)["status"] == "unavailable"


# ===========================================================================
# 7. Too little shared history gives a clear message, not a crash
# ===========================================================================

def test_no_shared_history_gives_a_plain_message(offline):
    empty = pd.DataFrame({"AAA": [], "BBB": [], "SPY": []}, dtype=float)
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: empty[data.clean_tickers(tickers)])
    with pytest.raises(ValueError, match="share"):
        mo.optimize(["AAA", "BBB"], max_weight_pct=100)
    with pytest.raises(ValueError, match="share"):
        mr.mix_risks({"AAA": 50, "BBB": 50})


# ===========================================================================
# Live: the DCF adjusts interest the right way for real companies
# ===========================================================================

@pytest.mark.live
def test_dcf_interest_adjustment_on_real_companies():
    # Coca-Cola counts interest paid in operating cash: interest after tax is added back.
    assert dcf.dcf_valuation("KO")["inputs"]["interest_adjustment"] > 0
    # Loblaw reports interest paid under financing: only its tax saving comes out.
    assert dcf.dcf_valuation("L.TO")["inputs"]["interest_adjustment"] < 0
