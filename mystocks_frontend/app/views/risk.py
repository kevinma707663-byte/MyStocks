"""Risk: one score, eight area chips, charts tucked into expanders (progressive disclosure)."""
import streamlit as st

from app import services as sv, theme
from app.views.common import safe
from core import my_risks as mr


def render():
    p = st.session_state.portfolio
    r = safe(sv.risks, p, spinner="Measuring risk from past prices…")
    if r is None:
        return
    col = theme.LEVEL_COLOR[r["level"]]
    theme.card(f'<div class="muted">Risk score (higher = riskier)</div><div class="row"><div class="big">{r["score"]:.0f}</div>'
               f'{theme.chip(r["level"].upper(), col)}</div>'
               f'<div class="muted">Based on {r["period"]["years"]} years of history ({r["period"]["start"]} to {r["period"]["end"]})</div>')
    st.markdown("#### What to watch")
    for t in r["top_risks"]:
        theme.card(f"⚠️ {t}")
    st.markdown("#### The eight areas")
    for area, row in r["areas"].iterrows():
        c = theme.LEVEL_COLOR.get(row["level"], theme.MUTED)
        with st.expander(f"{area}  ·  {row['level']}"):
            st.write(row["reading"])
    with st.expander("Charts"):
        for name, fn, h in [("Sectors", mr.sector_chart, 300), ("Moving together", mr.correlation_chart, 360),
                            ("Money vs risk share", mr.risk_share_chart, 320), ("Worst drops", mr.drawdown_chart, 300)]:
            try:
                theme.show_fig(fn(r), h, key=f"risk_{name}")
            except Exception as e:
                st.caption(f"{name} chart unavailable: {e}")
    theme.disclaimer()
