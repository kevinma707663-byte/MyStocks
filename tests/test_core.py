"""
Automatic checks for MyPortfolio's core code.

Run them all from the project folder with:

    python -m pytest tests

Most checks run OFFLINE. They swap the internet functions in core/data.py
for fake ones with made-up prices, so they're fast and give the same
answer every time. Checks labelled "live" use real Yahoo data. Skip those
with:  python -m pytest tests -m "not live"

Each test is a small story: set something up, do one thing, check the
result with "assert" (which means "this must be true, or the test fails").
"""
import math
import warnings
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from core import data
from core import dcf
from core import my_optimizer as mo
from core import my_risks as mr
from core import my_stocks as ms
from core import portfolio as pf
from core import warnings_sidebar as ws


# ===========================================================================
# FAKE MARKET DATA (so the offline tests never touch the internet)
# ===========================================================================

class FakeInfo(dict):
    """Company facts where anything we didn't fill in is blank (None)."""
    def __missing__(self, key):
        return None


def fake_info(ticker):
    return FakeInfo(name=ticker, sector="Technology", currency="USD")


def fake_daily_returns(tickers, n_days=756, seed=1):
    """Made-up daily returns: stock 1 grows fastest, the last one slowest."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(end=date.today(), periods=n_days)
    columns = {}
    for i, t in enumerate(tickers):
        columns[t] = rng.normal(0.0012 - 0.0004 * i, 0.01, n_days)
    return pd.DataFrame(columns, index=days)


@pytest.fixture
def offline(monkeypatch):
    """Swap the internet functions for fake ones, for one test."""
    monkeypatch.setattr(data, "get_info", fake_info)
    monkeypatch.setattr(data, "get_fx_rate", lambda a, b: 1.0)
    monkeypatch.setattr(data, "get_us_3m_yield", lambda: 4.0)
    return monkeypatch


def days_ago(n):
    return (date.today() - timedelta(days=n)).isoformat()


# ===========================================================================
# portfolio.py
# ===========================================================================

@pytest.mark.parametrize("bad", [float("nan"), "nan", float("inf"), "ten", None, 0, -5])
def test_shares_must_be_a_real_positive_number(bad):
    with pytest.raises(ValueError, match="Shares must"):
        pf.add_holding(pf.empty_portfolio(), "AAPL", bad, 100, "2024-01-15")


def test_backdated_sale_cant_use_shares_bought_later():
    # 10 shares by February, 10 more in March. A February sale of 15 must fail.
    p = pf.empty_portfolio()
    pf.add_holding(p, "AAPL", 10, 100, "2025-01-10")
    pf.add_holding(p, "AAPL", 10, 200, "2025-03-10")
    with pytest.raises(ValueError, match="only owned 10 shares"):
        pf.sell_holding(p, "AAPL", 15, 150, "2025-02-10")


def test_backdated_sale_uses_only_earlier_purchases():
    # A February sale of 5 uses January's $100 cost, not the March $200 buy.
    p = pf.empty_portfolio()
    pf.add_holding(p, "AAPL", 10, 100, "2025-01-10")
    pf.add_holding(p, "AAPL", 10, 200, "2025-03-10")
    pf.sell_holding(p, "AAPL", 5, 150, "2025-02-10")
    assert p["trades"][-1]["realized_gain"] == pytest.approx((150 - 100) * 5)
    shares = {h["buy_date"]: h["shares"] for h in p["holdings"]}
    assert shares == {"2025-01-10": pytest.approx(5), "2025-03-10": pytest.approx(10)}


def test_selling_today_works_as_before():
    p = pf.empty_portfolio()
    pf.add_holding(p, "AAPL", 10, 100, "2025-01-10")
    pf.add_holding(p, "AAPL", 10, 200, "2025-03-10")
    pf.sell_holding(p, "AAPL", 10, 300)
    # Average cost $150, so selling 10 at $300 locks in $1,500.
    assert p["trades"][-1]["realized_gain"] == pytest.approx(1500)
    assert sum(h["shares"] for h in p["holdings"]) == pytest.approx(10)


def test_removing_a_typo_deletes_the_right_diary_line():
    # Two buys of the same stock, same day, same price, different shares.
    p = pf.empty_portfolio()
    pf.add_holding(p, "AAPL", 10, 100, "2025-01-10")
    pf.add_holding(p, "AAPL", 3, 100, "2025-01-10")
    pf.remove_holding(p, 1)                         # remove the 3-share typo
    assert [t["shares"] for t in p["trades"]] == [10]


def test_removing_still_works_for_files_saved_before_name_tags():
    p = {"holdings": [{"ticker": "AAPL", "shares": 10.0, "buy_price": 100.0, "buy_date": "2025-01-10"},
                      {"ticker": "AAPL", "shares": 3.0, "buy_price": 100.0, "buy_date": "2025-01-10"}],
         "trades": [{"date": "2025-01-10", "action": "buy", "ticker": "AAPL", "shares": 10.0, "price": 100.0},
                    {"date": "2025-01-10", "action": "buy", "ticker": "AAPL", "shares": 3.0, "price": 100.0}]}
    pf.remove_holding(p, 1)
    assert [t["shares"] for t in p["trades"]] == [10]


# ===========================================================================
# my_stocks.py
# ===========================================================================

def fake_prices_for(known):
    """A fake get_prices() that only knows the tickers in `known` ({ticker: price})."""
    def get_prices(tickers, period="1y", start=None, adjusted=True):
        tickers = data.clean_tickers(tickers)
        days = pd.bdate_range(end=date.today(), periods=300)
        found = {t: [known[t]] * len(days) for t in tickers if t in known}
        if not found:
            raise ValueError(f"No prices found for {tickers}. Check the tickers.")
        missing = [t for t in tickers if t not in found]
        if missing:
            warnings.warn(f"No price data for {missing}. They were left out.")
        return pd.DataFrame(found, index=days)
    return get_prices


def test_unpriced_stock_is_left_out_of_totals(offline):
    # AAA cost $800 and is worth $1,000. BAD is a typo with no price.
    offline.setattr(data, "get_prices", fake_prices_for({"AAA": 100.0, "SPY": 500.0}))
    p = pf.empty_portfolio()
    pf.add_holding(p, "AAA", 10, 80, days_ago(60))
    pf.add_holding(p, "BAD", 10, 100, days_ago(60))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        group = ms.portfolio_summary(p)["groups"]["USD"]
    assert group["value"] == pytest.approx(1000)
    assert group["cost"] == pytest.approx(800)            # not 1,800
    assert group["gain"] == pytest.approx(200)


def test_every_ticker_mistyped_gives_blanks_not_an_error(offline):
    offline.setattr(data, "get_prices", fake_prices_for({"SPY": 500.0}))
    p = pf.empty_portfolio()
    pf.add_holding(p, "ZZZZFAKE", 5, 50, days_ago(60))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        positions = ms.positions_table(p)
        found = ws.standing_warnings(p)
    assert positions["price"].isna().all()
    assert [w["trap"] for w in found] == ["Ticker not found"]


# ===========================================================================
# my_risks.py
# ===========================================================================

def test_unknown_measurement_is_na_not_low():
    assert mr._level(float("nan"), "average_correlation") == "n/a"


def test_one_stock_score_leaves_out_what_cant_be_measured(offline):
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: fake_daily_returns(tickers))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        report = mr.mix_risks({"AAA": 100})
    levels = report["areas"]["level"]
    assert levels["Moving together"] == "n/a"
    measured = levels[levels != "n/a"].map(mr.LEVEL_POINTS)
    assert report["score"] == pytest.approx(measured.mean())


def test_stocks_without_history_are_listed_as_left_out(offline):
    returns = fake_daily_returns(["AAA", "BBB", "SPY"])
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: returns[[t for t in tickers if t in returns]])
    with pytest.warns(UserWarning, match="BAD"):
        report = mr.mix_risks({"AAA": 40, "BBB": 40, "BAD": 20})
    assert report["left_out"] == ["BAD"]


@pytest.mark.parametrize("mix, message", [
    ({"KO": "forty", "AAPL": 60}, "Weights must be numbers"),
    ({"ZZZZFAKE": 100}, "None of these have price history"),
])
def test_mix_risks_friendly_messages(offline, mix, message):
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: fake_daily_returns(["AAPL", "SPY"])[["SPY"]])
    with pytest.raises(ValueError, match=message):
        mr.mix_risks(mix)


# ===========================================================================
# my_optimizer.py
# ===========================================================================

STOCKS = ["AAA", "BBB", "CCC", "DDD"]


@pytest.fixture
def fake_market(offline):
    returns = fake_daily_returns(STOCKS)
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: returns[data.clean_tickers(tickers)])
    return returns


def test_sharpe_is_the_standard_one(fake_market):
    result = mo.optimize(STOCKS, min_return_pct=-100, max_drawdown_pct=100, max_weight_pct=60)
    w = np.array([result["best_weights"][t] for t in STOCKS]) / 100
    daily = fake_market.values @ w
    expected = (daily.mean() * 252 - 0.04) / (daily.std(ddof=1) * math.sqrt(252))
    # best_weights are rounded to 0.1%, so allow a tiny difference.
    assert result["comparison"].loc[mo.BEST, "Sharpe ratio"] == pytest.approx(expected, abs=0.01)


def test_a_tough_return_rule_finds_the_corner_mix(offline):
    # 8 stocks, at most 20% each. The highest return possible is the
    # "corner" 20/20/20/20/20/0/0/0, with the best 5 stocks.
    stocks = [f"S{i}" for i in range(8)]
    rng = np.random.default_rng(1)
    days = pd.bdate_range(end=date.today(), periods=756)
    returns = pd.DataFrame({t: rng.normal(0.0012 - 0.0002 * i, 0.01, 756) for i, t in enumerate(stocks)}, index=days)
    offline.setattr(data, "get_daily_returns", lambda tickers, years=3: returns[data.clean_tickers(tickers)])
    best_five = np.argsort(-(1 + returns).prod().values)[:5]
    w = np.zeros(8)
    w[best_five] = 0.2
    best_possible = ((1 + returns.values @ w).prod() ** (252 / 756) - 1) * 100
    # Ask for half a point under that. Random mixes alone never get this close.
    result = mo.optimize(stocks, min_return_pct=best_possible - 0.5, max_drawdown_pct=100, max_weight_pct=20)
    assert result["status"] == "ok"


def test_myedit_with_every_stock_set_adds_up_to_100(fake_market):
    result = mo.optimize(STOCKS, min_return_pct=-100, max_drawdown_pct=100, max_weight_pct=60)
    edit = mo.my_edit(result, {"AAA": 40, "BBB": 30, "CCC": 20, "DDD": 9.6})     # 99.6% typed
    assert sum(edit["edit_weights"].values()) == pytest.approx(100, abs=0.15)


def test_myedit_weights_must_be_numbers(fake_market):
    result = mo.optimize(STOCKS, min_return_pct=-100, max_drawdown_pct=100, max_weight_pct=60)
    with pytest.raises(ValueError, match="Weights must be numbers"):
        mo.my_edit(result, {"AAA": "twenty"})


def test_empty_portfolio_optimizer_message():
    with pytest.raises(ValueError, match="portfolio is empty"):
        mo.optimize_portfolio(pf.empty_portfolio())


# ===========================================================================
# warnings_sidebar.py
# ===========================================================================

def test_a_data_outage_never_blocks_a_trade(offline):
    def yahoo_is_down(*args, **kwargs):
        raise ConnectionError("Yahoo is down")
    offline.setattr(data, "get_prices", yahoo_is_down)
    p = pf.empty_portfolio()
    p, found = ws.trade(p, "buy", "KO", 5, 90)
    assert len(p["holdings"]) == 1                      # recorded anyway
    assert [w["trap"] for w in found] == ["Couldn't check"]


def test_real_input_mistakes_still_stop_a_trade():
    with pytest.raises(ValueError, match="Shares must be a number"):
        ws.trade(pf.empty_portfolio(), "buy", "KO", "ten", 90)
    with pytest.raises(ValueError, match="don't own any"):
        ws.trade(pf.empty_portfolio(), "sell", "KO", 1, 90)


# ===========================================================================
# dcf.py
# ===========================================================================

@pytest.mark.parametrize("setting", ["growth_pct", "terminal_growth_pct", "discount_rate_pct", "equity_risk_premium_pct"])
def test_dcf_turns_away_blank_numbers(setting):
    with pytest.raises(ValueError, match="must be a number"):
        dcf.dcf_valuation("KO", **{setting: float("nan")})


@pytest.mark.live
def test_dcf_reports_the_rate_it_really_used():
    mine = dcf.dcf_valuation("KO", discount_rate_pct=12)
    assert mine["inputs"]["discount_rate_pct"] == 12
    auto = dcf.dcf_valuation("KO")
    assert auto["inputs"]["discount_rate_pct"] == max(auto["inputs"]["worked_out_rate_pct"], dcf.MIN_DISCOUNT_RATE_PCT)


@pytest.mark.live
def test_dcf_adds_back_interest_only_when_it_was_taken_off():
    # Coca-Cola counts interest paid in operating cash: add it back.
    assert dcf.dcf_valuation("KO")["inputs"]["interest_added"] > 0
    # Loblaw reports interest paid under financing: nothing to add.
    assert dcf.dcf_valuation("L.TO")["inputs"]["interest_added"] == 0


# ===========================================================================
# The Streamlit trade form from the notebook (Chunk 7's partner example)
# ===========================================================================

TRADE_FORM_APP = '''
import streamlit as st
from core import portfolio as pf
from core import warnings_sidebar as ws

ws.check_trade = lambda *args, **kwargs: []        # no market data needed for this test

if "portfolio" not in st.session_state:
    st.session_state.portfolio = pf.empty_portfolio()
portfolio = st.session_state.portfolio

with st.form("trade"):
    action = st.radio("Action", ["buy", "sell"], horizontal=True)
    ticker = st.text_input("Ticker")
    shares = st.number_input("Shares", min_value=0.0)
    price = st.number_input("Price", min_value=0.0)
    if st.form_submit_button("Check this trade"):
        try:
            found = ws.check_trade(portfolio, action, ticker, shares, price)
            st.session_state.pending_trade = {"action": action, "ticker": ticker, "shares": shares, "price": price}
            st.session_state.pending_warnings = found
        except ValueError as error:
            st.error(str(error))

pending = st.session_state.get("pending_trade")
if pending:
    found = st.session_state.pending_warnings
    for w in found:
        st.warning(f"**{w['trap']}**: {w['message']}\\n\\n{w['tip']}")
    if st.button("Record it anyway" if found else "Record it"):
        try:
            ws.trade(portfolio, **pending)
            st.success("Recorded.")
        except ValueError as error:
            st.error(str(error))
        del st.session_state["pending_trade"]
'''


def test_streamlit_check_then_record_really_records():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string(TRADE_FORM_APP).run()
    app.text_input[0].input("KO")
    app.number_input[0].set_value(5)
    app.number_input[1].set_value(90)
    app.button[0].click().run()                         # "Check this trade"
    record = [b for b in app.button if b.label.startswith("Record")]
    assert record, "the Record button should appear after checking"
    record[0].click().run()                             # "Record it"
    assert len(app.session_state.portfolio["holdings"]) == 1
    assert app.success[0].value == "Recorded."
