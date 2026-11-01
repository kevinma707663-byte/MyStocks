"""Shared view helpers: friendly error handling and the unknown-buy-date rule."""
import streamlit as st

# These backend warnings need real buy dates. After a broker import every date is "today",
# so they would be false alarms. We hide them (UI only) until real dates exist.
DATE_DEPENDENT = {"Overtrading", "Holding a loser", "Quick flip"}


def safe(fn, *args, spinner="Loading…", show_soft=True, **kwargs):
    """Call a services.* function. Returns the result or None; shows readable messages, never a traceback."""
    try:
        with st.spinner(spinner):
            result, soft = fn(*args, **kwargs)
    except ValueError as e:               # the backend's own plain-English messages
        st.error(str(e))
        return None
    except Exception as e:
        st.error("Couldn't load this right now. Market data providers sometimes rate-limit or time out. "
                 "Try again in a minute.")
        with st.expander("Technical details"):
            st.code(f"{type(e).__name__}: {e}")
        return None
    if show_soft:
        for m in soft:
            st.warning(m)
    return result


def filter_dates(found: list) -> list:
    if st.session_state.get("dates_known", True):
        return found
    return [w for w in found if w["trap"] not in DATE_DEPENDENT]
