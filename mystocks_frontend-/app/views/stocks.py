"""Stocks: background verdicts for everything you own, plus a deep dive on any ticker."""
import streamlit as st

from app import services as sv, theme
from app.views.common import safe
from app.views.overview import VERD, VERD_PLAIN
from core import analysts as an, dcf, financials as fin, rivals as rv, technicals as ta, verdict as vd


def _list(store):
    done, errs = store.get("done", {}), store.get("errors", {})
    total = store.get("total", 0)
    running = store.get("running", False)
    if total:
        st.progress(min(1.0, (len(done) + len(errs)) / total),
                    text=("Scoring your stocks…" if running else "All stocks scored") + f" ({len(done) + len(errs)}/{total})")
    for t, v in done.items():
        sc = "n/a" if v["score"] != v["score"] else f'{v["score"]:.0f}'
        theme.card(f'<div class="row"><div><b>{t}</b> <span class="muted">{(v["name"] or "")[:26]}</span></div>'
                   f'{theme.chip(v["verdict"], VERD.get(v["verdict"], theme.MUTED))}</div>'
                   + (f'<div class="say">{VERD_PLAIN.get(v["verdict"], "")}</div>' if sc != "n/a" else "")
                   + (theme.bar(v["score"], VERD.get(v["verdict"], theme.MUTED), f'Score {sc} out of 100 · momentum: {v["momentum"]["reading"]}') if sc != "n/a" else '<div class="muted">No score yet: not enough data for this one</div>'))
    for t, e in errs.items():
        theme.card(f"<b>{t}</b> <span class='muted'>couldn't be scored: {e}</span>")
    return running


def render():
    p = st.session_state.portfolio
    store = st.session_state.verdicts
    pos = safe(sv.positions, p, show_soft=False)
    tickers = list(pos.sort_values("weight_pct", ascending=False)["ticker"]) if pos is not None and not pos.empty else []

    theme.tip("Each stock gets a <b>0 to 100 score</b> from six checks: business health, rivals, value, the economy, the price chart and what analysts say. "
              "It's a rule of thumb for deciding <b>what to look into</b>, not what to buy or sell.")
    st.markdown("#### Your stocks, scored")
    st.caption("Quick scores skip the slow 'versus rivals' step. Open any stock for the full picture.")
    if tickers and not store:
        sv.start_verdicts(store, tickers)

    @st.fragment(run_every=3 if store.get("running") else None)
    def live():
        running = _list(store)
        if not running and store.get("total"):
            if store.get("_rerun_done") is None:
                store["_rerun_done"] = True
                st.rerun()
    live()

    st.markdown("#### Look closer")
    options = tickers
    c1, c2 = st.columns([3, 2])
    pick = c1.selectbox("Your stock", options, index=None, placeholder="Choose…") if options else None
    typed = c2.text_input("Or any ticker", placeholder="MSFT, TD.TO")
    ticker = (typed.strip().upper() or pick) if (typed or pick) else None
    if ticker:
        detail(ticker)
    theme.learn("Score (0 to 100)", "Momentum", "RSI", "Moving average", "DCF", "P/E")
    theme.disclaimer()


def detail(t):
    st.markdown(f"### {t}")
    with_rivals = st.toggle("Include rivals comparison (slower, 15–30 s)", value=False, key=f"rv_{t}")
    v = safe(sv.verdict_one, t, with_rivals, spinner=f"Analysing {t}…")
    if v is None:
        return
    sc = "n/a" if v["score"] != v["score"] else f'{v["score"]:.0f}'
    theme.card(f'<div class="muted">{v["name"]}</div><div class="row"><div class="big">{sc}<span class="muted">/100</span></div>'
               f'{theme.chip(v["verdict"], VERD.get(v["verdict"], theme.MUTED))}</div>'
               + (theme.bar(v["score"], VERD.get(v["verdict"], theme.MUTED)) if sc != "n/a" else "")
               + f'<div class="say">{VERD_PLAIN.get(v["verdict"], "")}</div>'
               f'<div class="muted">Momentum: {v["momentum"]["reading"]}</div>')
    if v["strengths"]:
        st.markdown("**What looks good**")
    for s in v["strengths"]:
        theme.card(f"✅ {s}")
    if v["concerns"]:
        st.markdown("**What to look at**")
    for c in v["concerns"]:
        theme.card(f"⚠️ {c}")
    with st.expander("How the score is built"):
        st.dataframe(v["parts"].round(1), width="stretch")
        try:
            theme.show_fig(vd.verdict_chart(v), 300, key=f"vc_{t}")
        except Exception:
            pass
    with st.expander("Health checks"):
        if len(v["health_checks"]):
            st.dataframe(v["health_checks"], width="stretch")
        else:
            st.caption("No financial statements available (common for ETFs and funds).")

    tabs = st.tabs(["Technicals", "Analysts", "Valuation (DCF)", "Financials", "Rivals"])
    with tabs[0]:
        st.caption("What the price chart is doing: trend, moving averages and RSI. Often wrong over short periods.")
        if st.button("Load technicals", key=f"ta_{t}"):
            s = safe(sv.technicals, t)
            if s:
                st.write(f'Signal: **{s["verdict"]}** (score {s["score"]:.0f})')
                st.dataframe(s["signals"], width="stretch")
                theme.show_fig(ta.technical_chart(s), 520, key=f"tc_{t}")
    with tabs[1]:
        st.caption("What professional analysts say, and which way their opinions are moving. Analysts lean optimistic.")
        if st.button("Load analyst views", key=f"an_{t}"):
            s = safe(sv.analysts, t)
            if s:
                st.write(f'Analysts: **{s["verdict"]}**')
                st.dataframe(s["signals"], width="stretch")
                for f_, k in [(an.targets_chart, "tg"), ]:
                    try:
                        theme.show_fig(f_(s), 300, key=f"{k}_{t}")
                    except Exception:
                        pass
                if s.get("target_currency_note"):
                    st.caption(s["target_currency_note"])
    with tabs[2]:
        st.caption("A DCF is very sensitive to its assumptions. Treat the result as one input, not an answer.")
        if st.button("Run valuation", key=f"dcf_{t}"):
            r = safe(sv.dcf_for, t)
            if r:
                theme.card(f'<div class="muted">Value per share</div><div class="big">{r["value_per_share"]:,.2f} {r["currency"]}</div>'
                           f'<div class="muted">Price {r["price"]:,.2f} · {r["verdict"]} ({r["upside_pct"]:+.0f}%)</div>')
                for n in r["notes"]:
                    st.caption("• " + n)
                st.dataframe(r["assumptions"], width="stretch")
                theme.show_fig(dcf.bridge_chart(r), 320, key=f"br_{t}")
                with st.expander("Sensitivity"):
                    st.dataframe(r["sensitivity"], width="stretch")
    with tabs[3]:
        st.caption("The standard health numbers from the company's reports. 'n/a' means the company doesn't report it.")
        if st.button("Load financial ratios", key=f"fin_{t}"):
            r = safe(sv.ratios, t)
            if r is not None and len(r):
                st.dataframe(fin.format_ratios(r), width="stretch")
    with tabs[4]:
        st.caption("How it stacks up against its biggest competitors, scored 0 to 100.")
        if st.button("Compare with rivals", key=f"rvb_{t}"):
            r = safe(sv.rivals, t, spinner="Downloading rivals… 15–30 s first time")
            if r:
                st.write("Rivals: " + ", ".join(r["rivals"]))
                st.dataframe(r["scores"], width="stretch")
                try:
                    theme.show_fig(rv.scores_chart(r["scores"], t), 320, key=f"rs_{t}")
                except Exception:
                    pass
