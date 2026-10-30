"""Look and feel: colours, CSS, small HTML helpers and one Plotly style function.
Frontend only. Nothing here touches the backend."""
import streamlit as st

GREEN, RED, AMBER, BLUE, MUTED = "#4ADE80", "#F87171", "#FBBF24", "#60A5FA", "#8A97B1"
LEVEL_COLOR = {"low": GREEN, "medium": AMBER, "high": RED,
               "pass": GREEN, "fail": RED, "skip": MUTED,
               "caution": RED, "heads-up": AMBER}

CSS = """
<style>
.block-container{padding:1rem 1rem 6rem;max-width:760px}
header[data-testid="stHeader"]{background:transparent}
#MainMenu,footer{visibility:hidden}
h1,h2,h3{letter-spacing:-.02em}
.card{background:#131C2E;border:1px solid #1F2B44;border-radius:16px;padding:14px 16px;margin:8px 0}
.hero{background:linear-gradient(135deg,#16233D,#0F1A2E);border:1px solid #1F2B44;border-radius:20px;padding:18px 18px 14px;margin:4px 0 10px}
.muted{color:#8A97B1;font-size:.8rem}
.big{font-size:2rem;font-weight:700;line-height:1.1}
.mid{font-size:1.1rem;font-weight:650}
.row{display:flex;justify-content:space-between;align-items:center;gap:10px}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.72rem;font-weight:650;border:1px solid}
.pos{color:#4ADE80}.neg{color:#F87171}
.disc{color:#8A97B1;font-size:.72rem;text-align:center;margin-top:18px}
div[data-testid="stSegmentedControl"] button{padding:0 .5rem!important;font-size:.82rem!important}
div[data-testid="stSegmentedControl"]{position:sticky;top:0;z-index:50;background:#0B1220;padding:6px 0}
.stButton>button,.stDownloadButton>button{border-radius:12px;min-height:44px}
details{border-radius:14px!important}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


def chip(text, color):
    return f'<span class="chip" style="color:{color};border-color:{color}55;background:{color}18">{text}</span>'


def signed(x, suffix="%", digits=1):
    cls = "pos" if x >= 0 else "neg"
    return f'<span class="{cls}">{x:+,.{digits}f}{suffix}</span>'


def money(x, cur="CAD"):
    return f"{x:,.0f} {cur}" if abs(x) >= 1000 else f"{x:,.2f} {cur}"


def card(html):
    st.markdown(f'<div class="card">{html}</div>', unsafe_allow_html=True)


def style_fig(fig, height=300):
    """Make any backend Plotly figure fit a phone: dark, compact, no toolbar clutter."""
    if fig is None:
        return None
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=height, margin=dict(l=8, r=8, t=40, b=8), font=dict(size=11),
                      legend=dict(orientation="h", y=-0.2))
    return fig


def show_fig(fig, height=300, key=None):
    if fig is None:
        return
    st.plotly_chart(style_fig(fig, height), width="stretch", key=key,
                    config={"displayModeBar": False})


DISCLAIMER = "A rule of thumb based on past data, not financial advice."


def disclaimer():
    st.markdown(f'<div class="disc">{DISCLAIMER}</div>', unsafe_allow_html=True)
