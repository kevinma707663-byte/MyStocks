"""Risk: one score, eight area chips, charts tucked into expanders (progressive disclosure)."""
import streamlit as st

from app import services as sv, theme
from app.views.common import safe
from core import my_risks as mr

# One plain question per area (from the backend's own descriptions).
AREA_HELP = {
    "Concentration": "Too many eggs in one basket? Looks at your biggest holding and how few stocks you really depend on.",
    "Sector": "Is too much of your money in one industry?",
    "Currency": "How much is in a foreign currency, and what a 10% move in the exchange rate would do to your total.",
    "Moving together": "Do your stocks rise and fall together? If so, owning several protects you less than you'd think.",
    "Who brings risk": "Each stock's share of your money next to its share of your ups and downs. A small holding can bring big swings.",
    "Market risk": "How much you tend to move when the S&P 500 moves.",
    "Worst drop": "The biggest fall from a peak over the past few years.",
    "Bad day": "On a bad day, the kind that happens about 1 day in 20, how much you could lose.",
}


def render():
    p = st.session_state.portfolio
    r = safe(sv.risks, p, spinner="Measuring risk from past prices…")
    if r is None:
        return
    theme.tip("Risk is about <b>how much your portfolio could drop</b>, not whether it will. We check eight areas, "
              "score them 0 to 100 (lower = calmer), and show what stands out. It uses the past few years of prices, which is a guide, not a promise.")
    col = theme.LEVEL_COLOR[r["level"]]
    theme.card(f'<div class="muted">Risk score (higher = riskier)</div><div class="row"><div class="big">{r["score"]:.0f}</div>'
               f'{theme.chip(r["level"].upper(), col)}</div>' + theme.bar(r["score"], col) +
               f'<div class="muted">Based on {r["period"]["years"]} years of history ({r["period"]["start"]} to {r["period"]["end"]})</div>')
    if r.get("left_out"):
        theme.card(f'⚠️ Left out of this report (no price history): <b>{", ".join(r["left_out"])}</b>. '
                   f'Check the spelling; Canadian stocks need .TO, like RY.TO.')
    st.markdown("#### What to watch")
    for t in r["top_risks"]:
        theme.card(f"⚠️ {t}")
    st.markdown("#### The eight areas")
    st.caption("Tap an area to see what it asks and what we found.")
    for area, row in r["areas"].iterrows():
        c = theme.LEVEL_COLOR.get(row["level"], theme.MUTED)
        with st.expander(f"{area}  ·  {'not measurable' if row['level'] == 'n/a' else row['level']}"):
            st.caption(AREA_HELP.get(area, ""))
            st.write(row["reading"])
    with st.expander("Charts"):
        for name, fn, h in [("Sectors", mr.sector_chart, 300), ("Moving together", mr.correlation_chart, 360),
                            ("Money vs risk share", mr.risk_share_chart, 320), ("Worst drops", mr.drawdown_chart, 300)]:
            try:
                theme.show_fig(fn(r), h, key=f"risk_{name}")
            except Exception as e:
                st.caption(f"{name} chart unavailable: {e}")
    theme.learn("Risk score", "Diversification", "Correlation", "Beta", "Worst drop", "Bad day (1 in 20)")
    theme.disclaimer()
