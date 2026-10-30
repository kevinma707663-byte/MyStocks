"""First screen: add holdings by CSV, by hand, or load the sample."""
import copy
from pathlib import Path

import streamlit as st

from core import portfolio as pf
from app import state, theme

SAMPLE = Path(__file__).resolve().parents[2] / "sample" / "OpenPosition_10_24_2026.csv"


def render():
    st.markdown("## Know what you own.")
    st.caption("Bring in your investments and see how they're doing, where the risks are, and how they could be better balanced.")

    st.markdown("#### Import from your broker")
    up = st.file_uploader("Broker positions file (.csv)", type="csv", label_visibility="collapsed")
    if up is not None:
        try:
            p, problems = state.parse_broker_csv(up)
        except ValueError as e:
            st.error(str(e))
        else:
            for pr in problems:
                st.warning(pr)
            st.success(f"Read {len(p['holdings'])} holdings.")
            st.info("Broker files don't include purchase dates, so history-based features and a few trade warnings are switched off.")
            if st.button("Open my portfolio", type="primary", width="stretch"):
                state.load(p, dates_known=False)
                st.rerun()

    if SAMPLE.exists() and st.button("Try with a sample portfolio", width="stretch"):
        p, _ = state.parse_broker_csv(str(SAMPLE))
        state.load(p, dates_known=False)
        st.rerun()

    st.markdown("#### Or add one by hand")
    add_form()
    theme.disclaimer()


def add_form(compact=False):
    with st.form("add_holding", clear_on_submit=True):
        c1, c2 = st.columns(2)
        ticker = c1.text_input("Ticker", placeholder="AAPL or RY.TO")
        shares = c2.number_input("Shares", min_value=0.0, step=1.0, format="%g")
        c3, c4 = st.columns(2)
        price = c3.number_input("Price paid per share", min_value=0.0, step=0.01, format="%.2f")
        known = c4.checkbox("I know the buy date", value=False)
        when = st.date_input("Buy date", max_value=None) if known else None
        if st.form_submit_button("Add to portfolio", width="stretch", type="primary"):
            try:
                p = copy.deepcopy(st.session_state.portfolio)
                pf.add_holding(p, ticker, shares, price, when)
            except ValueError as e:
                st.error(str(e))
            else:
                # Mixing dated and undated purchases: stay on the cautious side.
                was_empty = not state.has_holdings()
                state.load(p, dates_known=bool(known) if was_empty else (st.session_state.dates_known and bool(known)))
                st.rerun()
