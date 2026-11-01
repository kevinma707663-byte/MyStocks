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

MAX_COACH_NOTES = 5      # per visitor session: a public app must not let one visitor run up the API bill


def _md(text):
    """AI text shown as plain markdown: a '$' pair would otherwise turn into a maths formula."""
    return str(text).replace("$", "\\$")


def _coach_card(tip):
    if tip["status"] == "ok":
        st.markdown("**🤖 AI coach**")
        st.info(_md(tip["note"]))
        for b in tip["biases"]:
            st.markdown(f'🧠 **{b["bias"]}**: you wrote "{_md(b["quote"])}". <span class="muted">({b["meaning"]})</span>',
                        unsafe_allow_html=False)
        st.caption(tip["disclaimer"])
    else:
        st.caption(f'🤖 AI coach: {tip["why"]}')


def _trade_form(p):
    ss = st.session_state
    with st.form("trade"):
        action = st.radio("Action", ["buy", "sell"], horizontal=True)
        c1, c2, c3 = st.columns([2, 1, 1])
        ticker = c1.text_input("Ticker", placeholder="AAPL")
        shares = c2.number_input("Shares", min_value=0.0, step=1.0, format="%g")
        price = c3.number_input("Price", min_value=0.0, step=0.01, format="%.2f")
        reason = st.text_area("Why are you making this trade? (optional)",
                              placeholder="e.g. everyone's talking about it", height=80)
        go = st.form_submit_button("Check this trade", type="primary", width="stretch")

    if go:
        ss.pop("pending_trade", None)
        found = safe(sv.check_trade, p, action, ticker, shares, price, spinner="Checking for traps…")
        if found is not None:                      # None = a friendly error was already shown
            found = filter_dates(found)
            if ss.get("coach_calls", 0) >= MAX_COACH_NOTES:
                tip = {"status": "off", "note": None, "biases": [], "disclaimer": "",
                       "why": f"You've used all {MAX_COACH_NOTES} coach notes for this visit."}
            else:
                try:
                    with st.spinner("Your coach is thinking…"):
                        tip = sv.coach_note(p, action, ticker, shares, price, reason, found, ss.dates_known)
                    if tip["status"] == "ok":
                        ss.coach_calls = ss.get("coach_calls", 0) + 1
                except ValueError as e:
                    st.error(str(e))
                    return
            ss.pending_trade = {"action": action, "ticker": ticker, "shares": shares, "price": price}
            ss.pending_found, ss.pending_tip = found, tip

    if "pending_trade" in ss:
        t = ss.pending_trade
        st.markdown(f'**{t["action"].title()} {t["shares"]:g} {t["ticker"].strip().upper()} at {t["price"]:.2f}**')
        _cards(ss.pending_found)
        _coach_card(ss.pending_tip)
        b1, b2 = st.columns(2)
        if b1.button("Record it", type="primary", width="stretch"):
            try:
                newp, _ = ws.trade(copy.deepcopy(p), **t)
            except ValueError as e:
                st.error(str(e))
            else:
                ss.portfolio = newp
                ss.verdicts = {}
                del ss["pending_trade"]
                st.toast("Recorded.")
                st.rerun()
        if b2.button("Discard", width="stretch"):
            del ss["pending_trade"]
            st.rerun()


def render():
    p = st.session_state.portfolio
    theme.tip("These are <b>common investing traps</b> (like buying because everyone else is, or selling in a panic). "
              "We point them out so you can pause and think. We never block anything: it's your call.")
    st.markdown("#### Heads-up on what you own")
    found = safe(sv.standing, p, spinner="Checking for common traps…")
    if found is not None:
        _cards(filter_dates(found))
        if not st.session_state.dates_known:
            st.caption("Warnings that need purchase dates are hidden because imported files don't include them.")

    st.markdown("#### Thinking of a trade? Check it first")
    st.caption("Tell us what you're about to do and, if you like, why. Writing the reason down is a good habit.")
    _trade_form(p)
    with st.expander("Trade diary"):
        st.dataframe(pf.trades_table(p), width="stretch")
    theme.learn("FOMO (chasing)", "Averaging down", "Panic selling", "Superficial loss", "Overtrading")
    theme.disclaimer()
