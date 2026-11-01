"""MyStocks: mobile-first Streamlit front end. Run:  streamlit run streamlit_app.py
`core/` (backend) is imported as-is and never modified."""
import streamlit as st

st.set_page_config(page_title="MyStocks", page_icon="📈", layout="centered", initial_sidebar_state="collapsed")

from app import state, theme                       # noqa: E402
from app.views import headsup, improve, overview, risk, start, stocks  # noqa: E402

theme.inject()
state.init()

if not state.has_holdings():
    start.render()
    st.stop()

TABS = {"Overview": overview, "Risk": risk, "Stocks": stocks, "Improve": improve, "Alerts": headsup}
tab = st.segmented_control("Section", list(TABS), default=st.session_state.tab, label_visibility="collapsed", key="nav")
tab = tab or st.session_state.tab
st.session_state.tab = tab
TABS[tab].render()

with st.expander("Portfolio"):
    start.add_form()
    if st.button("Start over / import a different file"):
        state.load(__import__("core.portfolio", fromlist=["x"]).empty_portfolio(), True)
        st.rerun()
