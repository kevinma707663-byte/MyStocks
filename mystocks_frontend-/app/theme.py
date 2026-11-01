"""Look and feel: colours, CSS, small HTML helpers and one Plotly style function.
Frontend only. Nothing here touches the backend."""
import streamlit as st

GREEN, RED, AMBER, BLUE, MUTED = "#15803D", "#B91C1C", "#B45309", "#1D4ED8", "#64748B"
LEVEL_COLOR = {"low": GREEN, "medium": AMBER, "high": RED,
               "pass": GREEN, "fail": RED, "skip": MUTED,
               "caution": RED, "heads-up": AMBER, "n/a": MUTED}

CSS = """
<style>
.block-container{padding:1rem 1rem 6rem;max-width:760px}
header[data-testid="stHeader"]{background:transparent}
#MainMenu,footer{visibility:hidden}
h1,h2,h3,h4{letter-spacing:-.02em;color:#1B2433}
.card{background:#FFFFFF;border:1px solid #E3E8F0;border-radius:16px;padding:14px 16px;margin:8px 0;box-shadow:0 1px 3px rgba(16,24,40,.06)}
.hero{background:linear-gradient(135deg,#E8F1FF,#F5F9FF);border:1px solid #CFE0FB;border-radius:20px;padding:18px 18px 14px;margin:4px 0 10px}
.tip{background:#EEF5FF;border:1px solid #CFE0FB;border-radius:14px;padding:10px 14px;margin:6px 0 12px;font-size:.9rem;line-height:1.45;color:#23314A}
.say{font-size:.86rem;color:#3B4760;margin-top:4px}
.muted{color:#5B6778;font-size:.8rem}
.big{font-size:2rem;font-weight:700;line-height:1.1}
.mid{font-size:1.1rem;font-weight:650}
.row{display:flex;justify-content:space-between;align-items:center;gap:10px}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:.74rem;font-weight:650;border:1px solid}
.pos{color:#15803D;font-weight:600}.neg{color:#B91C1C;font-weight:600}
.bar{height:8px;border-radius:99px;background:#E6EBF3;overflow:hidden;margin:8px 0 2px}
.bar>i{display:block;height:100%;border-radius:99px}
.disc{color:#5B6778;font-size:.74rem;text-align:center;margin-top:18px}
div[data-testid="stSegmentedControl"] button{padding:0 .5rem!important;font-size:.82rem!important}
div[data-testid="stSegmentedControl"]{position:sticky;top:0;z-index:50;background:#F6F8FB;padding:6px 0}
.stButton>button,.stDownloadButton>button{border-radius:12px;min-height:44px}
details{border-radius:14px!important;background:#FFFFFF}
div[data-testid="stProgressBarTrack"]{background:#E1E7F0!important}
</style>
"""

# Plain-English meanings (worded from the backend's own explanations in core/).
GLOSSARY = {
    "Gain": "How much more (or less) your stocks are worth now than what you paid for them.",
    "% of portfolio": "The slice of your total money that is in this one stock.",
    "S&P 500 twin": "An imaginary copy of your portfolio that put the same money into the S&P 500 (the SPY fund) on the same days. If you're ahead of your twin, you beat the market.",
    "Diversification": "Spreading your money across different stocks and industries, so one bad stock hurts less.",
    "Risk score": "0 to 100 from eight checks on how your portfolio could get hurt. Higher means bumpier. A low score doesn't mean no risk: every stock can still fall.",
    "Beta": "How much you tend to move when the S&P 500 moves. Beta 1.2 means a 10% market fall has tended to mean about 12% for you.",
    "Correlation": "Whether two stocks rise and fall together. 1 means always together, 0 means unrelated. If your stocks move together, owning several protects you less than you'd think.",
    "Worst drop": "The biggest fall from a peak to a low. -25% means that at its worst, $10,000 shrank to $7,500.",
    "Bad day (1 in 20)": "On a bad day, the kind that happens about 1 day in 20, how much you could lose.",
    "Score (0 to 100)": "Each stock is checked six ways (business health, rivals, value, economy, price chart, analysts). 50 is neutral; higher is better.",
    "Momentum": "Whether a stock (and the experts' opinions of it) have been moving up or down lately.",
    "RSI": "A 0 to 100 gauge of how fast a price has moved. Above 70 means it ran up fast and may cool off. Below 30 means it fell fast and may bounce.",
    "Moving average": "The average closing price over the last 50 or 200 days. It smooths out daily noise so you can see the trend.",
    "DCF": "A way to estimate what a business is worth: add up the cash it may hand back in future, shrunk down because future money is worth less than money today. It's only as good as its guesses.",
    "P/E": "Price divided by yearly profit per share: how many dollars you pay for each $1 of profit. Lower is cheaper.",
    "Sharpe ratio": "Return for each bump of risk. Above 1 is good, above 2 is excellent.",
    "Yearly swings": "How much the value bounces around in a year. Bigger means bumpier.",
    "FOMO (chasing)": "Buying because a price has been rising fast and you don't want to miss out. Prices that run up quickly often cool off.",
    "Averaging down": "Buying more of a stock you're losing money on, hoping to get back to even faster.",
    "Panic selling": "Selling in a hurry right after a sharp drop, which often locks in the worst price.",
    "Superficial loss": "In Canada, buying back a stock within 30 days of selling it at a loss can stop you claiming that loss for tax. Not tax advice: check with an accountant.",
    "Overtrading": "Lots of trades in a short time. Every trade costs fees and attention, and busy traders usually do worse.",
}


def tip(text):
    st.markdown(f'<div class="tip">💡 {text}</div>', unsafe_allow_html=True)


def learn(*terms, title="📖 Words explained"):
    with st.expander(title):
        for k in terms:
            st.markdown(f"**{k}**  \n{GLOSSARY[k]}")


def bar(score, color, label=""):
    """A simple 0-100 bar. Easier to read at a glance than a bare number."""
    w = max(0, min(100, 0 if score != score else score))
    return (f'<div class="bar"><i style="width:{w:.0f}%;background:{color}"></i></div>'
            + (f'<div class="muted">{label}</div>' if label else ""))


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
    """Make any backend Plotly figure fit a phone: light, compact, no toolbar clutter."""
    if fig is None:
        return None
    fig.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
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
