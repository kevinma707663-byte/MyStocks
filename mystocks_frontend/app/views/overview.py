"""Overview: the headline, the risk chip, top insights, holdings as cards."""
import streamlit as st

from app import services as sv, state, theme
from app.views.common import safe

VERD = {"looks strong": theme.GREEN, "hold": theme.BLUE, "look closer": theme.AMBER,
        "consider trimming": theme.RED, "not enough data": theme.MUTED}


def render():
    p = st.session_state.portfolio
    pos = safe(sv.positions, p, spinner="Getting latest prices…")
    summ = safe(sv.summary, p, spinner="Adding it up…")
    if pos is None or summ is None or pos.empty:
        return

    comb, groups = summ["combined"], summ["groups"]
    total_day = sum(g["day_change"] * comb["fx_rates"].get(c, 1.0) for c, g in groups.items())
    total_cost = sum(g["cost"] * comb["fx_rates"].get(c, 1.0) for c, g in groups.items())
    total_gain = comb["value"] - total_cost
    gain_pct = total_gain / total_cost * 100 if total_cost else 0
    day_pct = total_day / (comb["value"] - total_day) * 100 if comb["value"] - total_day else 0
    cur = comb["currency"]

    st.markdown(f"""<div class="hero"><div class="muted">Total value</div>
      <div class="big">{comb['value']:,.0f} <span class="muted">{cur}</span></div>
      <div class="row" style="margin-top:8px"><div><div class="muted">Today</div>{theme.signed(day_pct)} · {theme.signed(total_day, f' {cur}', 0)}</div>
      <div style="text-align:right"><div class="muted">All time</div>{theme.signed(gain_pct)} · {theme.signed(total_gain, f' {cur}', 0)}</div></div></div>""",
                unsafe_allow_html=True)

    risk = safe(sv.risks, p, spinner="Checking risk…", show_soft=False)
    if risk:
        col = theme.LEVEL_COLOR[risk["level"]]
        theme.card(f'<div class="row"><div><div class="muted">Portfolio risk</div>'
                   f'<div class="mid">{risk["score"]:.0f} / 100</div></div>{theme.chip(risk["level"].upper(), col)}</div>')
        for t in risk["top_risks"]:
            theme.card(f"💡 {t}")

    if len(groups) > 1 or True:
        for c, g in groups.items():
            line = (f'<div class="row"><b>{c} holdings</b><span class="muted">{g["stocks"]} stocks</span></div>'
                    f'<div class="mid">{g["value"]:,.0f} {c}</div>'
                    f'<div class="muted">Gain {theme.signed(g["gain_pct"])} · Today {theme.signed(g["day_change_pct"])}</div>')
            if st.session_state.dates_known and g.get("beat_sp500_by_pct") == g.get("beat_sp500_by_pct"):
                line += f'<div class="muted">vs S&P 500 twin: {theme.signed(g["beat_sp500_by_pct"], " pts")}</div>'
            theme.card(line)

    st.markdown("#### Holdings")
    vs = st.session_state.verdicts.get("done", {})
    for _, r in pos.iterrows():
        v = vs.get(r["ticker"])
        badge = theme.chip(v["verdict"], VERD.get(v["verdict"], theme.MUTED)) if v else ""
        theme.card(f'<div class="row"><div><b>{r["ticker"]}</b> <span class="muted">{(r["name"] or "")[:28]}</span></div>{badge}</div>'
                   f'<div class="row" style="margin-top:6px"><div class="mid">{r["value"]:,.0f} <span class="muted">{r["currency"]}</span></div>'
                   f'<div style="text-align:right">{theme.signed(r["gain_pct"])}<div class="muted">{r["weight_pct"]:.1f}% of portfolio</div></div></div>')

    with st.expander("Allocation chart"):
        theme.show_fig(sv_chart_alloc(pos), 320, key="alloc")
    if st.session_state.dates_known:
        with st.expander("Value over time"):
            for c in groups:
                h = safe(sv.history, p, c)
                if h is not None:
                    from core import my_stocks as ms
                    theme.show_fig(ms.value_chart(h, c), 280, key=f"hist{c}")
    else:
        st.caption("Value-over-time is hidden: imported files have no purchase dates.")
    theme.disclaimer()


def sv_chart_alloc(pos):
    from core import my_stocks as ms
    return ms.allocation_chart(pos)
