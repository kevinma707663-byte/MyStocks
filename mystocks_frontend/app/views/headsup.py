"""Heads-up: standing warnings about what you own + a trade checker."""
import copy

import streamlit as st

from app import services as sv, theme
from app.views.common import filter_dates, safe
from core import portfolio as pf, warnings_sidebar as ws


def _cards(found):
    if not found:
        theme.card("✅ No traps spotted.")
    for w in found:
        c = theme.LEVEL_COLOR.get(w["level"], theme.MUTED)
        theme.card(f'<div class="row"><b>{w["trap"]}</b>{theme.chip(w["level"], c)}</div>'
                   f'<div style="margin:6px 0">{w["message"]}</div><div class="muted">{w["tip"]}</div>')


def render():
    p = st.session_state.portfolio
    st.markdown("#### Heads-up on what you own")
    found = safe(sv.standing, p, spinner="Checking for common traps…")
    if found is not None:
        _cards(filter_dates(found))
        if not st.session_state.dates_known:
            st.caption("Warnings that need purchase dates are hidden because imported files don't include them.")

    st.markdown("#### Check a trade first")
    with st.form("trade"):
        c1, c2 = st.columns(2)
        action = c1.selectbox("Action", ["buy", "sell"])
        ticker = c2.text_input("Ticker", placeholder="AAPL")
        c3, c4 = st.columns(2)
        shares = c3.number_input("Shares", min_value=0.0, step=1.0, format="%g")
        price = c4.number_input("Price", min_value=0.0, step=0.01, format="%.2f")
        check = st.form_submit_button("Check it", width="stretch")
        record = st.form_submit_button("Check and record", type="primary", width="stretch")
    if check or record:
        try:
            if record:
                newp = copy.deepcopy(p)
                newp, found = ws.trade(newp, action, ticker, shares, price)
                st.session_state.portfolio = newp
                st.session_state.verdicts = {}
                st.session_state.dates_known = False if not st.session_state.dates_known else st.session_state.dates_known
                st.success("Recorded.")
            else:
                found = safe(sv.check_trade, p, action, ticker, shares, price) or []
            _cards(filter_dates(found))
        except ValueError as e:
            st.error(str(e))
    with st.expander("Trade diary"):
        st.dataframe(pf.trades_table(p), width="stretch")
    theme.disclaimer()
