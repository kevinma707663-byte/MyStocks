"""Per-visitor state and broker-file import. A hosted app must NOT use save_portfolio()
(one shared file for everyone), so each visitor's portfolio lives in st.session_state."""
import io

import pandas as pd
import streamlit as st

from core import portfolio as pf

REQUIRED = ["Symbol", "Quantity", "Currency", "PricePaid"]


def init():
    ss = st.session_state
    ss.setdefault("portfolio", pf.empty_portfolio())
    ss.setdefault("dates_known", True)     # False after a broker import (no buy dates in the file)
    ss.setdefault("verdicts", {})          # filled by the background worker
    ss.setdefault("tab", "Overview")
    ss.setdefault("optimizer", None)


def has_holdings() -> bool:
    return len(st.session_state.portfolio["holdings"]) > 0


def to_yahoo(symbol: str, currency: str) -> str:
    """Broker symbol -> Yahoo ticker (same rule as MyPracticeRun.ipynb)."""
    symbol = str(symbol).strip()
    return symbol.replace(".", "-") + ".TO" if str(currency).strip().upper() == "CAD" else symbol


def parse_broker_csv(file) -> tuple:
    """Return (portfolio, problems). Rows that can't be read are skipped and listed, not hidden."""
    df = pd.read_csv(file if not isinstance(file, bytes) else io.BytesIO(file))
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError("This doesn't look like a supported broker file. Missing columns: " + ", ".join(missing))
    p, problems = pf.empty_portfolio(), []
    for i, r in df.iterrows():
        try:
            pf.add_holding(p, to_yahoo(r["Symbol"], r["Currency"]), float(r["Quantity"]), float(r["PricePaid"]))
        except Exception as e:
            problems.append(f"Row {i + 2} ({r.get('Symbol', '?')}): {e}")
    if not p["holdings"]:
        raise ValueError("No holdings could be read from that file.")
    return p, problems


def load(portfolio, dates_known: bool):
    ss = st.session_state
    ss.portfolio, ss.dates_known = portfolio, dates_known
    ss.verdicts, ss.optimizer = {}, None   # caches are keyed by portfolio content, so no global clear
