"""Improve: the optimizer as an 'improver' of what you already own (history only)."""
import streamlit as st

from app import services as sv, theme
from app.views.common import safe
from core import my_optimizer as mo


def render():
    p = st.session_state.portfolio
    st.markdown("#### Could your mix be better balanced?")
    st.caption("Looks only at how these stocks moved in the past. It's an in-sample rule of thumb, not a forecast.")
    with st.form("opt"):
        goal = st.selectbox("Goal", list(mo.GOALS), format_func=lambda k: mo.GOALS[k].capitalize())
        c1, c2 = st.columns(2)
        maxw = c1.number_input("Max % in one stock", 5, 100, mo.MAX_WEIGHT_PCT)
        minw = c2.number_input("Min % in one stock", 0, 50, mo.MIN_WEIGHT_PCT)
        c3, c4 = st.columns(2)
        dd = c3.number_input("Max worst drop %", 5, 80, mo.MAX_DRAWDOWN_PCT)
        mr_ = c4.number_input("Min yearly return %", 0, 40, mo.MIN_RETURN_PCT)
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
    st.markdown("**Current vs best**")
    st.dataframe(res["comparison"], width="stretch")
    theme.show_fig(mo.weights_chart(res), 340, key="w")
    with st.expander("Growth of $10,000"):
        theme.show_fig(mo.growth_chart(res), 300, key="g")
    with st.expander("All mixes tried"):
        theme.show_fig(mo.cloud_chart(res), 340, key="c")
    with st.expander("MyEdit: tweak it yourself"):
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
    theme.disclaimer()
