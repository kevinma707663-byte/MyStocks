"""Improve: the optimizer as an 'improver' of what you already own (history only)."""
import streamlit as st

from app import services as sv, theme
from app.views.common import safe
from core import my_optimizer as mo


def render():
    p = st.session_state.portfolio
    st.markdown("#### Could your mix be better balanced?")
    theme.tip("Set your own rules below. We try thousands of different splits of <b>the stocks you already own</b> on their past prices, "
              "throw out any that break your rules, and show the best one next to what you have now. "
              "The best mix for the past is rarely the best for the future, so use it as a starting point.")
    with st.form("opt"):
        goal = st.selectbox("What matters most?", list(mo.GOALS), format_func=lambda k: mo.GOALS[k].capitalize().replace("sharpe", "Sharpe"),
                            help="Highest Sharpe ratio = the most return for each bump of risk. Lowest risk = the calmest mix. Highest return = the biggest past growth.")
        c1, c2 = st.columns(2)
        maxw = c1.number_input("Most in any one stock (%)", 5, 100, mo.MAX_WEIGHT_PCT,
                               help="Stops the best mix from piling everything into last period's winner.")
        minw = c2.number_input("Least in any one stock (%)", 0, 50, mo.MIN_WEIGHT_PCT,
                               help="0 lets it drop a stock completely.")
        c3, c4 = st.columns(2)
        dd = c3.number_input("Biggest fall you'd accept (%)", 5, 80, mo.MAX_DRAWDOWN_PCT,
                             help="The biggest drop from a peak you can stomach. 25 means $10,000 shrinking to $7,500 at its worst.")
        mr_ = c4.number_input("Least yearly return (%)", 0, 40, mo.MIN_RETURN_PCT,
                              help="The least you'd accept per year, on average, in the past data.")
        extra = st.text_input("Also consider (optional)", placeholder="MSFT, TD.TO")
        go = st.form_submit_button("Find a better mix", type="primary", width="stretch")
    if go:
        add = tuple(t.strip().upper() for t in extra.split(",") if t.strip())
        rules = (("goal", goal), ("max_weight_pct", maxw), ("min_weight_pct", minw),
                 ("max_drawdown_pct", dd), ("min_return_pct", mr_))
        st.session_state.optimizer = safe(sv.optimize, p, add, rules, spinner="Trying thousands of mixes…")
    res = st.session_state.optimizer
    if res is None:
        theme.disclaimer(); return
    if res["status"] != "ok":
        st.warning(res["message"])
    else:
        st.success(res["message"])
    st.markdown("**Your mix now vs the best mix we found**")
    st.dataframe(res["comparison"], width="stretch")
    theme.show_fig(mo.weights_chart(res), 340, key="w")
    with st.expander("Growth of $10,000"):
        theme.show_fig(mo.growth_chart(res), 300, key="g")
    with st.expander("All mixes tried"):
        theme.show_fig(mo.cloud_chart(res), 340, key="c")
    with st.expander("Tweak it yourself"):
        st.caption("Set one stock to the % you like. The others share what's left in the same proportions. We'll tell you which of your rules that breaks.")
        t = st.selectbox("Stock", res["tickers"], key="edit_t")
        v = st.slider("Set to % of your money", 0, 100, 10, key="edit_v")
        if st.button("Apply edit"):
            try:
                out, soft = sv._run(mo.my_edit, res, {t: v})
                st.session_state.optimizer = out
                for b in out["breaks"]:
                    st.warning(b)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    theme.learn("Sharpe ratio", "Yearly swings", "Worst drop", "Diversification")
    theme.disclaimer()
